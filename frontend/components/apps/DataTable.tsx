"use client";

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { callRoute, extractRows, parseClipboard } from "@/lib/appClient";
import type { Item, TableSpec } from "@/lib/uiSpec";

type Row = Record<string, unknown>;

function coerce(col: Item, raw: string): unknown {
  if (raw === "") return null;
  if (col.type === "number") {
    const n = Number(raw);
    return Number.isNaN(n) ? raw : n;
  }
  if (col.type === "boolean") return /^(true|1|yes|y)$/i.test(raw);
  return raw;
}

async function pool<T>(items: T[], size: number, fn: (item: T) => Promise<void>) {
  let i = 0;
  await Promise.all(
    Array.from({ length: Math.min(size, items.length) }, async () => {
      while (i < items.length) await fn(items[i++]);
    })
  );
}

export function DataTable({ appId, spec }: { appId: string; spec: TableSpec }) {
  const [rows, setRows] = useState<Row[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [draft, setDraft] = useState<Row>({});
  const gridRef = useRef<HTMLDivElement>(null);

  const columns = spec.columns;
  const editableCols = useMemo(() => columns.filter((c) => c.editable !== false && c.key !== spec.key), [columns, spec.key]);

  const load = useCallback(async () => {
    try {
      const data = await callRoute(appId, spec.list);
      setRows(extractRows(data, spec.rows_path));
      setError(null);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [appId, spec.list, spec.rows_path]);

  useEffect(() => {
    setLoading(true);
    load();
  }, [load]);

  const addRows = async (items: Row[]) => {
    if (!spec.create || items.length === 0) return;
    let done = 0;
    const failures: string[] = [];
    setStatus(`Saving 0/${items.length}…`);
    // Sequential on purpose: apps the agent writes often assign ids naively, and
    // concurrent inserts would collide. Row POSTs are cheap (no LLM involved).
    await pool(items, 1, async (item) => {
      try {
        await callRoute(appId, spec.create!, { body: item });
      } catch (e: any) {
        failures.push(e.message);
      }
      setStatus(`Saving ${++done}/${items.length}…`);
    });
    setStatus(
      failures.length
        ? `Saved ${items.length - failures.length}/${items.length}. First error: ${failures[0]}`
        : `Saved ${items.length} row${items.length === 1 ? "" : "s"}.`
    );
    await load();
  };

  const onPaste = (e: React.ClipboardEvent) => {
    const target = e.target as HTMLElement;
    if (target.tagName === "INPUT" && (target as HTMLInputElement).value) return; // normal paste into a filled cell
    const text = e.clipboardData.getData("text/plain");
    if (!text.trim()) return;
    e.preventDefault();
    let matrix = parseClipboard(text);
    // Drop a header row when it names our columns.
    const names = new Set(editableCols.flatMap((c) => [c.key.toLowerCase(), (c.label || "").toLowerCase()]));
    if (matrix.length > 1 && matrix[0].every((c) => names.has(c.toLowerCase()))) matrix = matrix.slice(1);
    const items = matrix.map((cells) => {
      const item: Row = {};
      editableCols.forEach((col, i) => {
        if (cells[i] !== undefined) item[col.key] = coerce(col, cells[i]);
      });
      return item;
    });
    void addRows(items);
  };

  const saveCell = async (row: Row, col: Item, raw: string) => {
    const next = { ...row, [col.key]: coerce(col, raw) };
    if (next[col.key] === row[col.key]) return;
    if (!spec.update) return;
    try {
      await callRoute(appId, spec.update, { row: next, body: next });
      setRows((rs) => rs.map((r) => (r[spec.key] === row[spec.key] ? next : r)));
      setStatus(null);
    } catch (e: any) {
      setStatus(`Update failed: ${e.message}`);
      await load();
    }
  };

  const remove = async (row: Row) => {
    if (!spec.delete) return;
    try {
      await callRoute(appId, spec.delete, { row });
      setRows((rs) => rs.filter((r) => r[spec.key] !== row[spec.key]));
    } catch (e: any) {
      setStatus(`Delete failed: ${e.message}`);
    }
  };

  const submitDraft = async (e: React.FormEvent) => {
    e.preventDefault();
    const item: Row = {};
    editableCols.forEach((c) => {
      const v = draft[c.key];
      if (v !== undefined && v !== "") item[c.key] = coerce(c, String(v));
    });
    if (Object.keys(item).length === 0) return;
    await addRows([item]);
    setDraft({});
  };

  return (
    <div className="app-card" ref={gridRef} onPaste={onPaste}>
      <div className="app-toolbar">
        <span className="muted">
          {loading ? "Loading…" : `${rows.length} row${rows.length === 1 ? "" : "s"}`}
          {spec.create && " · paste rows from a spreadsheet anywhere in the table"}
        </span>
        <button className="btn" onClick={load}>
          Refresh
        </button>
      </div>
      {error && <div className="banner error">Could not load data: {error}</div>}
      {status && <div className="banner">{status}</div>}
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              {columns.map((c) => (
                <th key={c.key}>{c.label || c.key}</th>
              ))}
              {spec.delete && <th />}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, ri) => (
              <tr key={String(row[spec.key] ?? ri)}>
                {columns.map((col) => {
                  const editable = !!spec.update && col.editable !== false && col.key !== spec.key;
                  const value = row[col.key];
                  if (col.type === "boolean") {
                    return (
                      <td key={col.key}>
                        <input
                          type="checkbox"
                          checked={!!value}
                          disabled={!editable}
                          onChange={(e) => saveCell(row, col, String(e.target.checked))}
                        />
                      </td>
                    );
                  }
                  return (
                    <td key={col.key}>
                      {editable ? (
                        <input
                          className="cell"
                          type={col.type === "number" ? "number" : col.type === "date" ? "date" : "text"}
                          defaultValue={value == null ? "" : String(value)}
                          key={`${row[spec.key]}-${String(value)}`}
                          onBlur={(e) => saveCell(row, col, e.target.value)}
                          onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()}
                        />
                      ) : (
                        <span className="cell-text">{value == null ? "" : String(value)}</span>
                      )}
                    </td>
                  );
                })}
                {spec.delete && (
                  <td>
                    <button className="icon-btn danger" title="Delete row" onClick={() => remove(row)}>
                      ✕
                    </button>
                  </td>
                )}
              </tr>
            ))}
            {!loading && rows.length === 0 && !error && (
              <tr>
                <td colSpan={columns.length + 1} className="empty-row">
                  No rows yet.
                </td>
              </tr>
            )}
          </tbody>
          {spec.create && (
            <tfoot>
              <tr>
                {columns.map((c) => (
                  <td key={c.key}>
                    {editableCols.includes(c) ? (
                      <form onSubmit={submitDraft} style={{ display: "contents" }}>
                        <input
                          className="cell"
                          placeholder={c.label || c.key}
                          type={c.type === "number" ? "number" : c.type === "date" ? "date" : "text"}
                          value={String(draft[c.key] ?? "")}
                          onChange={(e) => setDraft((d) => ({ ...d, [c.key]: e.target.value }))}
                        />
                      </form>
                    ) : null}
                  </td>
                ))}
                {spec.delete && (
                  <td>
                    <button className="btn primary" onClick={submitDraft}>
                      Add
                    </button>
                  </td>
                )}
              </tr>
            </tfoot>
          )}
        </table>
      </div>
    </div>
  );
}
