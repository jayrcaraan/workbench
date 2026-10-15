"use client";

import React, { useCallback, useEffect, useState } from "react";
import {
  ChevronRight, Database, File, FileCode, FileJson, FileSpreadsheet, FileText, Folder, FolderOpen, Image as ImageIcon, Loader2, RefreshCw, type LucideIcon,
} from "lucide-react";
import { filesApi, humanSize, type Entry } from "@/lib/files";

const ICONS: Record<string, LucideIcon> = {
  csv: FileSpreadsheet, tsv: FileSpreadsheet, parquet: FileSpreadsheet, duckdb: Database, db: Database, sqlite: Database, sqlite3: Database,
  json: FileJson, jsonl: FileJson, md: FileText, txt: FileText, log: FileText, py: FileCode, js: FileCode, ts: FileCode, tsx: FileCode,
  sh: FileCode, sql: FileCode, html: FileCode, css: FileCode, png: ImageIcon, jpg: ImageIcon, jpeg: ImageIcon, gif: ImageIcon, svg: ImageIcon,
};
const iconFor = (name: string) => ICONS[name.split(".").pop()?.toLowerCase() ?? ""] ?? File;

interface Props {
  /** Live sandboxes to try, best first. The home volume is shared, so any of them shows the same files. */
  sandboxIds: string[];
  onOpen: (sandboxId: string, path: string) => void;
}

function Dir({ sandboxId, path, depth, onOpen, reload }: { sandboxId: string; path: string; depth: number; onOpen: Props["onOpen"]; reload: number }) {
  const [entries, setEntries] = useState<Entry[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<Record<string, boolean>>({});

  useEffect(() => {
    let live = true;
    setEntries(null);
    filesApi.list(sandboxId, path).then((r) => live && setEntries(r.entries)).catch((e) => live && setError(e.message));
    return () => { live = false; };
  }, [sandboxId, path, reload]);

  if (error) return <div className="ft-note error" style={{ paddingLeft: 12 + depth * 14 }}>{error}</div>;
  if (!entries) return <div className="ft-note" style={{ paddingLeft: 12 + depth * 14 }}><Loader2 size={12} className="spin" /> Loading…</div>;
  if (!entries.length) return <div className="ft-note" style={{ paddingLeft: 12 + depth * 14 }}>Empty</div>;
  return (
    <ul className="ft">
      {entries.map((e) => {
        const child = path ? `${path}/${e.name}` : e.name;
        const isDir = e.type === "dir";
        const expanded = open[e.name];
        const Icon = isDir ? (expanded ? FolderOpen : Folder) : iconFor(e.name);
        return (
          <li key={e.name}>
            <button
              className="ft-row"
              style={{ paddingLeft: 8 + depth * 14 }}
              onClick={() => (isDir ? setOpen((o) => ({ ...o, [e.name]: !o[e.name] })) : onOpen(sandboxId, child))}
              title={isDir ? child : `${child} · ${humanSize(e.size)}`}
            >
              {isDir ? <ChevronRight size={12} className={expanded ? "chev open" : "chev"} /> : <span className="ft-gap" />}
              <Icon size={14} />
              <span className="ft-name">{e.name}</span>
              {!isDir && <span className="ft-size">{humanSize(e.size)}</span>}
            </button>
            {isDir && expanded && <Dir sandboxId={sandboxId} path={child} depth={depth + 1} onOpen={onOpen} reload={reload} />}
          </li>
        );
      })}
    </ul>
  );
}

/** Tree view of the user's home directory (read-only). Folders load on expand. */
export function FileBrowser({ sandboxIds, onOpen }: Props) {
  const [active, setActive] = useState<string | null>(null);
  const [probing, setProbing] = useState(true);
  const [reload, setReload] = useState(0);

  const probe = useCallback(async () => {
    setProbing(true);
    for (const id of sandboxIds) {
      try {
        await filesApi.list(id, "");
        setActive(id);
        setProbing(false);
        return;
      } catch {}
    }
    setActive(null);
    setProbing(false);
  }, [sandboxIds.join(",")]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { void probe(); }, [probe]);

  return (
    <div className="files">
      <div className="files-head">
        <span>~ home</span>
        <button className="icon-btn" title="Refresh" onClick={() => { setReload((r) => r + 1); void probe(); }}><RefreshCw size={13} /></button>
      </div>
      <div className="files-body">
        {probing ? (
          <div className="ft-note"><Loader2 size={12} className="spin" /> Looking for a sandbox…</div>
        ) : active ? (
          <Dir sandboxId={active} path="" depth={0} onOpen={onOpen} reload={reload} />
        ) : (
          <div className="ft-empty">
            <Folder size={20} />
            <p>No sandbox is running yet.</p>
            <p className="muted">Use “Start” above. Your home shows up here as soon as it is up.</p>
          </div>
        )}
      </div>
    </div>
  );
}
