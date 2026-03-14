/**
 * User / auth domain types.
 *
 * Backend contract for /api/auth/* endpoints.
 * The frontend only stores a minimal user object post-login;
 * full profile data lives server-side.
 */

export interface User {
  id: string;
  name: string;
  email: string;
  /** URL to the user's avatar image. null = use generated initials avatar. */
  avatarUrl: string | null;
  /** The tenant this user belongs to. */
  tenantId: string;
  tenantName: string;
  role: "admin" | "operator" | "viewer";
}
