"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { callRoute, extractRows } from "./appClient";
import { isInvalid, type Row, type SheetField } from "./sheets";
import type { SheetSpec } from "./uiSpec";

export type SaveState = "loading" | "saved" | "saving" | "error";

const uid = () => Math.random().toString(36).slice(2);
const CID = "__cid";
const ERR = "__error"; // set on a row the app has not accepted yet; never sent

const hasValue = (fields: SheetField[], row: Row) =>
  fields.some((f) => row[f.key] !== null && row[f.key] !== undefined && row[f.key] !== "" && row[f.key] !== false);

/**
 * Rows of an app, read and written ONLY through the app's own routes (via the gateway).
 * The grid edits a local copy; every change becomes list/create/update/delete calls, applied in order.
 */
export function useRemoteRows(appId: string, spec: SheetSpec) {
  const fields = spec.columns as SheetField[];
  const [rows, setRowsState] = useState<Row[]>([]);
  const [state, setState] = useState<SaveState>("loading");
  const [error, setError] = useState<string | null>(null);
  const [skipped, setSkipped] = useState(0);
  const rowsRef = useRef<Row[]>([]);
  const queue = useRef<Promise<void>>(Promise.resolve());
  const pending = useRef(0);
  const inflight = useRef(new Set<string>()); // client ids whose create call has not returned yet
  const specRef = useRef(spec);
  specRef.current = spec;

  const put = (next: Row[]) => {
    rowsRef.current = next;
    setRowsState(next);
  };

  const load = useCallback(async () => {
    setState("loading");
    try {
      const data = await callRoute(appId, specRef.current.list);
      put(extractRows(data, specRef.current.rows_path).map((r) => ({ ...r, [CID]: uid() })));
      setError(null);
      setState("saved");
    } catch (e: any) {
      setError(e.message);
      setState("error");
    }
  }, [appId]);

  useEffect(() => { void load(); }, [load]);

  // Rows change behind the grid's back (the agent adds data, another tab edits): pick them up quietly every few
  // seconds and on focus, but only when nothing is being saved and only if something actually differs.
  const misses = useRef(0);
  const sync = useCallback(async () => {
    if (pending.current > 0 || inflight.current.size > 0 || misses.current >= 3) return;
    try {
      const spec = specRef.current;
      const remote = extractRows(await callRoute(appId, spec.list), spec.rows_path);
      if (pending.current > 0 || inflight.current.size > 0) return; // a save started while we were reading
      misses.current = 0;
      const key = spec.key;
      const plain = (r: Row) => { const { [CID]: _c, [ERR]: _e, ...rest } = r; return JSON.stringify(rest); };
      const local = rowsRef.current;
      const saved = local.filter((r) => r[key] !== undefined);
      if (remote.length === saved.length && remote.every((r, i) => plain(r) === plain(saved[i]))) return;
      const cidByKey = new Map(saved.map((r) => [String(r[key]), r[CID] as string]));
      const merged = remote.map((r) => ({ ...r, [CID]: cidByKey.get(String(r[key])) ?? uid() }));
      put([...merged, ...local.filter((r) => r[key] === undefined)]); // keep drafts and the blank row
    } catch {
      misses.current++;
    }
  }, [appId]);

  useEffect(() => {
    const tick = () => { if (document.visibilityState === "visible") void sync(); };
    const onFocus = () => { misses.current = 0; tick(); };
    const id = window.setInterval(tick, 4000);
    window.addEventListener("focus", onFocus);
    return () => { window.clearInterval(id); window.removeEventListener("focus", onFocus); };
  }, [sync]);

  const run = (job: () => Promise<void>, reloadOnError = true) => {
    pending.current++;
    setState("saving");
    queue.current = queue.current.then(job).catch((e: any) => {
      setError(e.message);
      setState("error");
      return reloadOnError ? load() : undefined;
    }).finally(() => {
      if (--pending.current === 0) setState((s) => (s === "error" ? s : "saved"));
    });
  };

  /** Called by the grid with the full next rows array; diffed against the current one. */
  const setRows = (next: Row[]) => {
    const prev = rowsRef.current;
    const withCid = next.map((r) => (r[CID] ? r : { ...r, [CID]: uid() }));
    const key = specRef.current.key;
    const prevByCid = new Map(prev.map((r) => [r[CID] as string, r]));
    const nextCids = new Set(withCid.map((r) => r[CID] as string));
    put(withCid);

    const strip = (r: Row) => {
      const { [CID]: _c, [ERR]: _e, [key]: _k, ...rest } = r;
      return rest;
    };
    const valid = (r: Row) => !fields.some((f) => isInvalid(f, r[f.key]));

    let invalid = 0;
    const creates = withCid.filter((r) => {
      if (r[key] !== undefined || inflight.current.has(r[CID] as string)) return false;
      if (!hasValue(fields, r)) return false;
      if (!valid(r)) { invalid++; return false; }
      return true;
    });
    const updates = withCid.filter((r) => {
      const before = prevByCid.get(r[CID] as string);
      if (r[key] === undefined || !before) return false; // rows still being created are reconciled after
      if (JSON.stringify(strip(before)) === JSON.stringify(strip(r))) return false;
      if (!valid(r)) { invalid++; return false; }
      return true;
    });
    const deletes = prev.filter((r) => r[key] !== undefined && !nextCids.has(r[CID] as string));
    setSkipped(invalid);

    if (creates.length) {
      creates.forEach((r) => inflight.current.add(r[CID] as string));
      run(async () => {
        const cids = new Set(creates.map((r) => r[CID] as string));
        try {
          const body = creates.length === 1 ? strip(creates[0]) : { items: creates.map(strip) };
          const res = await callRoute(appId, specRef.current.create!, { body });
          const stored = extractRows(res, specRef.current.rows_path);
          const single = creates.length === 1 && !Array.isArray(res) && stored.length === 0 ? [res as Row] : stored;
          const sent = new Map(creates.map((r) => [r[CID] as string, JSON.stringify(strip(r))]));
          const edited: Row[] = [];
          const server = new Map(creates.map((r, i) => [r[CID] as string, single[i]]));
          setError(null);
          put(rowsRef.current.map((r) => {
            const s = server.get(r[CID] as string);
            if (!s || s[key] === undefined) return r;
            // Take the app's version of the row (ids, defaults, timestamps) but keep what the user typed meanwhile.
            const { [ERR]: _e, ...clean } = r;
            const merged = { ...s, ...clean, [key]: s[key] };
            if (JSON.stringify(strip(r)) !== sent.get(r[CID] as string)) edited.push(merged);
            return merged;
          }));
          // The user kept typing while the create was in flight: push those edits now.
          for (const r of edited) {
            if (specRef.current.update) await callRoute(appId, specRef.current.update, { row: r, body: strip(r) });
          }
        } catch (e: any) {
          // The app refused (usually a required field is still empty). Keep the row as a draft with the reason;
          // the next edit retries it. Never reload here: that would throw away what the user typed.
          const message = e?.message ?? String(e);
          put(rowsRef.current.map((r) => (cids.has(r[CID] as string) ? { ...r, [ERR]: message } : r)));
          setError(`Not saved yet: ${message}`);
          setState("error");
        } finally {
          cids.forEach((c) => inflight.current.delete(c));
        }
      }, false);
    }
    for (const r of updates) {
      run(async () => {
        const current = rowsRef.current.find((x) => x[CID] === r[CID]) ?? r;
        if (current[key] === undefined) return;
        await callRoute(appId, specRef.current.update!, { row: current, body: strip(current) });
      });
    }
    for (const r of deletes) {
      run(async () => { await callRoute(appId, specRef.current.delete!, { row: r }); });
    }
  };

  const drafts = rows.filter((r) => r[ERR]).length;
  return { rows, setRows, state, error, skipped, drafts, reload: load, canEdit: !!spec.create };
}
