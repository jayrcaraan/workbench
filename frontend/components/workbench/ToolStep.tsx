"use client";

import React from "react";
import {
  BarChart3, BookOpen, Bot, Box, Check, ChevronRight, FileEdit, FilePlus2, FileText, FolderOpen, Globe, ListChecks,
  LayoutDashboard, Loader2, PackagePlus, Play, Power, Search, Terminal, Trash2, Wrench, X, type LucideIcon,
} from "lucide-react";

type Status = "inProgress" | "executing" | "complete";
interface Props {
  name: string;
  parameters: unknown;
  status: Status;
  result?: string;
}

type Tone = "skill" | "tool" | "sandbox" | "data" | "app" | "agent";

const str = (v: unknown) => (typeof v === "string" ? v : "");
const short = (s: string, n = 48) => (s.length > n ? `${s.slice(0, n - 1)}…` : s);

interface Action {
  label: string;
  icon: LucideIcon;
  tone: Tone;
}

/** What a tool call is, in a sentence, with an icon and a colour family (skill, sandbox, data, app...). */
function describe(name: string, p: Record<string, unknown>): Action {
  const tool = name.replace(/^sbx_/, "");
  const path = str(p.path ?? p.file_path);
  switch (tool) {
    case "read_file": {
      const skill = /^\/skills\/([^/]+)\//.exec(path);
      if (skill) return { label: `Using skill ${skill[1]}`, icon: BookOpen, tone: "skill" };
      return { label: path ? `Reading ${short(path)}` : "Reading a file", icon: FileText, tone: "tool" };
    }
    case "write_file": return { label: path ? `Writing ${short(path)}` : "Writing a file", icon: FilePlus2, tone: "sandbox" };
    case "edit_file": return { label: path ? `Editing ${short(path)}` : "Editing a file", icon: FileEdit, tone: "sandbox" };
    case "delete_file":
    case "delete": return { label: `Deleting ${short(path)}`, icon: Trash2, tone: "sandbox" };
    case "list_files":
    case "ls": return { label: `Listing ${short(path || "home")}`, icon: FolderOpen, tone: "tool" };
    case "glob":
    case "grep": return { label: `Searching ${short(str(p.pattern))}`, icon: Search, tone: "tool" };
    case "run_command":
      return { label: str(p.command) ? `Running ${short(str(p.command))}` : "Running a command", icon: Terminal, tone: "sandbox" };
    case "start_background":
      return { label: str(p.command) ? `Starting ${short(str(p.command))}` : "Starting a process", icon: Play, tone: "sandbox" };
    case "create_sandbox": return { label: "Creating a sandbox", icon: Box, tone: "sandbox" };
    case "destroy_sandbox": return { label: "Destroying the sandbox", icon: Power, tone: "sandbox" };
    case "get_sandbox_status": return { label: "Checking the sandbox", icon: Box, tone: "sandbox" };
    case "expose_port": {
      const port = p.internal_port ?? p.port;
      return { label: port ? `Exposing :${port} as ${str(p.name) || "app"}` : "Exposing an app", icon: Globe, tone: "app" };
    }
    case "unexpose_port": return { label: `Removing app ${str(p.name)}`, icon: Globe, tone: "app" };
    case "list_apps": return { label: "Listing apps", icon: Globe, tone: "app" };
    case "publish_app": return { label: `Publishing ${str(p.title) || str(p.name)}`, icon: LayoutDashboard, tone: "app" };
    case "show_dashboard": return { label: `Querying data for ${str(p.title) || "a dashboard"}`, icon: BarChart3, tone: "data" };
    case "install_reference": return { label: `Installing ${str(p.reference) || "a reference app"}`, icon: PackagePlus, tone: "sandbox" };
    case "write_todos": return { label: "Planning", icon: ListChecks, tone: "agent" };
    case "task": return { label: `Delegating to ${str(p.subagent_type) || "a subagent"}`, icon: Bot, tone: "agent" };
    default: return { label: tool.replace(/_/g, " "), icon: Wrench, tone: "tool" };
  }
}

function pretty(v: unknown): string {
  if (typeof v === "string") {
    try { return JSON.stringify(JSON.parse(v), null, 2); } catch { return v; }
  }
  return JSON.stringify(v, null, 2) ?? "";
}

/** A collapsible step row for one tool call: action icon, sentence, status, and the raw args/result on expand. */
export function ToolStep({ name, parameters, status, result }: Props) {
  const params = (parameters && typeof parameters === "object" ? parameters : {}) as Record<string, unknown>;
  const { label, icon: Icon, tone } = describe(name, params);
  const failed = status === "complete" && !!result && /^\s*(error|\{\s*"(status|error)":\s*"error)/i.test(result);
  const running = status !== "complete";
  return (
    <details className={`step${failed ? " failed" : ""}`}>
      <summary>
        <ChevronRight size={13} className="chev" />
        <span className={`step-icon tone-${tone}`}><Icon size={13} /></span>
        <span className="step-label">{label}</span>
        <span className="step-status">
          {running ? <Loader2 size={13} className="spin" /> : failed ? <X size={13} /> : <Check size={13} />}
        </span>
      </summary>
      <div className="step-body">
        <div className="muted">{name}</div>
        {str(params.command) && <pre className="cmd">{`$ ${str(params.command)}`}</pre>}
        <pre>{pretty(parameters)}</pre>
        {result !== undefined && <pre>{short(pretty(result), 2000)}</pre>}
      </div>
    </details>
  );
}
