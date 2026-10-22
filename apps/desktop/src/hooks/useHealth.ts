import { useEffect, useState } from "react";
import { api } from "../api/client";

/**
 * Poll /health. `error` is true when the backend is unreachable or reports no model.
 * Polls every 10s while errored (per brief) and on a slow heartbeat otherwise so a
 * model going away is noticed.
 */
export function useHealth() {
  const [model, setModel] = useState<string | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout>;

    const check = async () => {
      try {
        const h = await api.health();
        if (!alive) return;
        const ok = h.status === "ok" && !!h.model;
        setModel(h.model || null);
        setError(!ok);
        schedule(ok ? 30_000 : 10_000);
      } catch {
        if (!alive) return;
        setModel(null);
        setError(true);
        schedule(10_000);
      }
    };
    const schedule = (ms: number) => {
      timer = setTimeout(check, ms);
    };

    check();
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, []);

  return { model, error };
}
