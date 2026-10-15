"use client";

import React, { useEffect, useRef, useState } from "react";
import { CopilotChat, useAgent, useConfigureSuggestions, useDefaultRenderTool } from "@copilotkit/react-core/v2";
import { Logo } from "@/components/workbench/Logo";
import { Canvas, type OpenFile } from "@/components/workbench/Canvas";
import { SessionRail } from "@/components/workbench/SessionRail";
import { ToolStep } from "@/components/workbench/ToolStep";
import { ThinkingBlock } from "@/components/workbench/ThinkingBlock";
import { RunningContext, groupTurns } from "@/components/workbench/TurnActions";
import type { AgentState, PublishedApp } from "@/lib/uiSpec";
import { AGENT_NAME, useSessions } from "./providers";
import { useCopilotKit } from "@copilotkit/react-core/v2";

const SUGGESTIONS = [
  { title: "Customer tracker", message: "Build a customer tracker with name, email, company and status." },
  { title: "Expense spreadsheet", message: "Create a spreadsheet for expenses with fields: description (text), amount (currency), date, category (select: Travel, Meals, Software) and reimbursed (checkbox)." },
  { title: "Two apps", message: "Build a notes API and a separate read-only page that lists the notes, as two apps." },
];

const RAIL_WIDTH = 232;

/**
 * The model emits a reasoning block per step; stacked, they bury the conversation. Show them as one
 * collapsed "Thoughts" block (all steps, in order) at the position of the latest one.
 */
function mergeReasoning(messages: any[]): any[] {
  // Per turn (a user message starts a new one): earlier turns' thoughts must not pile into the latest block.
  const out: any[] = [];
  let turn: any[] = [];
  const flush = () => {
    const reasoning = turn.filter((m) => m.role === "reasoning");
    if (reasoning.length < 2) return out.push(...turn);
    const last = reasoning[reasoning.length - 1];
    const merged = { ...last, content: reasoning.map((m) => m.content).filter(Boolean).join("\n\n---\n\n") };
    out.push(...turn.filter((m) => m.role !== "reasoning" || m === last).map((m) => (m === last ? merged : m)));
  };
  for (const m of messages) {
    if (m.role === "user") { flush(); turn = []; }
    turn.push(m);
  }
  flush();
  return out;
}

const textOf = (content: unknown): string =>
  typeof content === "string"
    ? content
    : Array.isArray(content)
    ? content.map((c: any) => (typeof c === "string" ? c : c?.text ?? "")).join("")
    : "";

export default function Workbench() {
  const { agent, isReady } = useAgent({ agentId: AGENT_NAME });
  const apps = (agent.state as AgentState | undefined)?.apps ?? [];
  const { sessions, activeId, select, create, update, remove } = useSessions();
  const { copilotkit } = useCopilotKit();

  // The conversation is stored in SQLite by the agent service. When a session opens with nothing in memory (after a
  // restart of any process, or in a fresh browser), load it back from there.
  const restored = useRef<Set<string>>(new Set());
  useEffect(() => {
    if (!activeId || !isReady || restored.current.has(activeId)) return;
    restored.current.add(activeId);
    let live = true;
    (async () => {
      try {
        const r = await fetch(`/api/sessions/${activeId}/history`, { cache: "no-store" });
        if (!r.ok) return;
        const h = await r.json();
        if (!h.messages?.length) return;
        // The runtime handshake (connect) can land after this and replace the list with its own (empty) one,
        // so apply, then check again a moment later.
        for (const wait of [0, 1200, 3000]) {
          await new Promise((res) => setTimeout(res, wait));
          if (!live) return;
          if (agent.messages?.length) return;
          agent.setMessages(h.messages);
          if (h.apps?.length) agent.setState({ ...(agent.state as object), apps: h.apps });
        }
      } catch {}
    })();
    return () => { live = false; };
  }, [activeId, isReady]); // eslint-disable-line react-hooks/exhaustive-deps

  // Every session gets its sandbox without anyone asking the agent: start it as soon as the session is open.
  const [starting, setStarting] = useState(false);
  const startedFor = useRef<Set<string>>(new Set());
  const startSandbox = async (id: string) => {
    setStarting(true);
    try {
      const res = await fetch(`/api/sessions/${id}/sandbox`, { method: "POST" });
      const body = await res.json();
      if (res.ok && body.sandbox_id) update(id, { sandboxId: body.sandbox_id });
    } catch {} finally {
      setStarting(false);
    }
  };
  const activeSession = sessions?.find((s) => s.id === activeId);
  useEffect(() => {
    if (!activeId || activeSession?.sandboxId || startedFor.current.has(activeId)) return;
    startedFor.current.add(activeId);
    void startSandbox(activeId);
  }, [activeId, activeSession?.sandboxId]); // eslint-disable-line react-hooks/exhaustive-deps

  // Name the session after the user's intent once the first answer is in (the truncated message is only a placeholder).
  const titled = useRef<Set<string>>(new Set());
  useEffect(() => {
    if (!activeId || agent.isRunning || titled.current.has(activeId)) return;
    const msgs = (agent.messages ?? []) as any[];
    const first = msgs.find((m) => m.role === "user");
    const answered = msgs.some((m) => m.role === "assistant" && textOf(m.content).trim());
    const t = activeSession?.title ?? "";
    const placeholder = t === "New session" || (first && textOf(first.content).trim().replace(/\s+/g, " ").startsWith(t.replace(/…$/, "")));
    if (!first || !answered || !placeholder) return;
    titled.current.add(activeId);
    fetch(`/api/sessions/${activeId}/title`, { method: "POST" })
      .then((r) => (r.ok ? r.json() : null))
      .then((b) => b?.title && update(activeId, { title: b.title }))
      .catch(() => {});
  }, [agent.isRunning, agent.messages, activeId, activeSession?.title]); // eslint-disable-line react-hooks/exhaustive-deps

  // Resume an app whose sandbox expired: the service starts a new sandbox and replays how the app was started.
  const resumeApp = async (app: PublishedApp) => {
    if (!activeId) return;
    const res = await fetch(`/api/sessions/${activeId}/apps/${encodeURIComponent(app.name)}/resume`, { method: "POST" });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(typeof body.detail === "string" ? body.detail : `Could not resume (HTTP ${res.status})`);
    const current = ((agent.state as AgentState | undefined)?.apps ?? []).filter((a) => a.app_id !== body.replaces);
    agent.setState({ ...(agent.state as object), apps: [...current, body.app] });
    if (body.sandbox_id) update(activeId, { sandboxId: body.sandbox_id });
  };

  // Files opened from the browser become tabs in the workspace.
  const [files, setFiles] = useState<OpenFile[]>([]);
  const [focus, setFocus] = useState<{ path: string; n: number } | null>(null);
  const openFile = (sandboxId: string, path: string) => {
    setFiles((f) => (f.some((x) => x.path === path) ? f : [...f, { sandboxId, path }]));
    setFocus((c) => ({ path, n: (c?.n ?? 0) + 1 }));
  };
  const closeFile = (path: string) => setFiles((f) => f.filter((x) => x.path !== path));
  const ask = async (text: string) => {
    agent.addMessage({ id: crypto.randomUUID(), role: "user", content: text } as any);
    try { await copilotkit.runAgent({ agent }); } catch {}
  };

  // Name the session after its first request and show which sandbox it is using.
  useEffect(() => {
    if (!activeId) return;
    const messages = (agent.messages ?? []) as any[];
    const first = messages.find((m) => m.role === "user");
    const title = first ? textOf(first.content).trim().replace(/\s+/g, " ").slice(0, 48) : "";
    const sandboxFromApps = apps.find((a) => a.app_id)?.app_id.split("/")[0];
    const sandboxFromTools = messages
      .filter((m) => m.role === "tool")
      .map((m) => /sbx-[0-9a-f]{8}/.exec(textOf(m.content))?.[0])
      .find(Boolean);
    update(activeId, {
      ...(title && activeSession?.title === "New session" ? { title } : {}),
      ...((sandboxFromApps || sandboxFromTools) ? { sandboxId: sandboxFromApps || sandboxFromTools } : {}),
    });
  }, [agent.messages, apps, activeId, update]);
  useDefaultRenderTool({ render: (p) => <ToolStep {...p} /> });
  useConfigureSuggestions({ suggestions: SUGGESTIONS, available: "before-first-message" });
  const [chatWidth, setChatWidth] = useState(440);
  const dragging = useRef(false);

  const onDrag = (e: React.PointerEvent) => {
    if (dragging.current) setChatWidth(Math.min(680, Math.max(340, e.clientX - RAIL_WIDTH)));
  };

  return (
    <div className="workbench" onPointerMove={onDrag} onPointerUp={() => (dragging.current = false)}>
      <header className="topbar">
        <Logo />
        <span className="brand-name">Workbench</span>
        <span className="brand-sub">Build, host and fill micro-apps</span>
      </header>
      <main className="split" style={{ gridTemplateColumns: `${RAIL_WIDTH}px ${chatWidth}px 6px 1fr` }}>
        <SessionRail sessions={sessions!} activeId={activeId!} starting={starting} onStart={() => activeId && startSandbox(activeId)} onSelect={select} onCreate={create} onRemove={remove} onOpenFile={openFile} />
        <section className="chat">
          <RunningContext.Provider value={agent.isRunning}>
          <CopilotChat
            agentId={AGENT_NAME}
            labels={{ chatInputPlaceholder: "Describe an app…" }}
            messageView={{ transformMessages: mergeReasoning, groupMessages: groupTurns as any, reasoningMessage: ThinkingBlock as any }}
          />
          </RunningContext.Provider>
        </section>
        <div className="divider" onPointerDown={(e) => { dragging.current = true; e.currentTarget.setPointerCapture(e.pointerId); }} />
        <section className="pane">
          <Canvas apps={apps} building={agent.isRunning} files={files} focus={focus} onCloseFile={closeFile} onAsk={ask} onResume={resumeApp} />
        </section>
      </main>
    </div>
  );
}
