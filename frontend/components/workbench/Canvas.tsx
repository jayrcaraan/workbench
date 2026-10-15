"use client";

import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  BarChart3, ExternalLink, File as FileIcon, FileSpreadsheet, Globe, LayoutDashboard, LayoutPanelLeft, RefreshCw, SquarePen, Table2, X, Loader2, Power,
} from "lucide-react";
import { AppView } from "@/components/apps/AppView";
import { APP_DEAD_EVENT } from "@/lib/appClient";
import { FileViewer } from "@/components/workbench/FileViewer";
import { useSessions } from "@/app/providers";
import type { PublishedApp } from "@/lib/uiSpec";

const KIND_ICON = { table: Table2, sheet: FileSpreadsheet, dashboard: LayoutDashboard, form: SquarePen, metrics: BarChart3, iframe: Globe } as const;
const iconFor = (kind: string) => KIND_ICON[kind as keyof typeof KIND_ICON] ?? Globe;

export interface OpenFile {
  sandboxId: string;
  path: string;
}

type Item =
  | { id: string; kind: "app"; title: string; app: PublishedApp }
  | { id: string; kind: "file"; title: string; file: OpenFile };

interface Props {
  apps: PublishedApp[];
  building: boolean;
  files: OpenFile[];
  /** Bumped by the page when the user opens a file, so it takes focus. */
  focus: { path: string; n: number } | null;
  onCloseFile: (path: string) => void;
  onAsk: (text: string) => void;
  /** Restart an app whose sandbox expired, in a new sandbox. Rejects with a readable message on failure. */
  onResume: (app: PublishedApp) => Promise<void>;
}

/** The right-hand workspace: what the agent published plus files opened from the browser, as closable tabs. */
export function Canvas({ apps: published, building, files, focus, onCloseFile, onAsk, onResume }: Props) {
  // Agent state can momentarily arrive without apps between runs; keep the last list instead of
  // unmounting (and re-fetching) the open app each time.
  const lastApps = useRef<PublishedApp[]>([]);
  if (published.length) lastApps.current = published;
  const all = published.length ? published : lastApps.current;

  // Closing an app tab hides it for this session; it comes back if the agent republishes it with a changed spec.
  const { activeId } = useSessions();
  const storeKey = `workbench.closed.${activeId}`;
  const [closed, setClosed] = useState<Record<string, string>>({});
  useEffect(() => {
    try { setClosed(JSON.parse(window.localStorage.getItem(storeKey) ?? "{}")); } catch { setClosed({}); }
  }, [storeKey]);
  const stamp = (a: PublishedApp) => JSON.stringify(a.ui).length + ":" + a.title;
  const persist = (next: Record<string, string>) => {
    setClosed(next);
    try { window.localStorage.setItem(storeKey, JSON.stringify(next)); } catch {}
  };

  const items: Item[] = useMemo(
    () => [
      ...all.filter((a) => closed[a.app_id] !== stamp(a)).map((a): Item => ({ id: `app:${a.app_id}`, kind: "app", title: a.title, app: a })),
      ...files.map((f): Item => ({ id: `file:${f.path}`, kind: "file", title: f.path.split("/").pop() ?? f.path, file: f })),
    ],
    [all, closed, files]
  );

  const [dead, setDead] = useState<Set<string>>(new Set());
  const [resuming, setResuming] = useState<string | null>(null);
  const [resumeError, setResumeError] = useState<string | null>(null);
  useEffect(() => {
    const on = (e: Event) => setDead((d) => new Set(d).add((e as CustomEvent).detail.appId));
    window.addEventListener(APP_DEAD_EVENT, on);
    return () => window.removeEventListener(APP_DEAD_EVENT, on);
  }, []);
  const [selected, setSelected] = useState<string | null>(null);
  const [reloads, setReloads] = useState<Record<string, number>>({});

  // A newly published app takes focus; after that the user's own tab choice wins.
  const lastApp = [...items].reverse().find((i) => i.kind === "app")?.id ?? null;
  const [seen, setSeen] = useState<string | null>(null);
  if (lastApp && lastApp !== seen) {
    setSeen(lastApp);
    setSelected(lastApp);
  }
  // Opening a file from the browser focuses it.
  const [seenFocus, setSeenFocus] = useState(0);
  if (focus && focus.n !== seenFocus) {
    setSeenFocus(focus.n);
    setSelected(`file:${focus.path}`);
  }

  const current = items.find((i) => i.id === selected) ?? items[items.length - 1];
  const closeItem = (i: Item) => (i.kind === "file" ? onCloseFile(i.file.path) : persist({ ...closed, [i.app.app_id]: stamp(i.app) }));
  const closeAll = () => {
    persist({ ...closed, ...Object.fromEntries(items.filter((i): i is Extract<Item, { kind: "app" }> => i.kind === "app").map((i) => [i.app.app_id, stamp(i.app)])) });
    files.forEach((f) => onCloseFile(f.path));
  };

  if (!current) {
    return (
      <div className="workspace">
        <div className="empty">
          <div className={building ? "empty-icon pulse" : "empty-icon"}><LayoutPanelLeft size={26} /></div>
          <h2>{building ? "Building your app…" : "Nothing open yet"}</h2>
          <p>
            {building
              ? "The agent is writing code and starting it in a sandbox. It appears here when it responds."
              : "Ask the agent for an app, a tracker, a spreadsheet or a dashboard. You can also open a file from the Files tab."}
          </p>
        </div>
      </div>
    );
  }

  const app = current.kind === "app" ? current.app : null;
  const CurrentIcon = app ? iconFor(app.ui.kind) : FileIcon;
  const iframeUrl = app && app.ui.kind === "iframe" ? app.ui.url : undefined;
  return (
    <div className="workspace">
      {items.length > 1 && (
        <div className="tabbar" role="tablist">
          {items.map((it) => {
            const TabIcon = it.kind === "app" ? iconFor(it.app.ui.kind) : FileIcon;
            const active = it.id === current.id;
            return (
              <div key={it.id} className={active ? "tab active" : "tab"} role="tab" aria-selected={active}
                   onClick={() => setSelected(it.id)} onAuxClick={(e) => { if (e.button === 1) closeItem(it); }}>
                <TabIcon size={14} /><span>{it.title}</span>
                <button className="tab-close" title="Close" aria-label={`Close ${it.title}`}
                        onClick={(e) => { e.stopPropagation(); closeItem(it); }}>
                  <X size={13} />
                </button>
              </div>
            );
          })}
          {items.length > 2 && <button className="tab-all" onClick={closeAll}>Close all</button>}
        </div>
      )}
      <div className="toolbar">
        <CurrentIcon size={16} />
        <strong>{current.title}</strong>
        <code className="chip">{app ? app.app_id : current.kind === "file" ? current.file.sandboxId : ""}</code>
        <span className="spacer" />
        <button className="icon-btn" title="Reload" onClick={() => setReloads((r) => ({ ...r, [current.id]: (r[current.id] ?? 0) + 1 }))}>
          <RefreshCw size={15} />
        </button>
        {iframeUrl && (
          <a className="icon-btn" title="Open in new tab" href={iframeUrl} target="_blank" rel="noreferrer">
            <ExternalLink size={15} />
          </a>
        )}
        <button className="icon-btn" title="Close this tab" aria-label="Close this tab" onClick={() => closeItem(current)}>
          <X size={15} />
        </button>
      </div>
      {app && dead.has(app.app_id) && (
        <div className="resume-bar" role="alert">
          <Power size={16} />
          <div>
            <strong>This app's sandbox has expired.</strong>
            <div className="muted">Its files and data are safe in your home. Start it again in a new sandbox.</div>
            {resumeError && <div className="muted" style={{ color: "var(--danger)" }}>{resumeError}</div>}
          </div>
          <span className="spacer" />
          <button
            className="btn primary"
            disabled={resuming === app.app_id}
            onClick={async () => {
              setResuming(app.app_id);
              setResumeError(null);
              try {
                await onResume(app);
                setDead((d) => { const n = new Set(d); n.delete(app.app_id); return n; });
              } catch (e: any) {
                setResumeError(e?.message ?? String(e));
              } finally {
                setResuming(null);
              }
            }}
          >
            {resuming === app.app_id ? <><Loader2 size={14} className="spin" /> Resuming…</> : "Resume in a new sandbox"}
          </button>
        </div>
      )}
      <div className={`workspace-body${app?.ui.kind === "sheet" ? " flush" : ""}`}>
        {current.kind === "app" ? (
          <AppView key={`${current.id}:${reloads[current.id] ?? 0}`} app={current.app} />
        ) : (
          <FileViewer key={`${current.id}:${reloads[current.id] ?? 0}`} sandboxId={current.file.sandboxId} path={current.file.path} onAsk={onAsk} />
        )}
      </div>
    </div>
  );
}
