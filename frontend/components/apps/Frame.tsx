"use client";

import React from "react";
import type { IframeSpec } from "@/lib/uiSpec";

// The app serves its own UI at its own origin, so this is the one component that
// loads it directly (the URL, minted by the agent service, carries the sandbox token).
export function Frame({ spec }: { spec: IframeSpec }) {
  if (!spec.url) return <div className="app-card banner error">This app has no URL yet.</div>;
  return (
    <div className="app-card frame">
      <div className="app-toolbar">
        <span className="muted">Served directly from the sandbox</span>
        <a className="btn" href={spec.url} target="_blank" rel="noreferrer">
          Open in new tab
        </a>
      </div>
      <iframe src={spec.url} title={spec.title} />
    </div>
  );
}
