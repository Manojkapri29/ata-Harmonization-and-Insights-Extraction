import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";
import type { Task } from "./types";

/** Load data with loading / error / reload handling. */
export function useAsync<T>(fn: () => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T | undefined>(undefined);
  const [error, setError] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const fnRef = useRef(fn);
  fnRef.current = fn;

  const reload = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    setError("");
    try {
      setData(await fnRef.current());
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return { data, error, loading, reload, setData };
}

/** Poll a background task until it completes or fails. */
export function useTask(onDone?: (t: Task) => void) {
  const [task, setTask] = useState<Task | null>(null);
  const timer = useRef<number | undefined>(undefined);
  const doneRef = useRef(onDone);
  doneRef.current = onDone;

  const stop = () => window.clearTimeout(timer.current);

  const track = useCallback((t: Task) => {
    stop();
    setTask(t);
    const poll = async () => {
      try {
        const next = await api.task(t.id);
        setTask(next);
        if (next.status === "completed" || next.status === "failed") {
          doneRef.current?.(next);
          return;
        }
      } catch {
        /* keep polling through brief network hiccups */
      }
      timer.current = window.setTimeout(poll, 800);
    };
    if (t.status === "completed" || t.status === "failed") doneRef.current?.(t);
    else timer.current = window.setTimeout(poll, 500);
  }, []);

  useEffect(() => stop, []);
  const running = task !== null && (task.status === "queued" || task.status === "running");
  return { task, track, running, clear: () => setTask(null) };
}

export function useDebounced<T>(value: T, ms = 350) {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = window.setTimeout(() => setV(value), ms);
    return () => window.clearTimeout(t);
  }, [value, ms]);
  return v;
}
