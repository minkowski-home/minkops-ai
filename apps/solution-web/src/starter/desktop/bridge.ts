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
  update?: { state: 'downloading' | 'ready' | 'waiting' | 'error'; version?: string } | null;
  name: string;
  device: { id: string; tenant: string; owner_id: string } | null;
}
export interface DesktopBridge {
  version: number;
  openTallyDiagnostics?(): Promise<void>;
  /** Companion 0.7.0+: sends a technical summary, or copies it when offline. */
  sendDiagnostics?(): Promise<{ reference?: string; copied?: boolean }>;
  status(): Promise<DesktopStatus>;
  checkUpdates?(): Promise<void>;
  restartForUpdate?(): Promise<boolean>;
  connect(tenant: string): Promise<{ id: string }>;
  disconnect(): Promise<void>;
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
