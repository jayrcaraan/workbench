import type { Route } from "./uiSpec";

/** Same-origin URL of an app route. Goes browser -> Next -> agent service -> sandbox. */
export function appUrl(appId: string, path: string): string {
  const [sandboxId, name] = appId.split("/");
  const clean = path.startsWith("/") ? path : `/${path}`;
  return `/api/apps/${sandboxId}/${name}${clean}`;
}

export class AppError extends Error {
  constructor(public status: number, message: string, public code?: string) {
    super(message);
  }
}

/** Raised on the window when an app's sandbox is gone, so the workspace can offer to resume it. */
export const APP_DEAD_EVENT = "workbench:app-dead";

/** Replaces `{field}` placeholders with values from `row` (URL-encoded). */
export function fillPath(path: string, row?: Record<string, unknown>): string {
  return path.replace(/\{(\w+)\}/g, (_, k) => encodeURIComponent(String(row?.[k] ?? "")));
}

export async function callRoute<T = unknown>(
  appId: string,
  route: Route,
  opts: { row?: Record<string, unknown>; body?: unknown; signal?: AbortSignal } = {}
): Promise<T> {
  const method = route.method ?? "GET";
  const res = await fetch(appUrl(appId, fillPath(route.path, opts.row)), {
    method,
    headers: opts.body !== undefined ? { "content-type": "application/json" } : undefined,
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
    signal: opts.signal,
  });
  const text = await res.text();
  if (!res.ok) {
    let msg = text;
    let code: string | undefined;
    try {
      const j = JSON.parse(text);
      code = typeof j.error === "string" ? j.error : undefined;
      msg = j.message || j.detail || j.error || text;
      if (typeof msg !== "string") msg = JSON.stringify(msg);
    } catch {}
    if (code === "sandbox_not_found" || code === "app_not_found") {
      window.dispatchEvent(new CustomEvent(APP_DEAD_EVENT, { detail: { appId } }));
    }
    throw new AppError(res.status, msg || res.statusText, code);
  }
  if (!text) return undefined as T;
  try {
    return JSON.parse(text) as T;
  } catch {
    return text as unknown as T;
  }
}

/** Pulls the row array out of a list response (array, or object holding one). */
export function extractRows(data: unknown, rowsPath?: string): Record<string, unknown>[] {
  if (Array.isArray(data)) return data as Record<string, unknown>[];
  if (data && typeof data === "object") {
    const obj = data as Record<string, unknown>;
    if (rowsPath && Array.isArray(obj[rowsPath])) return obj[rowsPath] as Record<string, unknown>[];
    const first = Object.values(obj).find(Array.isArray);
    if (first) return first as Record<string, unknown>[];
  }
  return [];
}

/** Parses clipboard text (TSV, or CSV when there are no tabs) into rows of cells. */
export function parseClipboard(text: string): string[][] {
  const lines = text.replace(/\r\n?/g, "\n").split("\n").filter((l) => l.trim() !== "");
  const delim = lines.some((l) => l.includes("\t")) ? "\t" : ",";
  return lines.map((l) => l.split(delim).map((c) => c.trim().replace(/^"(.*)"$/, "$1")));
}
