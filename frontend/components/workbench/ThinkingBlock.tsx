"use client";

import React from "react";
import { Brain, ChevronRight } from "lucide-react";

/** The model's reasoning: always collapsed, opened only by the user. Replaces CopilotKit's auto-opening block. */
export function ThinkingBlock({ message, isRunning, isLatest }: { message: any; isRunning?: boolean; isLatest?: boolean }) {
  const text = typeof message?.content === "string" ? message.content : "";
  const live = !!isRunning && !!isLatest;
  const words = text.trim() ? text.trim().split(/\s+/).length : 0;
  return (
    <details className="think">
      <summary>
        <ChevronRight size={13} className="chev" />
        <span className="step-icon tone-think"><Brain size={13} /></span>
        <span className="step-label">{live ? "Thinking…" : "Thought"}</span>
        {words > 0 && <span className="think-len">{words} words</span>}
        {live && <span className="think-dot" />}
      </summary>
      {text && <div className="think-body">{text}</div>}
    </details>
  );
}
