// Same-origin pass-through to the agent service's /sessions API: session index, per-session sandbox and history.
import { NextRequest } from "next/server";

export const dynamic = "force-dynamic";

const AGENT_BASE = (process.env.AGENT_BASE_URL || "http://localhost:8000").replace(/\/$/, "");

async function forward(req: NextRequest, { params }: { params: { path?: string[] } }) {
  const tail = (params.path ?? []).map(encodeURIComponent).join("/");
  const target = `${AGENT_BASE}/sessions${tail ? `/${tail}` : ""}`;
  const hasBody = !["GET", "HEAD", "DELETE", "POST"].includes(req.method);
  try {
    const upstream = await fetch(target, {
      method: req.method,
      headers: hasBody ? { "content-type": "application/json" } : undefined,
      body: hasBody ? await req.arrayBuffer() : undefined,
      cache: "no-store",
    });
    return new Response(upstream.status === 204 ? null : upstream.body, {
      status: upstream.status,
      headers: { "content-type": upstream.headers.get("content-type") ?? "application/json" },
    });
  } catch (e: any) {
    return Response.json({ detail: `Agent service unreachable: ${e?.message ?? e}` }, { status: 502 });
  }
}

export const GET = forward;
export const POST = forward;
export const PUT = forward;
export const DELETE = forward;
