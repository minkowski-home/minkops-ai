/**
 * Mock authenticated user for frontend development.
 * Replace with real session/auth API when backend is ready.
 */

import type { User } from "../types/user";

export const MOCK_USER: User = {
  id: "user-001",
  name: "Alex Reyes",
  email: "alex@acmecorp.com",
  avatarUrl: null,
  tenantId: "tenant-acme",
  tenantName: "Acme Corp",
  role: "admin"
};
