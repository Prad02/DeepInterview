import { NextResponse } from "next/server";
import { serverEnv } from "@/lib/env";

// Server-side proxy that triggers scoring for a session. Never prerender.
export const dynamic = "force-dynamic";

/**
 * POST /api/session/[id]/score — kick off scoring for a completed text
 * interview. Proxies to the agent's `POST ${AGENT_API_URL}/api/score`
 * ({ session_id }). Scoring re-runs are idempotent agent-side, so a retry is
 * safe. Returns the agent's ScoreResponse (or the resulting session status).
 */
export async function POST(
  _request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  try {
    const upstream = await fetch(`${serverEnv.agentApiUrl}/api/score`, {
      method: "POST",
      headers: { "content-type": "application/json", accept: "application/json" },
      body: JSON.stringify({ session_id: id }),
      cache: "no-store",
      // Scoring runs the full LLM pipeline; give it room.
      signal: AbortSignal.timeout(180_000),
    });
    const json = await upstream.json().catch(() => null);
    if (json === null) {
      return NextResponse.json({ error: "Agent unreachable" }, { status: 503 });
    }
    return NextResponse.json(json, { status: upstream.status });
  } catch {
    return NextResponse.json({ error: "Scoring failed" }, { status: 503 });
  }
}
