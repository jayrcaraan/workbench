"use client";

import React from "react";
import type { PublishedApp } from "@/lib/uiSpec";
import { DataTable } from "./DataTable";
import { FormView } from "./FormView";
import { Metrics } from "./Metrics";
import { Frame } from "./Frame";
import { Dashboard } from "./Dashboard";
import { ApiSheet } from "@/components/sheets/ApiSheet";
import { Badge, Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

class Boundary extends React.Component<{ children: React.ReactNode }, { error?: string }> {
  state: { error?: string } = {};
  static getDerivedStateFromError(e: Error) {
    return { error: e.message };
  }
  render() {
    if (this.state.error) return <div className="app-card banner error">This view crashed: {this.state.error}</div>;
    return this.props.children;
  }
}

const FRAME: Record<string, { label: string; hint: string }> = {
  table: { label: "Table", hint: "Edit cells inline, or paste rows from a spreadsheet." },
  form: { label: "Form", hint: "Submitting sends the values straight to the app." },
  metrics: { label: "Metrics", hint: "Live numbers read from the app." },
  iframe: { label: "Embedded app", hint: "Served directly from the sandbox." },
};

function Framed({ kind, title, children }: { kind: string; title: string; children: React.ReactNode }) {
  const f = FRAME[kind];
  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>{title}</CardTitle>
          {f && <CardDescription>{f.hint}</CardDescription>}
        </div>
        {f && <CardAction><Badge tone="outline">{f.label}</Badge></CardAction>}
      </CardHeader>
      <CardContent className="card-flat">{children}</CardContent>
    </Card>
  );
}

export function AppView({ app }: { app: PublishedApp }) {
  const ui = app.ui;
  let view: React.ReactNode;
  switch (ui.kind) {
    case "table":
      view = <DataTable appId={app.app_id} spec={ui} />;
      break;
    case "sheet":
      view = <ApiSheet appId={app.app_id} spec={ui} />;
      break;
    case "dashboard":
      view = <Dashboard spec={ui} />;
      break;
    case "form":
      view = <FormView appId={app.app_id} spec={ui} />;
      break;
    case "metrics":
      view = <Metrics appId={app.app_id} spec={ui} />;
      break;
    case "iframe":
      view = <Frame spec={ui} />;
      break;
    default:
      view = (
        <div className="app-card banner">
          Unsupported component “{(ui as any)?.kind}”. Ask the agent for a table, form, metrics or iframe view.
        </div>
      );
  }
  const framed = ["table", "form", "metrics", "iframe"].includes(ui.kind);
  return (
    <Boundary key={app.app_id}>
      {framed ? <Framed kind={ui.kind} title={(ui as { title?: string }).title ?? app.title}>{view}</Framed> : view}
    </Boundary>
  );
}
