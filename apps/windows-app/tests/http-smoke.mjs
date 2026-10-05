/** Opt-in HTTP/native integration against an isolated, migrated dev database.
 * Requires AUTH_DEV_MODE=1. Never point this fixture at a customer deployment. */
import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import { mkdtemp, readFile, writeFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
  inventory,
  tallyProbe,
} from "../../../connectors/desktop/src/index.js";
import { CompanionWorker } from "../../../platform/desktop-runtime/src/worker.js";

const origin = process.env.MINKOPS_SMOKE_URL;
assert.ok(
  /^http:\/\/(127\.0\.0\.1|localhost):\d+$/.test(origin || ""),
  "Use an isolated localhost API",
);
let cookie = "";
let csrf = "";
async function api(
  path,
  body,
  method = body === undefined ? "GET" : "POST",
  credential,
) {
  const form = body instanceof FormData;
  const response = await fetch(origin + path, {
    method,
    redirect: "error",
    signal: AbortSignal.timeout(10000),
    headers: {
      ...(form ? {} : { "Content-Type": "application/json" }),
      ...(credential
        ? { Authorization: `Bearer ${credential}` }
        : { Cookie: cookie, "x-csrf-token": csrf }),
    },
    body: body === undefined ? undefined : form ? body : JSON.stringify(body),
  });
  if (!response.ok) {
    const error = new Error(`HTTP ${response.status} at ${path}`);
    error.status = response.status;
    throw error;
  }
  const setCookie = response.headers.get("set-cookie");
  if (setCookie) cookie = setCookie.split(";")[0];
  return response.json();
}
const email = `native-http-${randomUUID()}@example.com`;
const password = "native smoke test password 123!";
const signup = await api("/api/auth/signup", {
  name: "Native smoke",
  email,
  password,
  organization_name: "Isolated desktop smoke",
});
await api("/api/auth/verify", {
  token: signup.verification_link.split("/").at(-1),
});
await api("/api/auth/login", { email, password });
const user = await api("/api/auth/me");
csrf = user.csrf_token;
const base = `/api/tenants/${user.memberships[0].slug}`;
const device = await api(base + "/desktop/devices", {
  name: "Windows native smoke",
  installation_id: randomUUID(),
});
const root = await mkdtemp(join(tmpdir(), "minkops-http-"));
try {
  await writeFile(join(root, "invoice.pdf"), "%PDF-1.4 native fixture");
  const files = await inventory(root);
  const form = new FormData();
  form.append("label", "Native fixture");
  form.append("writable", "true");
  form.append("paths", JSON.stringify(files.map((f) => f.path)));
  for (const file of files)
    form.append(
      "files",
      new Blob([Buffer.from(file.content, "base64")]),
      file.path,
    );
  const source = await api(base + "/accounts/sources", form);
  await api(
    base + `/desktop/devices/${device.id}/sources/${source.id}`,
    {},
    "POST",
  );
  await writeFile(
    join(root, "invoice.pdf"),
    "%PDF-1.4 refreshed native fixture",
  );
  const job = await api(base + "/desktop/jobs", {
    device_id: device.id,
    request_key: randomUUID(),
    operation: "files.refresh",
    input: { source_id: source.id },
  });
  const pendingFile = join(root, ".receipt.json");
  let executions = 0;
  let interrupt = true;
  const options = {
    request: async (path, body) => {
      const result = await api(path, body, "POST", device.credential);
      if (path.endsWith("/finish") && interrupt) {
        interrupt = false;
        throw new Error("Lost acknowledgement after server commit");
      }
      return result;
    },
    execute: async (claimed) => {
      assert.equal(claimed.id, job.id);
      executions++;
      return { files: await inventory(root) };
    },
    pending: () => options.saved,
    savePending: async (value) => {
      options.saved = value;
      await writeFile(pendingFile, JSON.stringify(value));
    },
    saved: null,
  };
  await assert.rejects(
    new CompanionWorker(options).tick(),
    /Lost acknowledgement/,
  );
  options.saved = JSON.parse(await readFile(pendingFile, "utf8"));
  await new CompanionWorker(options).tick();
  assert.equal(executions, 1);
  assert.equal(options.saved, null);
  const completed = await api(base + `/desktop/jobs/${job.id}`);
  assert.equal(completed.state, "completed");
  assert.equal(completed.result.file_count, 1);
  const refreshed = await api(base + "/accounts/sources");
  assert.notEqual(refreshed[0].files[0].sha256, source.files[0].sha256);
  const probe = await api(base + "/desktop/jobs", {
    device_id: device.id,
    request_key: randomUUID(),
    operation: "tally.probe",
    input: {},
  });
  const worker = new CompanionWorker({
    ...options,
    execute: () => tallyProbe(),
  });
  await worker.tick();
  const tally = await api(base + `/desktop/jobs/${probe.id}`);
  assert.ok(["completed", "failed"].includes(tally.state));
  console.log(
    `HTTP + PostgreSQL + Windows native folder refresh and restart/replay passed. Tally: ${tally.state}.`,
  );
  await api(base + `/desktop/devices/${device.id}`, undefined, "DELETE");
  await assert.rejects(
    api("/api/desktop/worker/claim", {}, "POST", device.credential),
    (error) => error.status === 401,
  );
  console.log("Device revocation passed.");
} finally {
  await rm(root, { recursive: true, force: true });
}
