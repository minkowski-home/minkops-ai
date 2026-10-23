/** Bounded, memory-only GET state. Decisions always go through the server. */
export interface ReadSnapshot<T> {
  data: T | undefined;
  error: string;
  fetching: boolean;
  updatedAt: number;
}
type Loader = (signal: AbortSignal) => Promise<unknown>;
interface Entry {
  value: ReadSnapshot<unknown>;
  listeners: Set<() => void>;
  generation: number;
  controller?: AbortController;
  pending?: Promise<void>;
  loader?: Loader;
}
const EMPTY: ReadSnapshot<never> = { data: undefined, error: "", fetching: false, updatedAt: 0 };
export const readKey = (scope: string, path: string) => JSON.stringify([scope, path]);

export class ReadCache {
  private entries = new Map<string, Entry>();
  private limit: number;
  constructor(limit = 100) { this.limit = limit; }

  snapshot<T>(key: string): ReadSnapshot<T> {
    return (this.entries.get(key)?.value ?? EMPTY) as ReadSnapshot<T>;
  }
  private entry(key: string): Entry {
    let entry = this.entries.get(key);
    if (!entry) {
      entry = { value: EMPTY, listeners: new Set(), generation: 0 };
      this.entries.set(key, entry);
      for (const [oldKey, old] of this.entries) {
        if (this.entries.size <= this.limit) break;
        if (oldKey !== key && !old.listeners.size) { this.cancel(old); this.entries.delete(oldKey); }
      }
    }
    return entry;
  }
  private publish(entry: Entry, value: ReadSnapshot<unknown>) {
    entry.value = value;
    entry.listeners.forEach(listener => listener());
  }
  private cancel(entry: Entry) {
    entry.generation++;
    entry.controller?.abort(); entry.controller = undefined; entry.pending = undefined;
  }
  subscribe(key: string, listener: () => void) {
    const entry = this.entry(key); entry.listeners.add(listener);
    return () => {
      entry.listeners.delete(listener);
      if (!entry.listeners.size && entry.pending) {
        this.cancel(entry); this.publish(entry, { ...entry.value, fetching: false });
      }
    };
  }
  refresh<T>(key: string, loader: (signal: AbortSignal) => Promise<T>): Promise<void> {
    const entry = this.entry(key); entry.loader = loader;
    if (entry.pending) return entry.pending;
    const generation = entry.generation;
    const controller = new AbortController(); entry.controller = controller;
    this.publish(entry, { ...entry.value, fetching: true });
    // Invoke immediately so callers joining this turn see the same operation.
    const pending = loader(controller.signal).then(data => {
      if (entry.generation === generation && !controller.signal.aborted)
        this.publish(entry, { data, error: "", fetching: false, updatedAt: Date.now() });
    }).catch(error => {
      if (entry.generation === generation && !controller.signal.aborted) {
        const inaccessible = error && typeof error === "object" && "status" in error && [401,403,404].includes(Number(error.status));
        this.publish(entry, { ...(inaccessible ? EMPTY : entry.value), fetching: false,
          error: error instanceof Error ? error.message : "Could not refresh." });
      }
    }).finally(() => {
      if (entry.generation === generation) { entry.pending = undefined; entry.controller = undefined; }
    });
    entry.pending = pending;
    return pending;
  }
  /** A committed response fences reads that started before the decision. */
  put<T>(key: string, data: T) {
    const entry = this.entry(key); this.cancel(entry);
    this.publish(entry, { data, error: "", fetching: false, updatedAt: Date.now() });
  }
  invalidate(scope: string, matches: (path: string) => boolean = () => true) {
    for (const [key, entry] of this.entries) {
      const [entryScope, path] = JSON.parse(key) as [string, string];
      if (entryScope !== scope || !matches(path)) continue;
      this.cancel(entry); this.publish(entry, { ...entry.value, updatedAt: 0, fetching: false });
      if (entry.listeners.size && entry.loader) void this.refresh(key, entry.loader);
    }
  }
  clear() {
    for (const [key, entry] of this.entries) {
      this.cancel(entry); this.publish(entry, EMPTY);
      if (!entry.listeners.size) this.entries.delete(key);
    }
  }
}

export const reads = new ReadCache();
