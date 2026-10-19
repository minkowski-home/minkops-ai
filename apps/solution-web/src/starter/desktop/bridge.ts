export interface NativeFile {
  path: string;
  content: string;
}
export interface NativeFolder {
  grantId: string;
  label: string;
  files: NativeFile[];
}
export interface DesktopStatus {
  discovery_archive_error?: string | null;
  version: string;
  update?: { state: 'downloading' | 'ready' | 'waiting' | 'error'; version?: string } | null;
  name: string;
  device: { id: string; tenant: string; owner_id: string } | null;
}
export interface DesktopBridge {
  version: number;
  schemaOnlyFolders?: boolean;
  discoveryPackages?: boolean;
  openTallyDiagnostics?(): Promise<void>;
  /** Companion 0.7.0+: sends a technical summary, or copies it when offline. */
  sendDiagnostics?(): Promise<{ reference?: string; copied?: boolean }>;
  status(): Promise<DesktopStatus>;
  checkUpdates?(): Promise<void>;
  restartForUpdate?(): Promise<boolean>;
  connect(tenant: string): Promise<{ id: string }>;
  disconnect(): Promise<void>;
  saveCatalog?(tenant: string, discoveryId: string): Promise<boolean>;
  pickFolder(tenant: string, sourceId?: string, schemaOnly?: boolean): Promise<NativeFolder | null>;
  bindFolder(tenant: string, sourceId: string, grantId: string): Promise<void>;
  refreshFolder(tenant: string, sourceId: string): Promise<NativeFile[]>;
}
declare global {
  interface Window {
    minkopsDesktop?: DesktopBridge;
  }
}

export function desktopBridge() {
  return window.minkopsDesktop?.version === 1 ? window.minkopsDesktop : undefined;
}

/** Same-origin authenticated downloads also work inside the Windows shell. */
export async function downloadFile(path: string, filename: string) {
  if (!path.startsWith("/api/")) throw new Error("Invalid download path.");
  const response = await fetch(path, { credentials: "same-origin" });
  if (!response.ok) throw new Error("Could not download the exception sheet.");
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url; link.download = filename;
  document.body.append(link);
  link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10000);
}

export function nativeFilesForm(
  files: NativeFile[],
  label: string,
  sourceId?: string
): FormData {
  const form = new FormData();
  form.append("label", label);
  form.append("writable", "true");
  if (sourceId) form.append("source_id", sourceId);
  form.append("paths", JSON.stringify(files.map((f) => f.path)));
  for (const file of files) {
    const content = Uint8Array.from(atob(file.content), (c) => c.charCodeAt(0));
    form.append("files", new Blob([content]), file.path.split("/").at(-1));
  }
  return form;
}
