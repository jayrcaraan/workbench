"use client";

import React from "react";
import { Check, Download, Loader2, RefreshCw, TriangleAlert } from "lucide-react";
import { useRemoteRows } from "@/lib/useRemoteRows";
import type { Row, SheetField } from "@/lib/sheets";
import type { SheetSpec } from "@/lib/uiSpec";
import { SheetGrid } from "./SheetGrid";

function toCsv(fields: SheetField[], rows: Row[]): string {
  const esc = (v: unknown) => {
    const s = v === null || v === undefined ? "" : String(v);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  return [fields.map((f) => esc(f.label ?? f.key)).join(","), ...rows.map((r) => fields.map((f) => esc(r[f.key])).join(","))].join("\n");
}

/** A typed spreadsheet bound to an app's routes. The same component serves any app that follows the contract. */
export function ApiSheet({ appId, spec, actions }: { appId: string; spec: SheetSpec; actions?: React.ReactNode }) {
  const { rows, setRows, state, error, skipped, drafts, reload, canEdit } = useRemoteRows(appId, spec);
  // Apps may use their own vocabulary (boolean, textarea); the grid knows the six sheet types.
  const fields = spec.columns.map((c) => ({
    ...c,
    label: c.label ?? c.key,
    type: c.type === "boolean" ? "checkbox" : c.type === "textarea" || !c.type ? "text" : c.type,
    // Ids and timestamps are the app's to fill in.
    editable: c.editable !== false && c.key !== spec.key && !/^(id|created_at|updated_at|created|updated)$/i.test(c.key),
  })) as SheetField[];

  const download = () => {
    const url = URL.createObjectURL(new Blob([toCsv(fields, rows)], { type: "text/csv" }));
    Object.assign(document.createElement("a"), { href: url, download: `${spec.title}.csv` }).click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="sheet-view">
      <div className="sheet-head">
        <h3 className="sheet-name">{spec.title}</h3>
        <span className={`save-state ${state}`}>
          {state === "loading" ? <><Loader2 size={13} className="spin" /> Loading</> :
           state === "saving" ? <><Loader2 size={13} className="spin" /> Saving</> :
           state === "error" ? <><TriangleAlert size={13} /> Problem</> :
           <><Check size={13} /> Saved to app</>}
        </span>
        {drafts > 0 && <span className="save-state error" title={error ?? ""}><TriangleAlert size={13} /> {drafts} row{drafts > 1 ? "s" : ""} not accepted yet</span>}
        {skipped > 0 && <span className="save-state error"><TriangleAlert size={13} /> {skipped} invalid, not saved</span>}
        <span className="spacer" />
        <span className="muted">{rows.length} rows</span>
        {actions}
        <button className="icon-btn" title="Reload from the app" onClick={reload}><RefreshCw size={15} /></button>
        <button className="btn" onClick={download}><Download size={14} /> CSV</button>
      </div>
      {error && <div className="banner error">{error}</div>}
      {!canEdit && <div className="banner">This app has no create route, so the grid is read-only.</div>}
      <SheetGrid fields={fields} rows={rows} onChange={canEdit ? setRows : () => {}} />
      <p className="hint">Changes are saved to the app as you make them, and new rows appear on their own. Enter ↓ · Tab → · paste from Excel or Sheets.</p>
    </div>
  );
}
