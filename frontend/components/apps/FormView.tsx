"use client";

import React, { useState } from "react";
import { callRoute } from "@/lib/appClient";
import type { FormSpec } from "@/lib/uiSpec";

export function FormView({ appId, spec }: { appId: string; spec: FormSpec }) {
  const [values, setValues] = useState<Record<string, unknown>>({});
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; text: string } | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setResult(null);
    const body: Record<string, unknown> = {};
    spec.fields.forEach((f) => {
      const v = values[f.key];
      if (v === undefined || v === "") return;
      body[f.key] = f.type === "number" ? Number(v) : v;
    });
    try {
      const res = await callRoute(appId, spec.submit, { body });
      setResult({ ok: true, text: typeof res === "string" ? res : JSON.stringify(res, null, 2) ?? "Done." });
      setValues({});
    } catch (err: any) {
      setResult({ ok: false, text: err.message });
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="app-card form" onSubmit={submit}>
      {spec.fields.map((f) => (
        <label key={f.key}>
          <span>
            {f.label || f.key}
            {f.required && " *"}
          </span>
          {f.type === "textarea" ? (
            <textarea
              required={f.required}
              value={String(values[f.key] ?? "")}
              onChange={(e) => setValues((v) => ({ ...v, [f.key]: e.target.value }))}
            />
          ) : f.type === "boolean" ? (
            <input
              type="checkbox"
              checked={!!values[f.key]}
              onChange={(e) => setValues((v) => ({ ...v, [f.key]: e.target.checked }))}
            />
          ) : (
            <input
              required={f.required}
              type={f.type === "number" ? "number" : f.type === "date" ? "date" : "text"}
              value={String(values[f.key] ?? "")}
              onChange={(e) => setValues((v) => ({ ...v, [f.key]: e.target.value }))}
            />
          )}
        </label>
      ))}
      <button className="btn primary" disabled={busy}>
        {busy ? "Sending…" : "Submit"}
      </button>
      {result && <pre className={`banner ${result.ok ? "" : "error"}`}>{result.text}</pre>}
    </form>
  );
}
