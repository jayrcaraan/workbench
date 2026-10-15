// User-defined spreadsheets: schema, row coercion and the API client.

export type FieldType = "text" | "number" | "currency" | "date" | "checkbox" | "select";

export interface SheetField {
  key: string;
  label: string;
  type: FieldType;
  options?: string[];
  editable?: boolean; // false: shown, not editable (ids, timestamps)
}
export type Row = Record<string, unknown>;
/** Parses pasted/typed text into the value a field of this type stores. */
export function coerce(field: SheetField, raw: string): unknown {
  const text = raw.trim();
  if (text === "") return field.type === "checkbox" ? false : null;
  switch (field.type) {
    case "number":
    case "currency": {
      const n = Number(text.replace(/[$,\s]/g, ""));
      return Number.isNaN(n) ? text : n; // keep invalid text so the cell can flag it
    }
    case "checkbox":
      return /^(true|yes|y|1|x|✓)$/i.test(text);
    case "date": {
      if (/^\d{4}-\d{2}-\d{2}$/.test(text)) return text;
      const d = new Date(text);
      if (Number.isNaN(d.getTime())) return text;
      // Local components: toISOString() would shift the day in timezones ahead of UTC.
      const pad = (n: number) => String(n).padStart(2, "0");
      return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
    }
    case "select":
      return field.options?.find((o) => o.toLowerCase() === text.toLowerCase()) ?? text;
    default:
      return text;
  }
}

export function isInvalid(field: SheetField, value: unknown): boolean {
  if (value === null || value === undefined || value === "") return false;
  if (field.type === "number" || field.type === "currency") return typeof value !== "number";
  // Apps often store timestamps in date columns ("2026-10-15T02:28:31"): the date part is what matters.
  if (field.type === "date") return !/^\d{4}-\d{2}-\d{2}([T ].*)?$/.test(String(value));
  if (field.type === "select") return !!field.options?.length && !field.options.includes(String(value));
  return false;
}

export function display(field: SheetField, value: unknown): string {
  if (value === null || value === undefined) return "";
  if (field.type === "currency" && typeof value === "number")
    return value.toLocaleString(undefined, { style: "currency", currency: "USD" });
  if (field.type === "number" && typeof value === "number") return value.toLocaleString();
  if (field.type === "date" && typeof value === "string") return value.slice(0, 10);
  return String(value);
}
