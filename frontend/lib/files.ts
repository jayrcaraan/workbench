// Client for the read-only file browser API (the user's home, via any live sandbox).

export interface Entry {
  name: string;
  type: "dir" | "file" | "symlink" | string;
  size: number;
  mtime: number;
}
export interface Preview {
  path: string;
  size: number;
  truncated: boolean;
  mime: string;
  suffix: string;
  text: string | null;
  image_b64?: string;
}

async function get<T>(url: string): Promise<T> {
  const res = await fetch(url, { cache: "no-store" });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof body.detail === "string" ? body.detail : `HTTP ${res.status}`);
  return body as T;
}

const q = (o: Record<string, string>) => new URLSearchParams(o).toString();

export const filesApi = {
  list: (sandboxId: string, path = "") =>
    get<{ path: string; entries: Entry[] }>(`/api/files?${q({ sandbox_id: sandboxId, path })}`),
  read: (sandboxId: string, path: string) => get<Preview>(`/api/files/read?${q({ sandbox_id: sandboxId, path })}`),
};

export const DATA_SUFFIXES = [".csv", ".tsv", ".parquet", ".duckdb", ".db", ".sqlite", ".sqlite3", ".json", ".jsonl", ".ndjson"];
export const isDataFile = (name: string) => DATA_SUFFIXES.some((s) => name.toLowerCase().endsWith(s));

export function humanSize(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 ** 2) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 ** 2).toFixed(1)} MB`;
}
