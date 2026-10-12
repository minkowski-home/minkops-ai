import type { Source } from './types';

export function eligibleFiles(sources: Source[]) {
  return sources.flatMap(source => source.files.filter(file => /\.(pdf|png|jpe?g|webp)$/i.test(file.path))
    .map(file => ({ ...file, key: `${source.id}:${file.path}` })));
}

/** Missing/invalid preferences use the initial choice; an explicit [] means none. */
export function restoreSelection(sources: Source[], raw: string | null): string[] {
  let saved: string[] | null = null;
  try {
    const value: unknown = raw === null ? null : JSON.parse(raw);
    if (Array.isArray(value) && value.every(key => typeof key === 'string')) saved = value;
  } catch { /* Ignore obsolete preference formats. */ }
  return eligibleFiles(sources).filter(file => saved === null || saved.includes(file.key)).map(file => file.id);
}

export function selectionKeys(sources: Source[], selected: string[]) {
  return eligibleFiles(sources).filter(file => selected.includes(file.id)).map(file => file.key);
}

/** Source refresh can rotate IDs. Reconcile by source/path, never silently add bills. */
export function reconcileSelection(previous: Source[], next: Source[], selected: string[]) {
  return restoreSelection(next, JSON.stringify(selectionKeys(previous, selected)));
}
