"use client";

import React, { useMemo, useState } from "react";
import { AlertTriangle, ArrowDownRight, ArrowUpRight, CheckCircle2, Download, Info, Search, TriangleAlert } from "lucide-react";
import { Badge, Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { DashboardSpec, Panel } from "@/lib/uiSpec";

interface Result {
  columns: string[];
  rows: unknown[][];
  truncated?: boolean;
  error?: string;
}

const PALETTE = ["var(--c1)", "var(--c2)", "var(--c3)", "var(--c4)", "var(--c5)"];

function fmt(v: unknown, f: Panel["format"] = "number", compact = false): string {
  if (v === null || v === undefined) return "—";
  const n = Number(v);
  if (f === "text" || Number.isNaN(n) || typeof v === "boolean") return String(v);
  if (f === "currency")
    return n.toLocaleString(undefined, { style: "currency", currency: "USD", maximumFractionDigits: compact ? 1 : 0, notation: compact ? "compact" : "standard" });
  if (f === "percent") return `${(n * 100).toFixed(1)}%`;
  if (compact && Math.abs(n) >= 10000) return n.toLocaleString(undefined, { notation: "compact", maximumFractionDigits: 1 });
  return Math.abs(n) >= 1000 ? n.toLocaleString(undefined, { maximumFractionDigits: 1 }) : String(Math.round(n * 100) / 100);
}

const colIndex = (r: Result, name: string | null | undefined, fallback: number) => {
  const i = name ? r.columns.indexOf(name) : -1;
  return i >= 0 ? i : Math.min(fallback, Math.max(r.columns.length - 1, 0));
};
const num = (v: unknown) => (typeof v === "number" ? v : Number(v));

/* ---------------------------------------------------------------- stat */
function Sparkline({ values }: { values: number[] }) {
  if (values.length < 2) return null;
  const min = Math.min(...values), max = Math.max(...values), span = max - min || 1;
  const W = 120, H = 36;
  const pts = values.map((v, i) => `${(i / (values.length - 1)) * W},${H - 3 - ((v - min) / span) * (H - 6)}`).join(" ");
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="spark" preserveAspectRatio="none" aria-hidden>
      <polyline points={pts} fill="none" stroke="var(--c1)" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

function Stat({ r, p }: { r: Result; p: Panel }) {
  const yi = colIndex(r, p.y, 0);
  const series = p.x ? r.rows.map((row) => num(row[yi])).filter((n) => !Number.isNaN(n)) : [];
  const value = series.length ? series[series.length - 1] : r.rows[0][yi];
  const prev = series.length > 1 ? series[series.length - 2] : null;
  const delta = prev !== null && prev !== 0 ? (num(value) - prev) / Math.abs(prev) : null;
  return (
    <div className="stat">
      <div className="stat-value">{fmt(value, p.format, true)}</div>
      <div className="stat-foot">
        {delta !== null && (
          <Badge tone={delta >= 0 ? "success" : "destructive"}>
            {delta >= 0 ? <ArrowUpRight size={12} /> : <ArrowDownRight size={12} />}
            {Math.abs(delta * 100).toFixed(1)}%
          </Badge>
        )}
        <Sparkline values={series} />
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------- charts */
function Bars({ r, p }: { r: Result; p: Panel }) {
  const xi = colIndex(r, p.x, 0), yi = colIndex(r, p.y, 1);
  const rows = r.rows.slice(0, 20);
  const max = Math.max(1e-9, ...rows.map((row) => Math.abs(num(row[yi])) || 0));
  return (
    <div className="bars">
      {rows.map((row, i) => (
        <div className="bar-row" key={i}>
          <span className="bar-label" title={String(row[xi])}>{String(row[xi])}</span>
          <span className="bar-track"><span className="bar-fill" style={{ width: `${((Math.abs(num(row[yi])) || 0) / max) * 100}%` }} /></span>
          <span className="bar-value">{fmt(row[yi], p.format, true)}</span>
        </div>
      ))}
    </div>
  );
}

function Chart({ r, p, kind }: { r: Result; p: Panel; kind: "line" | "column" }) {
  const xi = colIndex(r, p.x, 0), yi = colIndex(r, p.y, 1);
  const rows = r.rows.slice(0, 120);
  const ys = rows.map((row) => num(row[yi]));
  const [hover, setHover] = useState<number | null>(null);
  if (ys.length < 1 || ys.every((v) => Number.isNaN(v))) return <div className="muted">Nothing to plot.</div>;
  const W = 640, H = 220, L = 44, R = 10, T = 12, B = 26;
  const max = Math.max(0, ...ys.filter((v) => !Number.isNaN(v)));
  const min = Math.min(0, ...ys.filter((v) => !Number.isNaN(v)));
  const span = max - min || 1;
  const sx = (i: number) => (kind === "line" ? L + (i / Math.max(ys.length - 1, 1)) * (W - L - R) : L + ((i + 0.5) / ys.length) * (W - L - R));
  const sy = (v: number) => T + (1 - (v - min) / span) * (H - T - B);
  const ticks = [0, 0.5, 1].map((t) => min + t * span);
  const labelEvery = Math.ceil(rows.length / 6);
  const path = ys.map((v, i) => `${i === 0 ? "M" : "L"}${sx(i)},${sy(v)}`).join(" ");
  const bw = Math.max(4, ((W - L - R) / ys.length) * 0.62);
  return (
    <div className="chart-wrap" onMouseLeave={() => setHover(null)}>
      <svg viewBox={`0 0 ${W} ${H}`} className="chart" role="img" aria-label={p.title}>
        <defs>
          <linearGradient id={`g-${p.title.replace(/\W/g, "")}`} x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="var(--c1)" stopOpacity=".28" />
            <stop offset="100%" stopColor="var(--c1)" stopOpacity="0" />
          </linearGradient>
        </defs>
        {ticks.map((t, i) => (
          <g key={i}>
            <line x1={L} x2={W - R} y1={sy(t)} y2={sy(t)} className="grid-line" />
            <text x={L - 8} y={sy(t) + 4} textAnchor="end" className="axis-text">{fmt(t, p.format, true)}</text>
          </g>
        ))}
        {kind === "line" ? (
          <>
            <path d={`${path} L${sx(ys.length - 1)},${sy(min)} L${sx(0)},${sy(min)} Z`} fill={`url(#g-${p.title.replace(/\W/g, "")})`} />
            <path d={path} fill="none" stroke="var(--c1)" strokeWidth="2.25" strokeLinejoin="round" strokeLinecap="round" />
          </>
        ) : (
          ys.map((v, i) => (
            <rect key={i} x={sx(i) - bw / 2} width={bw} y={Math.min(sy(v), sy(0))} height={Math.max(2, Math.abs(sy(v) - sy(0)))}
                  rx="3" fill="var(--c1)" opacity={hover === null || hover === i ? 1 : 0.45} />
          ))
        )}
        {rows.map((row, i) => (i % labelEvery === 0 ? (
          <text key={i} x={sx(i)} y={H - 6} textAnchor="middle" className="axis-text">{String(row[xi]).slice(0, 10)}</text>
        ) : null))}
        {hover !== null && kind === "line" && <circle cx={sx(hover)} cy={sy(ys[hover])} r="4.5" fill="var(--surface)" stroke="var(--c1)" strokeWidth="2.25" />}
        {rows.map((_, i) => (
          <rect key={`h${i}`} x={sx(i) - (W - L - R) / ys.length / 2} y={T} width={(W - L - R) / ys.length} height={H - T - B}
                fill="transparent" onMouseEnter={() => setHover(i)} />
        ))}
      </svg>
      {hover !== null && (
        <div className="chart-tip" style={{ left: `${(sx(hover) / W) * 100}%` }}>
          <span className="muted">{String(rows[hover][xi])}</span>
          <strong>{fmt(ys[hover], p.format)}</strong>
        </div>
      )}
    </div>
  );
}

function Donut({ r, p }: { r: Result; p: Panel }) {
  const xi = colIndex(r, p.x, 0), yi = colIndex(r, p.y, 1);
  const items = r.rows.slice(0, 8).map((row) => ({ label: String(row[xi]), v: Math.max(0, num(row[yi]) || 0) }));
  const total = items.reduce((a, b) => a + b.v, 0) || 1;
  const R = 52, C = 2 * Math.PI * R;
  let offset = 0;
  return (
    <div className="donut">
      <svg viewBox="0 0 140 140" className="donut-svg" role="img" aria-label={p.title}>
        <circle cx="70" cy="70" r={R} fill="none" stroke="var(--track)" strokeWidth="16" />
        {items.map((it, i) => {
          const len = (it.v / total) * C;
          const el = (
            <circle key={i} cx="70" cy="70" r={R} fill="none" stroke={PALETTE[i % PALETTE.length]} strokeWidth="16"
                    strokeDasharray={`${Math.max(len - 1.5, 0)} ${C - Math.max(len - 1.5, 0)}`} strokeDashoffset={-offset}
                    transform="rotate(-90 70 70)" />
          );
          offset += len;
          return el;
        })}
        <text x="70" y="68" textAnchor="middle" className="donut-total">{fmt(total, p.format, true)}</text>
        <text x="70" y="84" textAnchor="middle" className="axis-text">total</text>
      </svg>
      <ul className="legend">
        {items.map((it, i) => (
          <li key={i}>
            <span className="dot" style={{ background: PALETTE[i % PALETTE.length] }} />
            <span className="legend-label">{it.label}</span>
            <span className="legend-value">{((it.v / total) * 100).toFixed(0)}%</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Progress({ r, p }: { r: Result; p: Panel }) {
  const yi = colIndex(r, p.y, 0);
  const row = r.rows[0];
  const value = num(row[yi]);
  const ti = p.target ? r.columns.indexOf(p.target) : -1;
  const target = ti >= 0 ? num(row[ti]) : Number(p.target);
  const pct = target > 0 ? Math.max(0, Math.min(1, value / target)) : 0;
  return (
    <div className="progress">
      <div className="progress-top">
        <span className="stat-value">{Math.round(pct * 100)}%</span>
        <span className="muted">{fmt(value, p.format, true)} of {Number.isNaN(target) ? "—" : fmt(target, p.format, true)}</span>
      </div>
      <div className="progress-track"><div className="progress-fill" style={{ width: `${pct * 100}%` }} /></div>
    </div>
  );
}

function Details({ r }: { r: Result }) {
  return (
    <dl className="details">
      {r.columns.map((c, i) => (
        <div key={c}>
          <dt>{c.replace(/_/g, " ")}</dt>
          <dd>{r.rows[0][i] === null || r.rows[0][i] === undefined ? "—" : String(r.rows[0][i])}</dd>
        </div>
      ))}
    </dl>
  );
}

const STATUSISH = /^(active|open|done|closed|blocked|pending|lead|churned|won|lost|paid|unpaid|todo|in progress|reading|want)$/i;
const statusTone = (v: string) =>
  /^(active|done|closed|paid|won)$/i.test(v) ? "success" : /^(blocked|churned|lost|unpaid)$/i.test(v) ? "destructive" : /^(pending|lead|todo|open|in progress|reading|want)$/i.test(v) ? "warning" : "secondary";

function DataTable({ r, p }: { r: Result; p: Panel }) {
  const [q, setQ] = useState("");
  const rows = useMemo(() => {
    const t = q.trim().toLowerCase();
    return t ? r.rows.filter((row) => row.some((v) => String(v ?? "").toLowerCase().includes(t))) : r.rows;
  }, [r.rows, q]);
  const csv = () => {
    const esc = (v: unknown) => (/[",\n]/.test(String(v ?? "")) ? `"${String(v).replace(/"/g, '""')}"` : String(v ?? ""));
    const text = [r.columns.map(esc).join(","), ...r.rows.map((row) => row.map(esc).join(","))].join("\n");
    const url = URL.createObjectURL(new Blob([text], { type: "text/csv" }));
    Object.assign(document.createElement("a"), { href: url, download: `${p.title}.csv` }).click();
    URL.revokeObjectURL(url);
  };
  return (
    <div className="dt">
      <div className="dt-bar">
        <label className="search">
          <Search size={14} />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Filter rows…" aria-label="Filter rows" />
        </label>
        <span className="muted">{rows.length}{r.truncated ? "+" : ""} row{rows.length === 1 ? "" : "s"}</span>
        <button className="icon-btn" title="Download CSV" onClick={csv}><Download size={15} /></button>
      </div>
      <div className="table-wrap panel-table">
        <table>
          <thead><tr>{r.columns.map((c) => <th key={c}>{c.replace(/_/g, " ")}</th>)}</tr></thead>
          <tbody>
            {rows.slice(0, 200).map((row, i) => (
              <tr key={i}>
                {row.map((v, j) => {
                  const isNum = typeof v === "number";
                  const s = String(v ?? "—");
                  return (
                    <td key={j} className={isNum ? "num" : ""}>
                      {isNum ? fmt(v, p.format === "text" ? "number" : p.format) : typeof v === "string" && STATUSISH.test(v) ? <Badge tone={statusTone(v) as any}>{s}</Badge> : s}
                    </td>
                  );
                })}
              </tr>
            ))}
            {!rows.length && <tr><td colSpan={r.columns.length} className="empty-row">No matching rows.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------- card */
const WIDE: Panel["type"][] = ["table", "line", "column"];
const NOTE_ICON = { info: Info, success: CheckCircle2, warning: AlertTriangle } as const;

function PanelCard({ panel }: { panel: Panel }) {
  const type = panel.type ?? "table";
  const data = panel.result as Result | undefined;
  const wide = panel.wide || WIDE.includes(type);

  if (type === "note") {
    const Icon = NOTE_ICON[panel.tone ?? "info"];
    const parts = (panel.text ?? "").split(/(\*\*[^*]+\*\*)/g);
    return (
      <Card className={`note note-${panel.tone ?? "info"}${wide ? " wide" : ""}`}>
        <CardContent className="note-body">
          <Icon size={18} />
          <div>
            <div className="card-title">{panel.title}</div>
            <p>{parts.map((s, i) => (s.startsWith("**") ? <strong key={i}>{s.slice(2, -2)}</strong> : <span key={i}>{s}</span>))}</p>
          </div>
        </CardContent>
      </Card>
    );
  }

  let body: React.ReactNode;
  if (!data) body = <div className="muted">No result.</div>;
  else if (data.error) body = <div className="banner error"><TriangleAlert size={14} /> {data.error}</div>;
  else if (!data.rows.length) body = <div className="muted">No rows.</div>;
  else if (type === "metric") body = <Stat r={data} p={panel} />;
  else if (type === "bar") body = <Bars r={data} p={panel} />;
  else if (type === "line" || type === "column") body = <Chart r={data} p={panel} kind={type} />;
  else if (type === "donut") body = <Donut r={data} p={panel} />;
  else if (type === "progress") body = <Progress r={data} p={panel} />;
  else if (type === "details") body = <Details r={data} />;
  else body = <DataTable r={data} p={panel} />;

  return (
    <Card className={`${wide ? "wide" : ""} card-${type}`}>
      <CardHeader>
        <div>
          <CardTitle>{panel.title}</CardTitle>
          {panel.description && <CardDescription>{panel.description}</CardDescription>}
        </div>
        {data?.truncated && <CardAction><Badge tone="outline">truncated</Badge></CardAction>}
      </CardHeader>
      <CardContent>{body}</CardContent>
    </Card>
  );
}

/** A grid of cards. The agent service ran each SQL read-only in the sandbox and embedded the rows. */
export function Dashboard({ spec }: { spec: DashboardSpec }) {
  return (
    <div className="dashboard">
      {spec.panels.map((p, i) => <PanelCard key={`${i}:${p.title}`} panel={p} />)}
    </div>
  );
}
