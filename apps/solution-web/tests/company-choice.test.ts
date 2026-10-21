import test from "node:test";
import assert from "node:assert/strict";
import { initialLockedCompany, type DiscoveredCompany } from "../src/starter/accounts/companyChoice.ts";

const companies: DiscoveredCompany[] = [
  { company: "Sachin Infra (2025-26)", company_guid: "a" },
  { company: "Sachin Infra (2026-27)", company_guid: "b" },
];

test("the locked company is never silently the first of several", () => {
  assert.equal(initialLockedCompany(companies, undefined), "");
  assert.equal(initialLockedCompany(companies.slice(0, 1), undefined), "a");
  assert.equal(initialLockedCompany(companies, "b"), "b");
  assert.equal(initialLockedCompany(companies.slice(0, 1), "gone"), "gone", "a lost choice never falls back");
});
