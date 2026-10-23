// A headless companion for development and end-to-end tests.
//
// It runs the same job executor and native connectors as the Windows app
// (platform/desktop-runtime/src/jobs.js), against a local Minkops server and
// the Tally that `scripts/wsl_tally_forward.py` relays to 127.0.0.1. Folder
// grants are not offered headless. Credentials and durable save intents are
// plain files in an owner-only development directory, so never point this at
// a production server.
//
//   node scripts/companion_dev.mjs register ORIGIN TENANT EMAIL   (password on stdin)
//   node scripts/companion_dev.mjs run
import { readFileSync } from "node:fs";
import { mkdir, open, readFile, writeFile, rename } from "node:fs/promises";
import { hostname, homedir } from "node:os";
import { join } from "node:path";
import { randomUUID } from "node:crypto";
import { checkTally, createSupplier, runSync, saveVoucher, tallyTransport } from "../connectors/desktop/src/index.js";
import { CompanionWorker } from "../platform/desktop-runtime/src/worker.js";
import { createExecutor, PLAN_VERSION } from "../platform/desktop-runtime/src/jobs.js";

const ROOT = process.env.MINKOPS_COMPANION_DIR ?? join(homedir(), ".local/state/minkops-dev/companion");
const STATE = join(ROOT, "state.json");
const VERSION = JSON.parse(await readFile(new URL("../apps/windows-app/package.json", import.meta.url), "utf8")).version;
const pc = `${hostname().slice(0, 70)}-HEADLESS`;

async function load() {
  return JSON.parse(await readFile(STATE, "utf8"));
}
async function save(state) {
  await mkdir(ROOT, { recursive: true, mode: 0o700 });
  await writeFile(`${STATE}.tmp`, JSON.stringify(state, null, 2), { mode: 0o600 });
  await rename(`${STATE}.tmp`, STATE);
}

async function register([origin, tenant, email]) {
  if (!/^http:\/\/(127\.0\.0\.1|localhost):\d+$/.test(origin ?? "")) throw new Error("Register only against a local server.");
  const password = readFileSync(0, "utf8").trim();
  const login = await fetch(`${origin}/api/auth/login`, { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }) });
  if (!login.ok) throw new Error(`Sign-in failed (${login.status}).`);
  const cookie = login.headers.getSetCookie().map((c) => c.split(";")[0]).join("; ");
  const me = await (await fetch(`${origin}/api/auth/me`, { headers: { cookie } })).json();
  const response = await fetch(`${origin}/api/tenants/${tenant}/desktop/devices`, { method: "POST",
    headers: { cookie, "Content-Type": "application/json", "x-csrf-token": me.csrf_token },
    body: JSON.stringify({ name: pc, installation_id: randomUUID() }) });
  if (!response.ok) throw new Error(`Registration failed (${response.status}): ${await response.text()}`);
  const device = await response.json();
  await save({ origin, tenant, device_id: device.id, credential: device.credential, pending: null });
  console.log(`Registered ${pc} as device ${device.id}.`);
}

async function run() {
  const state = await load();
  const request = async (path, body) => {
    const response = await fetch(state.origin + path, {
      method: body === undefined ? "GET" : "POST", redirect: "error",
      signal: AbortSignal.timeout(path.endsWith("/finish") ? 120000 : 45000),
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${state.credential}`,
        "X-Minkops-Plan-Version": String(PLAN_VERSION), "X-Minkops-Companion-Version": VERSION,
        "X-Minkops-Host": pc, "X-Minkops-Session": "console" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (!response.ok) {
      const detail = await response.json().catch(() => null);
      throw Object.assign(new Error(typeof detail?.detail === "string" ? detail.detail : `HTTP ${response.status}`),
        { status: response.status });
    }
    return response.json();
  };
  const intents = join(ROOT, "intents");
  const execute = createExecutor({
    connectors: { checkTally, createSupplier, saveVoucher, runSync }, request, pc,
    transportFor: () => tallyTransport({ pc }),
    grantFor: () => { throw new Error("Folder grants are not available headless."); },
    // One fsynced file per remote ID: once written, that voucher is never imported again.
    durableIntent: (job) => async (intent) => {
      await mkdir(intents, { recursive: true, mode: 0o700 });
      let handle;
      try { handle = await open(join(intents, `${intent.remote_id}.json`), "wx", 0o600); }
      catch (error) { if (error.code === "EEXIST") return false; throw error; }
      try { await handle.writeFile(JSON.stringify({ job_id: job.id, plan: intent })); await handle.sync(); }
      finally { await handle.close(); }
      return true;
    },
  });
  const worker = new CompanionWorker({
    request, execute,
    heartbeat: () => request("/api/desktop/worker/heartbeat", {}),
    pending: () => state.pending,
    savePending: async (pending) => { state.pending = pending; await save(state); },
  });
  console.log(`${pc} (companion ${VERSION}) polling ${state.origin} for tenant ${state.tenant}.`);
  for (;;) {
    try { await worker.tick(); }
    catch (error) {
      console.error(`tick: ${error.message}`);
      if (error.status === 401) process.exit(1);
    }
    await new Promise((resolve) => setTimeout(resolve, 2000));
  }
}

const [command, ...args] = process.argv.slice(2);
if (command === "register") await register(args);
else if (command === "run") await run();
else {
  console.error("Usage: companion_dev.mjs register ORIGIN TENANT EMAIL | run");
  process.exit(2);
}
