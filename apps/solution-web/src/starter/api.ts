export interface Membership {
  slug: string;
  name: string;
  role: "admin" | "member";
}

export interface SessionUser {
  id: string;
  name: string;
  email: string;
  is_platform_admin: boolean;
  memberships: Membership[];
  csrf_token: string;
}

export interface SettingSpec {
  type: "boolean" | "string" | "integer";
  title?: string;
  description?: string;
  enum?: (string | number)[];
  "x-enabled-options"?: (string | number)[];
}

export interface ConfigSchema {
  type: "object";
  properties: Record<string, SettingSpec>;
}

export interface Employee {
  id: string;
  key: string;
  name: string;
  description: string;
  status: "active" | "inactive";
  config_schema: ConfigSchema;
  config_values: Record<string, string | number | boolean>;
  config_version: number;
}

export interface Workflow {
  id: string;
  key: string;
  name: string;
  description: string;
  status: "active" | "paused" | "planned";
  employee_ids: string[];
  config_schema: ConfigSchema;
  config_values: Record<string, string | number | boolean>;
  config_version: number;
}

export interface Task {
  id: string;
  workflow_id: string | null;
  title: string;
  status: "running" | "attention" | "handoff" | "completed" | "failed";
  progress: number;
  summary: string;
  created_at: string;
  updated_at: string;
}

export interface TaskEvent {
  id: number;
  event_type: string;
  summary: string;
  progress: number | null;
  created_at: string;
}

export interface Workspace {
  tenant: { slug: string; name: string };
  can_edit: boolean;
  employees: Employee[];
  workflows: Workflow[];
  tasks: Task[];
}

export async function api<T>(path: string, options: RequestInit = {}, csrf?: string): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body && !(options.body instanceof FormData)) headers.set("Content-Type", "application/json");
  if (csrf) headers.set("x-csrf-token", csrf);
  const response = await fetch(path, { ...options, headers, credentials: "same-origin" });
  const body = await response.json().catch(() => null) as (T & { detail?: string }) | null;
  if (!response.ok) {
    const detail = body?.detail;
    throw new Error(typeof detail === "string" ? detail : `Request failed (${response.status}).`);
  }
  return body as T;
}

export function tenantSlug(routeSlug: string): string {
  return routeSlug === "mock-client" ? "mock-tenant" : routeSlug;
}
