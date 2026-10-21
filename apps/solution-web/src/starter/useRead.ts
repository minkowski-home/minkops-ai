import { useCallback, useEffect, useRef, useSyncExternalStore } from "react";
import { api } from "./api";
import { readKey, reads } from "./readCache";

/** Shared GET subscription. Cached results remain visible during revalidation. */
export function useRead<T>(scope: string, path: string, options: {
  enabled?: boolean;
  initial?: T;
  interval?: number | ((data: T | undefined) => number);
} = {}) {
  const key = readKey(scope, path);
  const latest = useRef(options); latest.current = options;
  const enabled = options.enabled !== false;
  const subscribe = useCallback((listener: () => void) => reads.subscribe(key, listener), [key]);
  const snapshot = useCallback(() => reads.snapshot<T>(key), [key]);
  const value = useSyncExternalStore(subscribe, snapshot, snapshot);
  const refresh = useCallback(() => reads.refresh<T>(key, signal => api<T>(path, { signal })), [key, path]);
  const setData = useCallback((data: T | ((current: T | undefined) => T)) => {
    reads.put(key, typeof data === "function" ? (data as (current: T | undefined) => T)(reads.snapshot<T>(key).data) : data);
  }, [key]);
  useEffect(() => {
    if (!enabled) return;
    let active = true, timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      await refresh();
      if (!active) return;
      const interval = latest.current.interval;
      const delay = typeof interval === "function" ? interval(reads.snapshot<T>(key).data) : interval;
      if (delay) timer = setTimeout(() => {
        if (document.visibilityState === "hidden") timer = setTimeout(() => void poll(), Math.max(delay, 10000));
        else void poll();
      }, delay);
    };
    void poll();
    const visible = () => { if (document.visibilityState === "visible") void refresh(); };
    document.addEventListener("visibilitychange", visible);
    return () => { active = false; clearTimeout(timer); document.removeEventListener("visibilitychange", visible); };
  }, [enabled, key, refresh]);
  return { ...value, data: value.data === undefined && !value.error ? options.initial : value.data, loading: enabled && value.data === undefined && options.initial === undefined,
    refresh, setData };
}
