"use client";

import React, { createContext, useContext } from "react";
import { messageGroup, messageRow } from "@copilotkit/react-core/v2";
import { Brain, ChevronRight, ListChecks, Loader2 } from "lucide-react";

/** True while the agent is running, so the latest turn's actions stay open and live. */
export const RunningContext = createContext(false);

// Key of the last group built by groupTurns, to know which group is the live one.
let lastGroupKey: string | null = null;

const hasText = (m: any) =>
  typeof m.content === "string"
    ? m.content.trim().length > 0
    : Array.isArray(m.content) && m.content.some((c: any) => (typeof c === "string" ? c : c?.text ?? "").trim());

/**
 * Lays each turn out as: user message, ONE group holding every action (tool calls, skills, thoughts),
 * then the agent's answer. The group is open while the agent works and collapses when it is done.
 */
export function groupTurns(messages: any[]) {
  const rows: ReturnType<typeof messageRow>[] = [];
  let i = 0;
  lastGroupKey = null;
  while (i < messages.length) {
    const m = messages[i];
    if (m.role === "user") {
      rows.push(messageRow(m));
      i++;
      continue;
    }
    // Everything up to the next user message belongs to this turn.
    let j = i;
    while (j < messages.length && messages[j].role !== "user") j++;
    const turn = messages.slice(i, j);
    // The answer is the last assistant message with text; everything before it (and after, e.g. a trailing
    // thought) is an action.
    let answerAt = -1;
    for (let k = turn.length - 1; k >= 0; k--) {
      if (turn[k].role === "assistant" && hasText(turn[k]) && !(turn[k].toolCalls?.length)) { answerAt = k; break; }
    }
    const actions = turn.filter((_, k) => k !== answerAt);
    if (actions.length) {
      const key = `turn-${turn[0].id}`;
      lastGroupKey = key;
      rows.push(messageGroup({ key, messages: actions, wrapper: ActionsGroup }));
    }
    if (answerAt >= 0) rows.push(messageRow(turn[answerAt]));
    i = j;
  }
  return rows;
}

function ActionsGroup({
  groupKey, messages, children, state, setState,
}: { groupKey: string; messages: any[]; children: React.ReactNode; state: boolean | undefined; setState: (v: boolean) => void }) {
  const running = useContext(RunningContext);
  const live = running && groupKey === lastGroupKey;
  const open = state ?? live;          // the user's choice wins; otherwise open only while it is working
  const tools = messages.reduce((n, m) => n + (m.role === "assistant" ? (m.toolCalls?.length ?? 0) : 0), 0);
  const thoughts = messages.filter((m) => m.role === "reasoning").length;
  const label = live
    ? `Working… ${tools} step${tools === 1 ? "" : "s"}`
    : tools
    ? `Worked through ${tools} step${tools === 1 ? "" : "s"}`
    : "Thought it through";
  return (
    <div className={`turn${open ? " open" : ""}${live ? " live" : ""}`}>
      <button className="turn-head" onClick={() => setState(!open)} aria-expanded={open}>
        <ChevronRight size={14} className="chev" />
        <span className="step-icon tone-agent">{live ? <Loader2 size={13} className="spin" /> : <ListChecks size={13} />}</span>
        <span className="turn-label">{label}</span>
        {thoughts > 0 && <span className="turn-meta"><Brain size={12} /> {thoughts}</span>}
      </button>
      {open && <div className="turn-body">{children}</div>}
    </div>
  );
}
