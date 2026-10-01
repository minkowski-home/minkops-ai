export interface LocalFile {
  getFile(): Promise<Blob>;
  createWritable(): Promise<{ write(blob: Blob): Promise<void>; close(): Promise<void>; abort(): Promise<void> }>;
}

export async function sha256(blob: Blob): Promise<string> {
  const bytes = await crypto.subtle.digest('SHA-256', await blob.arrayBuffer());
  return Array.from(new Uint8Array(bytes), (v) => v.toString(16).padStart(2, '0')).join('');
}

/** A retry accepts an already-saved result; it never replays an append.
 * Chrome commits its temporary file at close. The original stays in IndexedDB
 * until the server acknowledges the saved bytes, supporting interrupted writes.
 */
export async function commitLocalWrite(file: LocalFile, approved: Blob, before: string, after: string,
  backup: (blob: Blob) => Promise<void>): Promise<Blob> {
  if (await sha256(approved) !== after) throw new Error('Approved workbook failed its integrity check.');
  const current = await file.getFile();
  const currentHash = await sha256(current);
  if (currentHash === after) return current;
  if (currentHash !== before) throw new Error('The local workbook changed. Refresh discovery before applying these entries.');
  await backup(current);
  const writer = await file.createWritable();
  try {
    // Recheck after acquiring the file stream to catch intervening edits.
    if (await sha256(await file.getFile()) !== before) throw new Error('The local workbook changed before saving.');
    await writer.write(approved);
    await writer.close();
  } catch (error) {
    await writer.abort().catch(() => {});
    throw error;
  }
  const saved = await file.getFile();
  if (await sha256(saved) !== after) throw new Error('Local save could not be verified. Keep this run open and reconnect the folder.');
  return saved;
}
