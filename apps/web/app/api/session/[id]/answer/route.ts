import { NextResponse } from "next/server";
import { serverEnv } from "@/lib/env";

// Server-side proxy to the agent's text-answer endpoint. Keeps AGENT_API_URL
// server-only and avoids CORS. Never prerender.
export const dynamic = "force-dynamic";

/**
 * POST /api/session/[id]/answer — record one typed answer (text-interview path).
 * Body: { question_id: string, transcript: string, duration_sec?: number }.
 * Proxies to `POST ${AGENT_API_URL}/api/session/{id}/answer`.
 */
export async function POST(
  request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const body = await request.json().catch(() => null);
  if (body === null) {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  try {
    const upstream = await fetch(
      `${serverEnv.agentApiUrl}/api/session/${encodeURIComponent(id)}/answer`,
      {
        method: "POST",
        headers: { "content-type": "application/json", accept: "application/json" },
        body: JSON.stringify(body),
        cache: "no-store",
        signal: AbortSignal.timeout(15_000),
      },
    );
    const json = await upstream.json().catch(() => null);
    if (json === null) {
      return NextResponse.json({ error: "Agent unreachable" }, { status: 503 });
    }
    return NextResponse.json(json, { status: upstream.status });
  } catch {
    return NextResponse.json({ error: "Agent unreachable" }, { status: 503 });
  }
}
