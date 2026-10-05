import { api } from '../api';
import { commitLocalWrite } from './localWrites';
import type { LocalFile } from './localWrites';
import type { Source, WritePlan } from './types';
import { desktopBridge, nativeFilesForm } from '../desktop/bridge';

export interface Directory {
  kind: 'directory'; name: string;
  entries(): AsyncIterableIterator<[string, Directory | FileHandle]>;
  getDirectoryHandle(name: string): Promise<Directory>;
  getFileHandle(name: string): Promise<FileHandle>;
  queryPermission(options: { mode: 'readwrite' }): Promise<string>;
  requestPermission(options: { mode: 'readwrite' }): Promise<string>;
}
interface FileHandle extends LocalFile { kind: 'file'; name: string; getFile(): Promise<File> }
type PickerWindow = Window & { showDirectoryPicker?: (options: { mode: 'readwrite' }) => Promise<Directory> };

function database(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open('minkops-local-sources-v1', 1);
    request.onupgradeneeded = () => request.result.createObjectStore('bindings');
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

export async function localValue<T>(key: string): Promise<T | undefined> {
  const db = await database();
  try { return await new Promise((resolve, reject) => {
    const request = db.transaction('bindings').objectStore('bindings').get(key);
    request.onsuccess = () => resolve(request.result as T | undefined);
    request.onerror = () => reject(request.error);
  }); } finally { db.close(); }
}

async function saveLocal(key: string, value: unknown): Promise<void> {
  const db = await database();
  try { await new Promise<void>((resolve, reject) => {
    const tx = db.transaction('bindings', 'readwrite');
    if (value === undefined) tx.objectStore('bindings').delete(key);
    else tx.objectStore('bindings').put(value, key);
    tx.oncomplete = () => resolve(); tx.onerror = () => reject(tx.error);
  }); } finally { db.close(); }
}

export function supportsLocalFolder() { return Boolean(desktopBridge() || (window as PickerWindow).showDirectoryPicker); }
const bindingKey = (tenant: string, source: string) => `${tenant}:folder:${source}`;

interface RemoteSource { source_id: string; device_id: string }
interface RemoteJob { id: string; state: string; error?: string }
async function connectedSource(tenant: string, sourceId: string) {
  const sources = await api<RemoteSource[]>(`/api/tenants/${tenant}/desktop/sources`);
  return sources.find((s) => s.source_id === sourceId);
}
async function onConnectedPC(tenant: string, deviceId: string, operation: string, input: Record<string, string>, csrf: string) {
  const base = `/api/tenants/${tenant}/desktop/jobs`;
  let job = await api<RemoteJob>(base, { method: 'POST', body: JSON.stringify({
    device_id: deviceId, operation, input, request_key: crypto.randomUUID(),
  }) }, csrf);
  // The server owns the job. Leaving the page does not cancel native work.
  const deadline = Date.now() + 120000;
  while (['queued', 'executing'].includes(job.state) && Date.now() < deadline) {
    await new Promise((resolve) => setTimeout(resolve, 1500));
    job = await api<RemoteJob>(`${base}/${job.id}`);
  }
  if (job.state === 'failed') throw new Error(job.error || 'This PC needs attention.');
  if (job.state !== 'completed') throw new Error('Waiting for your PC. Keep Minkops running there, then return to this task.');
}

export async function chooseFolder(tenant: string, csrf: string, existing?: Source): Promise<Source> {
  const native = desktopBridge();
  if (native) {
    const chosen = await native.pickFolder(tenant, existing?.id);
    if (!chosen) throw new Error('Folder selection cancelled.');
    const source = await api<Source>(`/api/tenants/${tenant}/accounts/sources`, { method: 'POST',
      body: nativeFilesForm(chosen.files, chosen.label, existing?.id) }, csrf);
    await native.bindFolder(tenant, source.id, chosen.grantId);
    return source;
  }
  const picker = (window as PickerWindow).showDirectoryPicker;
  if (!picker) throw new Error('Use Chrome or Edge to connect a local folder for in-place Excel edits.');
  const folder = await picker.call(window, { mode: 'readwrite' });
  if (existing) {
    // Rebinding a source to an unrelated directory could overwrite the wrong
    // workbook. Reconnection is restricted to the original directory handle.
    const previous = await localValue<Directory & { isSameEntry?: (other: Directory) => Promise<boolean> }>(bindingKey(tenant, existing.id));
    if (previous?.isSameEntry && !await previous.isSameEntry(folder)) throw new Error('Choose the original source folder, or connect this folder as a new source.');
  }
  const uploaded = await syncFolder(tenant, csrf, folder, existing?.id);
  await saveLocal(bindingKey(tenant, uploaded.id), folder);
  return uploaded;
}

async function inventory(folder: Directory, path = '', result: { path: string; file: File }[] = []) {
  for await (const [name, handle] of folder.entries()) {
    // Explicit mock policy excludes real-client samples, evaluation answers and
    // hidden files. Other file types are reported by the UI as unsupported.
    if (name.startsWith('.') || ['ground_truth', 'ground-truth', 'pr-infra-sample-bills'].includes(name)) continue;
    const relative = path ? `${path}/${name}` : name;
    if (handle.kind === 'directory') await inventory(handle, relative, result);
    else if (/\.(xlsx|pdf|png|jpe?g|webp)$/i.test(name)) result.push({ path: relative, file: await handle.getFile() });
    if (result.length > 100) throw new Error('This folder contains more than 100 supported files. Select a narrower folder.');
  }
  return result;
}

async function syncFolder(tenant: string, csrf: string, folder: Directory, sourceId?: string): Promise<Source> {
  const entries = await inventory(folder);
  if (!entries.length) throw new Error('No supported Excel, PDF or image files were found in this folder.');
  const form = new FormData();
  form.append('label', folder.name); form.append('writable', 'true');
  if (sourceId) form.append('source_id', sourceId);
  form.append('paths', JSON.stringify(entries.map((f) => f.path)));
  entries.forEach((f) => form.append('files', f.file));
  return api<Source>(`/api/tenants/${tenant}/accounts/sources`, { method: 'POST', body: form }, csrf);
}

export async function refreshFolder(tenant: string, source: Source, csrf: string): Promise<Source> {
  const remote = await connectedSource(tenant, source.id);
  if (remote) {
    await onConnectedPC(tenant, remote.device_id, 'files.refresh', { source_id: source.id }, csrf);
    const sources = await api<Source[]>(`/api/tenants/${tenant}/accounts/sources`);
    const updated = sources.find((s) => s.id === source.id);
    if (!updated) throw new Error('This source is no longer available.');
    return updated;
  }
  const native = desktopBridge();
  if (native) return api<Source>(`/api/tenants/${tenant}/accounts/sources`, { method: 'POST',
    body: nativeFilesForm(await native.refreshFolder(tenant, source.id), source.label, source.id) }, csrf);
  const folder = await localValue<Directory>(bindingKey(tenant, source.id));
  if (!folder) throw new Error('Reconnect the original local folder on this browser.');
  if (await folder.queryPermission({ mode: 'readwrite' }) !== 'granted' && await folder.requestPermission({ mode: 'readwrite' }) !== 'granted') throw new Error('Folder permission is required.');
  return syncFolder(tenant, csrf, folder, source.id);
}

export async function applyLocalPlan(tenant: string, runId: string, write: WritePlan, csrf: string): Promise<void> {
  const remote = await connectedSource(tenant, write.source_id);
  if (remote) {
    await onConnectedPC(tenant, remote.device_id, 'accounts.save', { run_id: runId, write_id: write.id }, csrf);
    return;
  }
  const native = desktopBridge();
  if (native) throw new Error('Reconnect the original folder on this PC before resuming saves.');
  const folder = await localValue<Directory>(bindingKey(tenant, write.source_id));
  if (!folder) throw new Error('Reconnect the original local folder to finish the approved entries.');
  if (await folder.queryPermission({ mode: 'readwrite' }) !== 'granted' && await folder.requestPermission({ mode: 'readwrite' }) !== 'granted') throw new Error('Local write permission is required. Select Resume local writes.');
  const parts = write.path.split('/');
  if (parts.some((p) => !p || p === '.' || p === '..' || p.includes('\\'))) throw new Error('Invalid local write path.');
  let directory = folder;
  for (const name of parts.slice(0, -1)) directory = await directory.getDirectoryHandle(name);
  const file = await directory.getFileHandle(parts[parts.length - 1]);
  const base = `/api/tenants/${tenant}/accounts/runs/${runId}/writes/${write.id}`;
  const response = await fetch(base + '/content', { credentials: 'same-origin' });
  if (!response.ok) throw new Error('Could not retrieve the approved Excel changes.');
  const approved = await response.blob();
  const execute = async () => {
    const saved = await commitLocalWrite(file, approved, write.before_sha256, write.after_sha256,
      (blob) => saveLocal(`${tenant}:backup:${write.id}`, blob));
    const form = new FormData(); form.append('file', saved, parts[parts.length - 1]);
    await api(base + '/verify', { method: 'POST', body: form }, csrf);
    await saveLocal(`${tenant}:backup:${write.id}`, undefined);
  };
  if (navigator.locks) await navigator.locks.request(`${tenant}:write:${write.source_id}:${write.path}`, execute);
  else await execute();
}
