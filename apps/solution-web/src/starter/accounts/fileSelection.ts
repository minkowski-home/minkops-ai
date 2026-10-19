import type { Source } from './types';

const BILL_FILES = /\.(pdf|png|jpe?g|webp)$/i;

export function eligibleFiles(sources: Source[], pattern = BILL_FILES) {
  return sources.flatMap(source => source.files.filter(file => pattern.test(file.path))
    .map(file => ({ ...file, key: `${source.id}:${file.path}` })));
}

/** Missing/invalid preferences use the initial choice; an explicit [] means none. */
export function restoreSelection(sources: Source[], raw: string | null, pattern = BILL_FILES): string[] {
  let saved: string[] | null = null;
  try {
    const value: unknown = raw === null ? null : JSON.parse(raw);
    if (Array.isArray(value) && value.every(key => typeof key === 'string')) saved = value;
  } catch { /* Ignore obsolete preference formats. */ }
  return eligibleFiles(sources, pattern).filter(file => saved === null || saved.includes(file.key)).map(file => file.id);
}

export function selectionKeys(sources: Source[], selected: string[], pattern = BILL_FILES) {
  return eligibleFiles(sources, pattern).filter(file => selected.includes(file.id)).map(file => file.key);
}

/** Source refresh can rotate IDs. Reconcile by source/path, never silently add bills. */
export function reconcileSelection(previous: Source[], next: Source[], selected: string[], pattern = BILL_FILES) {
  return restoreSelection(next, JSON.stringify(selectionKeys(previous, selected, pattern)), pattern);
}
