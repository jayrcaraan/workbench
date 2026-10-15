"use client";

import React, { useEffect, useMemo, useState } from "react";
import { Database, Loader2, Sparkles } from "lucide-react";
import { Badge, Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { filesApi, humanSize, isDataFile, type Preview } from "@/lib/files";
import { parseClipboard } from "@/lib/appClient";

const BINARY_DATA = [".duckdb", ".db", ".sqlite", ".sqlite3", ".parquet"];

/** Preview of one file from the user's home: text, CSV as a table, JSON pretty-printed, images; data files can be handed to the agent. */
export function FileViewer({
  sandboxId, path, onAsk,
}: { sandboxId: string; path: string; onAsk: (text: string) => void }) {
  const [p, setP] = useState<Preview | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    setP(null);
    setError(null);
    filesApi.read(sandboxId, path).then((r) => live && setP(r)).catch((e) => live && setError(e.message));
    return () => { live = false; };
  }, [sandboxId, path]);

  const name = path.split("/").pop() ?? path;
  const kind = useMemo(() => {
    if (!p) return "loading";
    if (p.image_b64) return "image";
    if (p.text === null) return "binary";
    if (/\.(csv|tsv)$/i.test(p.suffix ? name : "")) return "table";
    if (/\.json$/i.test(name)) return "json";
    return "text";
  }, [p, name]);

  const body = (() => {
    if (error) return <div className="banner error">{error}</div>;
    if (!p) return <div className="muted"><Loader2 size={14} className="spin" /> Loading…</div>;
    if (kind === "image") return <img className="fv-image" alt={name} src={`data:${p.mime};base64,${p.image_b64}`} />;
    if (kind === "binary")
      return (
        <div className="fv-binary">
          <Database size={22} />
          <p>{BINARY_DATA.some((s) => name.toLowerCase().endsWith(s)) ? "A data file." : "A binary file."} It can't be previewed as text.</p>
        </div>
      );
    if (kind === "table") {
      const rows = parseClipboard(p.text ?? "");
      const [head, ...rest] = rows;
      return (
        <div className="table-wrap panel-table">
          <table>
            <thead><tr>{head?.map((c, i) => <th key={i}>{c}</th>)}</tr></thead>
            <tbody>{rest.slice(0, 200).map((r, i) => <tr key={i}>{r.map((c, j) => <td key={j}>{c}</td>)}</tr>)}</tbody>
          </table>
          {rest.length > 200 && <div className="muted pad-sm">Showing the first 200 of {rest.length} rows.</div>}
        </div>
      );
    }
    let text = p.text ?? "";
    if (kind === "json") {
      try { text = JSON.stringify(JSON.parse(text), null, 2); } catch {}
    }
    return <pre className="fv-text">{text}</pre>;
  })();

  return (
    <div className="fv">
      <Card>
        <CardHeader>
          <div>
            <CardTitle>{name}</CardTitle>
            <CardDescription>{path}</CardDescription>
          </div>
          <CardAction>
            {p && <Badge tone="outline">{humanSize(p.size)}</Badge>}
            {p?.truncated && <Badge tone="warning">preview truncated</Badge>}
            {isDataFile(name) && (
              <button className="btn" onClick={() => onAsk(`Show me a dashboard of ${path} in my home directory: what it contains, row counts, and the most useful breakdowns.`)}>
                <Sparkles size={14} /> Explore with agent
              </button>
            )}
          </CardAction>
        </CardHeader>
        <CardContent>{body}</CardContent>
      </Card>
    </div>
  );
}
