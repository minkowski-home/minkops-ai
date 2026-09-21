/**
 * Mock authenticated user for frontend development.
 * Replace with real session/auth API when backend is ready.
 */

import type { User } from "../types/user";

export const MOCK_USER: User = {
  id: "user-001",
  name: "Workspace Operator",
  email: "operator@example.com",
  avatarUrl: null,
  tenantId: "tenant-starter",
  tenantName: "Starter workspace",
  role: "admin"
};
