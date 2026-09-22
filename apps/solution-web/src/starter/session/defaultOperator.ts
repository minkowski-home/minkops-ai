import type { User } from "../types/user";

/** Local session fallback until the shared auth API is connected. */
export const DEFAULT_OPERATOR: User = {
  id: "local-operator",
  name: "Operator",
  email: "operator@example.com",
  avatarUrl: null,
  tenantId: "starter-workspace",
  tenantName: "Starter workspace",
  role: "operator"
};
