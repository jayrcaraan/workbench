"use client";

import React, { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Calendar, CalendarDays, Check, CheckSquare, ChevronDown, DollarSign, Hash, Trash2, Type, type LucideIcon } from "lucide-react";
import { coerce, display, isInvalid, type FieldType, type Row, type SheetField } from "@/lib/sheets";

const TYPE_ICON: Record<FieldType, LucideIcon> = {
  text: Type,
  number: Hash,
  currency: DollarSign,
  date: Calendar,
  checkbox: CheckSquare,
  select: ChevronDown,
};

interface Props {
  fields: SheetField[];
  rows: Row[];
  onChange: (rows: Row[]) => void;
}
interface Pos {
  r: number;
  c: number;
}

const PILLS = 6;
/** Stable colour for a select value, so the same status always looks the same. */
const pillIndex = (options: string[] | undefined, v: string) => Math.max(0, options?.indexOf(v) ?? 0) % PILLS;

/** Dropdown for select cells. Focus stays on the grid, so arrows / Enter / Esc go through the grid's key handling. */
function OptionPopover({ options, current, onPick }: { options: string[]; current: string; onPick: (v: string) => void }) {
  const anchor = useRef<HTMLSpanElement>(null);
  const [rect, setRect] = useState<{ top: number; left: number; width: number } | null>(null);
  useLayoutEffect(() => {
    const td = anchor.current?.parentElement?.getBoundingClientRect();
    if (td) setRect({ top: td.bottom + 4, left: td.left, width: Math.max(td.width, 180) });
  }, []);
  const choices = ["", ...options];
  return (
    <>
      <span ref={anchor} />
      {rect && (
        <ul className="popover" role="listbox" style={{ top: rect.top, left: rect.left, minWidth: rect.width }}
            onMouseDown={(e) => e.preventDefault()}>
          {choices.map((o) => (
            <li key={o || "__none"} role="option" aria-selected={o === current}
                className={o === current ? "on" : ""} onClick={() => onPick(o)}>
              {o ? <span className={`pill pill-${pillIndex(options, o)}`}>{o}</span> : <span className="muted">— none —</span>}
              {o === current && <Check size={14} />}
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

/** Text entry that also opens the browser's native date picker (button, Alt+↓, or opening the cell). */
function DateEditor({
  value, onChange, onPick, onBlurOut, autoOpen,
}: { value: string; onChange: (v: string) => void; onPick: (iso: string) => void; onBlurOut: () => void; autoOpen: boolean }) {
  const wrap = useRef<HTMLDivElement>(null);
  const picker = useRef<HTMLInputElement>(null);
  const open = () => { try { picker.current?.showPicker?.(); } catch {} };
  useEffect(() => { if (autoOpen) open(); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const iso = /^\d{4}-\d{2}-\d{2}/.test(value) ? value.slice(0, 10) : "";
  return (
    <div
      ref={wrap}
      className="date-edit"
      onBlur={(e) => { if (!wrap.current?.contains(e.relatedTarget as Node)) onBlurOut(); }}
    >
      <input
        autoFocus
        type="text"
        placeholder="YYYY-MM-DD"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => { if (e.altKey && e.key === "ArrowDown") { e.preventDefault(); open(); } }}
      />
      <input ref={picker} type="date" className="date-hidden" tabIndex={-1} value={iso}
             onChange={(e) => e.target.value && onPick(e.target.value)} aria-hidden />
      <button type="button" className="date-btn" tabIndex={-1} title="Pick a date"
              onMouseDown={(e) => e.preventDefault()} onClick={open}>
        <CalendarDays size={15} />
      </button>
    </div>
  );
}

/** A keyboard-driven, typed spreadsheet grid. A blank row is always available at the bottom. */
export function SheetGrid({ fields, rows, onChange }: Props) {
  const [sel, setSelState] = useState<Pos>({ r: 0, c: 0 });
  const setSel = (p: Pos | ((q: Pos) => Pos)) => {
    const next = typeof p === "function" ? p(selRef.current) : p;
    selRef.current = next;
    setSelState(next);
  };
  const [editing, setEditingState] = useState<string | null>(null); // draft text while editing
  // The ref is the source of truth for key handlers: events can arrive faster than renders.
  const editingRef = useRef<string | null>(null);
  const selRef = useRef<Pos>({ r: 0, c: 0 });
  const setEditing = (v: string | null) => {
    editingRef.current = v;
    setEditingState(v);
  };
  const root = useRef<HTMLDivElement>(null);
  const editOpenedByPointer = useRef(false);
  const total = rows.length + 1; // + trailing blank row
  // Latest rows, updated synchronously on every change so rapid edits never overwrite each other.
  const rowsRef = useRef(rows);
  rowsRef.current = rows;
  const emit = useCallback((next: Row[]) => { rowsRef.current = next; onChange(next); }, [onChange]);

  const setCell = useCallback(
    (r: number, c: number, value: unknown) => {
      const next = rowsRef.current.slice();
      while (next.length <= r) next.push({});
      next[r] = { ...next[r], [fields[c].key]: value };
      emit(next);
    },
    [fields, emit]
  );

  const clamp = (p: Pos): Pos => ({
    r: Math.max(0, Math.min(total - 1, p.r)),
    c: Math.max(0, Math.min(fields.length - 1, p.c)),
  });
  const move = (dr: number, dc: number) => setSel((p) => clamp({ r: p.r + dr, c: p.c + dc }));

  const commit = (moveDown = true) => {
    const draft = editingRef.current;
    if (draft !== null) {
      const { r, c } = selRef.current;
      setEditing(null); // before anything else, so a blur during unmount cannot commit twice
      setCell(r, c, coerce(fields[c], draft));
    }
    if (moveDown) move(1, 0);
  };

  const startEdit = (initial?: string) => {
    const { r, c } = selRef.current;
    const f = fields[c];
    if (f.type === "checkbox" || f.editable === false) return;
    editOpenedByPointer.current = initial === undefined; // Enter / double-click opens the picker; typing does not
    const current = rows[r]?.[f.key];
    setEditing(initial ?? (current === null || current === undefined ? "" : String(current)));
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    const f = fields[selRef.current.c];
    if (editingRef.current !== null) {
      // Keys that reach the grid (not the input) while editing: the input has not taken focus yet.
      if (e.target === e.currentTarget && e.key.length === 1 && !e.metaKey && !e.ctrlKey) {
        e.preventDefault();
        setEditing(editingRef.current + e.key);
        return;
      }
      if (f.type === "select" && (e.key === "ArrowDown" || e.key === "ArrowUp")) {
        e.preventDefault();
        const opts = ["", ...(f.options ?? [])];
        const i = Math.max(0, opts.indexOf(editingRef.current ?? ""));
        setEditing(opts[(i + (e.key === "ArrowDown" ? 1 : opts.length - 1)) % opts.length]);
        return;
      }
      if (f.type === "select" && e.key.length === 1 && !e.metaKey && !e.ctrlKey) {   // type to jump
        e.preventDefault();
        const hit = (f.options ?? []).find((o) => o.toLowerCase().startsWith(e.key.toLowerCase()));
        if (hit) setEditing(hit);
        return;
      }
      if (e.key === "Enter") { e.preventDefault(); commit(true); }
      else if (e.key === "Tab") { e.preventDefault(); commit(false); move(0, e.shiftKey ? -1 : 1); }
      else if (e.key === "Escape") { e.preventDefault(); setEditing(null); }
      return;
    }
    const mod = e.metaKey || e.ctrlKey;
    if (e.key === "ArrowDown") { e.preventDefault(); move(1, 0); }
    else if (e.key === "ArrowUp") { e.preventDefault(); move(-1, 0); }
    else if (e.key === "ArrowLeft") { e.preventDefault(); move(0, -1); }
    else if (e.key === "ArrowRight") { e.preventDefault(); move(0, 1); }
    else if (e.key === "Tab") { e.preventDefault(); move(0, e.shiftKey ? -1 : 1); }
    else if (e.key === "Enter" || e.key === "F2") { e.preventDefault(); startEdit(); }
    else if (e.key === "Backspace" || e.key === "Delete") { e.preventDefault(); const { r, c } = selRef.current; if (r < rows.length && f.editable !== false) setCell(r, c, f.type === "checkbox" ? false : null); }
    else if (e.key === " " && f.type === "select" && f.editable !== false) { e.preventDefault(); startEdit(); }
    else if (e.key === " " && f.type === "checkbox" && f.editable !== false) { e.preventDefault(); const { r, c } = selRef.current; setCell(r, c, !rows[r]?.[f.key]); }
    else if (!mod && e.key.length === 1 && f.type !== "checkbox" && f.editable !== false) { e.preventDefault(); startEdit(e.key); }
  };

  const onPaste = (e: React.ClipboardEvent) => {
    if (editingRef.current !== null) return;
    const text = e.clipboardData.getData("text/plain");
    if (!text) return;
    e.preventDefault();
    const grid = text.replace(/\r/g, "").replace(/\n$/, "").split("\n").map((l) => l.split("\t"));
    const next = rowsRef.current.slice();
    grid.forEach((line, i) => {
      const r = selRef.current.r + i;
      while (next.length <= r) next.push({});
      const row = { ...next[r] };
      line.forEach((raw, j) => {
        const f = fields[selRef.current.c + j];
        if (f && f.editable !== false) row[f.key] = coerce(f, raw);
      });
      next[r] = row;
    });
    emit(next);
  };

  const removeRow = (r: number) => {
    emit(rowsRef.current.filter((_, i) => i !== r));
    setSel((p) => clamp({ ...p, r: Math.min(p.r, rows.length - 1) }));
  };

  // The editor input unmounts when an edit ends; hand focus back to the grid so typing continues.
  const wasEditing = useRef(false);
  useEffect(() => {
    if (editing === null && wasEditing.current) root.current?.focus({ preventScroll: true });
    wasEditing.current = editing !== null;
  }, [editing]);

  useEffect(() => { setSel((p) => clamp(p)); }, [fields.length, rows.length]); // eslint-disable-line react-hooks/exhaustive-deps

  const sums = useMemo(
    () =>
      fields.map((f) =>
        // An identifier column (read-only, or named id) is not a measure: summing row ids means nothing.
        (f.type === "number" || f.type === "currency") && f.editable !== false && !/^id$|_id$/i.test(f.key)
          ? rows.reduce((a, r) => a + (typeof r[f.key] === "number" ? (r[f.key] as number) : 0), 0)
          : null
      ),
    [fields, rows]
  );

  return (
    <div className="sheet-scroll">
      <div ref={root} className="sheet" tabIndex={0} onKeyDown={onKeyDown} onPaste={onPaste} role="grid">
        <table>
          <thead>
            <tr>
              <th className="rownum" />
              {fields.map((f, c) => {
                const Icon = TYPE_ICON[f.type];
                return (
                  <th key={f.key} className={sel.c === c ? "active-col" : ""}>
                    <span className="th-inner"><Icon size={13} />{f.label}</span>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {Array.from({ length: total }, (_, r) => {
              const row = rows[r];
              const ghost = r === rows.length;
              return (
                <tr key={r} className={ghost ? "ghost" : sel.r === r ? "active-row" : ""}>
                  <td className="rownum">
                    {!ghost && row?.__error ? (
                      <span className="row-warn" title={String(row.__error)}>!</span>
                    ) : null}
                    <span className="n">{ghost ? "+" : r + 1}</span>
                    {!ghost && (
                      <button className="row-del" title="Delete row" tabIndex={-1} onClick={() => removeRow(r)}>
                        <Trash2 size={13} />
                      </button>
                    )}
                  </td>
                  {fields.map((f, c) => {
                    const value = row?.[f.key];
                    const active = sel.r === r && sel.c === c;
                    const bad = isInvalid(f, value);
                    return (
                      <td
                        key={f.key}
                        className={`cell t-${f.type}${active ? " active" : ""}${bad ? " invalid" : ""}${f.editable === false ? " readonly" : ""}`}
                        onMouseDown={() => {
                          const wasActive = selRef.current.r === r && selRef.current.c === c;
                          if (editingRef.current !== null) { if (wasActive && f.type === "select") return; commit(false); }
                          setSel({ r, c });
                          root.current?.focus();
                          // One click on an already-selected dropdown or date cell opens it.
                          if (wasActive && (f.type === "select" || f.type === "date") && f.editable !== false) setTimeout(() => startEdit(), 0);
                        }}
                        onDoubleClick={() => startEdit()}
                      >
                        {active && editing !== null ? (
                          f.type === "select" ? (
                            <OptionPopover
                              options={f.options ?? []}
                              current={editing}
                              onPick={(v) => { setCell(r, c, v || null); setEditing(null); root.current?.focus(); }}
                            />
                          ) : f.type === "date" ? (
                            <DateEditor
                              value={editing}
                              autoOpen={editOpenedByPointer.current}
                              onChange={(v) => setEditing(v)}
                              onPick={(iso) => { setCell(r, c, iso); setEditing(null); root.current?.focus(); }}
                              onBlurOut={() => commit(false)}
                            />
                          ) : (
                            <input
                              autoFocus
                              type="text"
                              inputMode={f.type === "number" || f.type === "currency" ? "decimal" : undefined}
                              value={editing}
                              onChange={(e) => setEditing(e.target.value)}
                              onBlur={() => commit(false)}
                            />
                          )
                        ) : f.type === "checkbox" ? (
                          <input
                            type="checkbox"
                            tabIndex={-1}
                            checked={!!value}
                            onChange={(e) => setCell(r, c, e.target.checked)}
                          />
                        ) : f.type === "select" && value ? (
                          <span className="cell-inner">
                            <span className={`pill pill-${pillIndex(f.options, String(value))}`}>{String(value)}</span>
                            <ChevronDown size={13} className="cell-affordance" />
                          </span>
                        ) : f.type === "select" ? (
                          <span className="cell-inner"><span /><ChevronDown size={13} className="cell-affordance" /></span>
                        ) : f.type === "date" ? (
                          <span className="cell-inner"><span>{display(f, value)}</span><CalendarDays size={13} className="cell-affordance" /></span>
                        ) : (
                          <span>{display(f, value)}</span>
                        )}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
          {sums.some((s) => s !== null) && (
            <tfoot>
              <tr>
                <td className="rownum">Σ</td>
                {fields.map((f, i) => (
                  <td key={f.key} className="sum">
                    {sums[i] !== null ? display(f, sums[i]) : ""}
                  </td>
                ))}
              </tr>
            </tfoot>
          )}
        </table>
      </div>
    </div>
  );
}
