import test from "node:test";
import assert from "node:assert/strict";
import {
  ensureTallyDiscovery,
  startupCompanies,
} from "../src/tally-recovery.js";

const companies = ["A", "B", "Unopened"].map((company, i) => ({
  company,
  company_guid: `guid-${i}`,
  company_number: `${100000 + i}`,
}));
const xml = (values, disk) =>
  `<ENVELOPE><HEADER><STATUS>1</STATUS></HEADER><BODY><DATA><COLLECTION>${values
    .map((c) => {
      const tag = disk ? "COMPANYONDISK" : "COMPANY";
      return `<${tag}><NAME>${c.company}</NAME>${disk ? "" : `<GUID>${c.company_guid}</GUID>`}<COMPANYNUMBER TYPE="Number"> ${c.company_number}</COMPANYNUMBER></${tag}>`;
    })
    .join("")}</COLLECTION></DATA></BODY></ENVELOPE>`;

test("discovery starts stopped Tally with all configured company directories", async () => {
  let running = false;
  const events = [];
  const result = await ensureTallyDiscovery(
    { port: 9000 },
    {
      installation: async () => ({
        exe: "known",
        loads: companies.map((c) => c.company_number),
        pid: running ? 1 : null,
      }),
      isRunning: async () => running,
      start: async (observed) => {
        events.push(observed.loads);
        running = true;
      },
      stop: async () => assert.fail("already stopped"),
      ready: async () => {},
      request: async (_url, { body }) =>
        new Response(xml(companies, body.includes("Company on Disk"))),
    },
  );
  assert.deepEqual(events, [["100000", "100001", "100002"]]);
  assert.deepEqual(result.company_scope, companies);
});

test("discovery includes an unopened on-disk company through graceful scoped restart", async () => {
  let loaded = companies.slice(0, 2),
    stopped = false;
  const result = await ensureTallyDiscovery(
    { port: 9000 },
    {
      installation: async () => ({ exe: "known", pid: 1, loads: ["100000"] }),
      isRunning: async () => true,
      stop: async () => {
        stopped = true;
      },
      start: async (observed) => {
        assert.equal(stopped, true);
        assert.deepEqual(observed.loads, ["100000", "100001", "100002"]);
        assert.equal(observed.required_companies.length, 3);
        loaded = companies;
      },
      ready: async () => {},
      request: async (_url, { body }) =>
        new Response(
          xml(
            body.includes("Company on Disk") ? companies : loaded,
            body.includes("Company on Disk"),
          ),
        ),
    },
  );
  assert.equal(result.company_scope.length, 3);
});

test("discovery loads configured companies when Tally is running with none open", async () => {
  let loaded = [];
  const result = await ensureTallyDiscovery(
    { port: 9000 },
    {
      installation: async () => ({ exe: "known", pid: 1, loads: ["100000"] }),
      isRunning: async () => true,
      stop: async () => {},
      start: async () => {
        loaded = companies;
      },
      ready: async () => {},
      request: async (_url, { body }) =>
        new Response(
          xml(
            body.includes("Company on Disk") ? companies : loaded,
            body.includes("Company on Disk"),
          ),
        ),
    },
  );
  assert.deepEqual(result.company_scope, companies);
});

test("unsafe close, uncertain process and incomplete login never claim discovery readiness", async () => {
  for (const problem of ["unsafe-close", "uncertain", "login"]) {
    let starts = 0;
    await assert.rejects(
      ensureTallyDiscovery(
        { port: 9000 },
        {
          installation: async () => ({
            exe: "known",
            pid: 1,
            loads: ["100000"],
          }),
          isRunning: async () => (problem === "uncertain" ? null : true),
          stop: async () => {
            if (problem === "unsafe-close") throw new Error("save your work");
          },
          start: async () => {
            starts++;
          },
          ready: async () => {},
          request: async (_url, { body }) =>
            new Response(
              xml(
                body.includes("Company on Disk")
                  ? companies
                  : companies.slice(0, 2),
                body.includes("Company on Disk"),
              ),
            ),
        },
      ),
    );
    assert.equal(starts, problem === "login" ? 1 : 0);
  }
});

test("startup scans only numbered company directories with a native company marker", async () => {
  const entry = (name, type) => ({
    name,
    isDirectory: () => type === "dir",
    isFile: () => type === "file",
  });
  const paths = [];
  const result = await startupCompanies(
    "C:/Tally/tally.exe",
    ";Data = bad\r\nData = C:/Business Data\r\n",
    {
      list: async (path) => {
        paths.push(path);
        if (paths.length === 1)
          return [
            entry("100000", "dir"),
            entry("100001", "dir"),
            entry("backup", "dir"),
            entry("100002", "link"),
          ];
        return path.endsWith("100000")
          ? [entry("Company.1800", "file")]
          : [entry("not-company.txt", "file")];
      },
    },
  );
  assert.deepEqual(result, ["100000"]);
  assert.equal(paths.length, 3);
});
