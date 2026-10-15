"use client";

import React, { useCallback, useEffect, useState } from "react";
import { callRoute } from "@/lib/appClient";
import type { Item, MetricsSpec } from "@/lib/uiSpec";

function fmt(v: unknown, f: Item["format"]): string {
  if (v == null) return "—";
  const n = Number(v);
  if (f === "text" || Number.isNaN(n)) return String(v);
  if (f === "currency") return n.toLocaleString(undefined, { style: "currency", currency: "USD" });
  if (f === "percent") return `${(n * 100).toFixed(1)}%`;
  return n.toLocaleString();
}

export function Metrics({ appId, spec }: { appId: string; spec: MetricsSpec }) {
  const [data, setData] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const res = await callRoute<any>(appId, spec.source);
      setData(Array.isArray(res) ? res[0] ?? {} : res ?? {});
      setError(null);
    } catch (e: any) {
      setError(e.message);
    }
  }, [appId, spec.source]);

  useEffect(() => {
    load();
    if (!spec.refresh_s) return;
    const t = setInterval(load, spec.refresh_s * 1000);
    return () => clearInterval(t);
  }, [load, spec.refresh_s]);

  return (
    <div className="app-card">
      {error && <div className="banner error">Could not load metrics: {error}</div>}
      <div className="metrics">
        {spec.items.map((m) => (
          <div className="metric" key={m.key}>
            <div className="metric-value">{data ? fmt(data[m.key], m.format) : "…"}</div>
            <div className="muted">{m.label || m.key}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
