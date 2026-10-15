"use client";

import React from "react";
import { FolderTree, HardDrive, MessageSquare, Plus, X } from "lucide-react";
import { FileBrowser } from "./FileBrowser";
import type { Session } from "@/lib/sessions";

function ago(ts: number): string {
  const s = Math.max(0, (Date.now() - ts) / 1000);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

/** Sessions of the user. All of them mount the same home volume; each has its own sandbox. */
export function SessionRail({
  sessions, activeId, onSelect, onCreate, onRemove, onOpenFile, starting, onStart,
}: {
  starting: boolean;
  onStart: () => void;
  sessions: Session[];
  activeId: string;
  onSelect: (id: string) => void;
  onCreate: () => void;
  onRemove: (id: string) => void;
  onOpenFile: (sandboxId: string, path: string) => void;
}) {
  const [tab, setTab] = React.useState<"sessions" | "files">("sessions");
  // Files are read through a live sandbox; the home volume is shared, so the active session's is tried first.
  const active = sessions.find((s) => s.id === activeId);
  const sandboxIds = [active?.sandboxId, ...sessions.map((s) => s.sandboxId)].filter(
    (v, i, a): v is string => !!v && a.indexOf(v) === i
  );
  return (
    <nav className="rail" aria-label="Sidebar">
      <div className="seg" role="tablist">
        <button role="tab" aria-selected={tab === "sessions"} className={tab === "sessions" ? "on" : ""} onClick={() => setTab("sessions")}>
          <MessageSquare size={13} /> Sessions
        </button>
        <button role="tab" aria-selected={tab === "files"} className={tab === "files" ? "on" : ""} onClick={() => setTab("files")}>
          <FolderTree size={13} /> Files
        </button>
      </div>
      <div className={`pill-live ${starting ? "starting" : active?.sandboxId ? "" : "none"}`}>
        {starting ? "Starting sandbox…" : active?.sandboxId ? <>Sandbox <code>{active.sandboxId}</code></> : (
          <>No sandbox <button className="link" onClick={onStart}>Start</button></>
        )}
      </div>
      {tab === "files" ? <FileBrowser sandboxIds={sandboxIds} onOpen={onOpenFile} /> : (<>
      <button className="btn primary rail-new" onClick={onCreate}><Plus size={14} /> New session</button>
      <ul>
        {sessions.map((s) => (
          <li key={s.id} className={s.id === activeId ? "active" : ""}>
            <button className="rail-item" onClick={() => onSelect(s.id)} title={s.title}>
              <MessageSquare size={14} />
              <span className="rail-text">
                <span className="rail-title">{s.title}</span>
                <span className="rail-meta">
                  {s.sandboxId ? <code>{s.sandboxId}</code> : <span>no sandbox yet</span>} · {ago(s.createdAt)}
                </span>
              </span>
            </button>
            {sessions.length > 1 && (
              <button className="icon-btn rail-del" title="Remove from list" onClick={() => onRemove(s.id)}>
                <X size={13} />
              </button>
            )}
          </li>
        ))}
      </ul>
      <div className="rail-foot"><HardDrive size={13} /> One home volume shared by all sessions</div>
      </>)}
    </nav>
  );
}
