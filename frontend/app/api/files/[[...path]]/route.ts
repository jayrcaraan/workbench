// Same-origin pass-through to the agent service's read-only /files API (list + preview).
import { NextRequest } from "next/server";

export const dynamic = "force-dynamic";

const AGENT_BASE = (process.env.AGENT_BASE_URL || "http://localhost:8000").replace(/\/$/, "");

export async function GET(req: NextRequest, { params }: { params: { path?: string[] } }) {
  const tail = (params.path ?? []).map(encodeURIComponent).join("/");
  const target = `${AGENT_BASE}/files${tail ? `/${tail}` : ""}${req.nextUrl.search}`;
  try {
    const upstream = await fetch(target, { cache: "no-store" });
    return new Response(upstream.body, {
      status: upstream.status,
      headers: { "content-type": upstream.headers.get("content-type") ?? "application/json" },
    });
  } catch (e: any) {
    return Response.json({ detail: `Agent service unreachable: ${e?.message ?? e}` }, { status: 502 });
  }
}
