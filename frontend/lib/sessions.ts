"use client";

import { useCallback, useEffect, useRef, useState } from "react";

/**
 * A session is one chat thread. Each thread gets its own sandbox, but all sessions of the user share one
 * home volume, so files outlive and cross sessions.
 *
 * The index lives in SQLite on the agent service (so it survives a new browser or a cleared cache);
 * localStorage is only a fallback while the service is unreachable.
 */
export interface Session {
  id: string;
  title: string;
  createdAt: number;
  sandboxId?: string | null;
}

const LIST_KEY = "workbench.sessions.v2";
const ACTIVE_KEY = "workbench.activeSession.v2";

const read = <T,>(key: string, fallback: T): T => {
  try {
    const raw = window.localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
};
const write = (key: string, value: unknown) => {
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {}
};

const fresh = (): Session => ({ id: crypto.randomUUID(), title: "New session", createdAt: Date.now() });

const api = {
  list: async (): Promise<Session[] | null> => {
    try {
      const r = await fetch("/api/sessions", { cache: "no-store" });
      return r.ok ? ((await r.json()) as Session[]) : null;
    } catch {
      return null;
    }
  },
  put: (s: Session) =>
    fetch(`/api/sessions/${s.id}`, {
      method: "PUT",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ title: s.title, sandbox_id: s.sandboxId ?? null, created_at: s.createdAt }),
    }).catch(() => {}),
  remove: (id: string) => fetch(`/api/sessions/${id}`, { method: "DELETE" }).catch(() => {}),
};

export function useSessionStore() {
  const [sessions, setSessions] = useState<Session[] | null>(null);
  const [activeId, setActiveId] = useState<string | null>(null);
  const synced = useRef<Record<string, string>>({}); // what the server already has, to avoid echo writes

  useEffect(() => {
    let live = true;
    (async () => {
      let list = (await api.list()) ?? read<Session[]>(LIST_KEY, []);
      // Sessions that only exist in this browser (created before the index was server-side) are adopted.
      const local = read<Session[]>(LIST_KEY, []).filter((l) => !list.some((s) => s.id === l.id));
      list = [...list, ...local].sort((a, b) => b.createdAt - a.createdAt);
      const f = list.length ? null : fresh();
      if (f) list = [f];
      if (!live) return;
      list.forEach((s) => (synced.current[s.id] = JSON.stringify([s.title, s.sandboxId ?? null])));
      if (f) void api.put(f);
      local.forEach((s) => void api.put(s));
      const active = read<string | null>(ACTIVE_KEY, null);
      setSessions(list);
      setActiveId(list.some((s) => s.id === active) ? active : list[0].id);
    })();
    return () => { live = false; };
  }, []);

  useEffect(() => { if (sessions) write(LIST_KEY, sessions); }, [sessions]);
  useEffect(() => { if (activeId) write(ACTIVE_KEY, activeId); }, [activeId]);

  // Push title / sandbox changes to the server index.
  useEffect(() => {
    sessions?.forEach((s) => {
      const sig = JSON.stringify([s.title, s.sandboxId ?? null]);
      if (synced.current[s.id] !== sig) {
        synced.current[s.id] = sig;
        void api.put(s);
      }
    });
  }, [sessions]);

  const create = useCallback(() => {
    const s = fresh();
    synced.current[s.id] = JSON.stringify([s.title, null]);
    void api.put(s);
    setSessions((l) => [s, ...(l ?? [])]);
    setActiveId(s.id);
  }, []);

  const update = useCallback((id: string, patch: Partial<Session>) => {
    setSessions((l) => {
      if (!l) return l;
      const cur = l.find((s) => s.id === id);
      if (!cur || Object.entries(patch).every(([k, v]) => (cur as any)[k] === v)) return l; // no-op: avoid loops
      return l.map((s) => (s.id === id ? { ...s, ...patch } : s));
    });
  }, []);

  const remove = useCallback((id: string) => {
    void api.remove(id);
    setSessions((l) => {
      const rest = (l ?? []).filter((s) => s.id !== id);
      const next = rest.length ? rest : [fresh()];
      setActiveId((a) => (a === id ? next[0].id : a));
      return next;
    });
  }, []);

  return { sessions, activeId, select: setActiveId, create, update, remove };
}
