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
  version: string;
  name: string;
  device: { id: string; tenant: string; owner_id: string } | null;
}
export interface DesktopBridge {
  version: number;
  status(): Promise<DesktopStatus>;
  connect(tenant: string): Promise<{ id: string }>;
  disconnect(): Promise<void>;
  saveCatalog?(tenant: string, discoveryId: string): Promise<boolean>;
  pickFolder(tenant: string, sourceId?: string): Promise<NativeFolder | null>;
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
