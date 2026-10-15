import test from "node:test";
import assert from "node:assert/strict";
import { initialLockedCompany, voucherTypeLaunch, type DiscoveredCompany } from "../src/starter/accounts/voucherTypes.ts";

const offer = (default_: string | null, ...names: string[]) => ({
  default: default_, candidates: names.map((name, i) => ({ name, guid: `${name}-guid`, used: i })),
});
const companies: DiscoveredCompany[] = [
  { company: "Sachin Infra (2025-26)", company_guid: "a", purchase_voucher_types: offer("Purchase GST-guid", "Purchase", "Purchase GST") },
  { company: "Sachin Infra (2026-27)", company_guid: "b", purchase_voucher_types: offer("Purchase-guid", "Purchase") },
  { company: "Old Catalog Co", company_guid: "c" },
  { company: "No Types Co", company_guid: "d", purchase_voucher_types: offer(null) },
];

test("a locked run asks only about its own company, preselecting the most used type", () => {
  const launch = voucherTypeLaunch(companies, "locked", "a", {});
  assert.deepEqual(launch.questions.map((q) => q.company_guid), ["a"]);
  assert.deepEqual(launch.choices, { a: "Purchase GST-guid" });
  assert.equal(launch.blocker, "");
  assert.deepEqual(voucherTypeLaunch(companies, "locked", "a", { a: "Purchase-guid" }).choices, { a: "Purchase-guid" });
  const cleared = voucherTypeLaunch(companies, "locked", "a", { a: "" });
  assert.deepEqual(cleared.choices, {});
  assert.match(cleared.blocker, /Choose the purchase voucher type/);
});

test("a locked run cannot start without a type the server will accept", () => {
  const tie = [{ ...companies[0], purchase_voucher_types: offer(null, "Purchase", "Purchase GST") }];
  assert.match(voucherTypeLaunch(tie, "locked", "a", {}).blocker, /Choose the purchase voucher type for Sachin Infra \(2025-26\)/);
  assert.match(voucherTypeLaunch(companies, "locked", "d", {}).blocker, /No Types Co has no active purchase voucher type/);
  assert.equal(voucherTypeLaunch(companies, "locked", "b", {}).questions.length, 0, "one type needs no question");
  assert.equal(voucherTypeLaunch(companies, "locked", "c", {}).blocker, "", "older catalogs defer to the server");
});

test("an inferred run asks about every ambiguous company and never blocks the others", () => {
  const launch = voucherTypeLaunch(companies, "infer", "", {});
  assert.deepEqual(launch.questions.map((q) => q.company_guid), ["a"]);
  assert.equal(launch.blocker, "");
  assert.match(launch.notice, /No Types Co/);
  assert.deepEqual(voucherTypeLaunch(companies, "infer", "", { zzz: "x" }).choices, { a: "Purchase GST-guid" });
});

test("the locked company is never silently the first of several", () => {
  assert.equal(initialLockedCompany(companies, undefined), "");
  assert.equal(initialLockedCompany(companies.slice(0, 1), undefined), "a");
  assert.equal(initialLockedCompany(companies, "b"), "b");
  assert.equal(initialLockedCompany(companies.slice(0, 1), "gone"), "gone", "a lost choice never falls back");
});
