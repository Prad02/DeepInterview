import { NextResponse } from "next/server";
import { readProfile, saveProfile } from "@/lib/profile";

// Reads/writes a local file per request; never prerender.
export const dynamic = "force-dynamic";

/**
 * GET /api/profile — return the saved candidate profile (empty if none yet).
 * The setup screen calls this on load to auto-fill the CV.
 */
export async function GET() {
  const profile = await readProfile();
  return NextResponse.json(profile, { status: 200 });
}

/**
 * POST /api/profile — save the candidate profile to disk.
 * Body: { name?: string, cvText: string }.
 */
export async function POST(request: Request) {
  const body = await request.json().catch(() => null);
  if (body === null) {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }
  try {
    const saved = await saveProfile(body);
    return NextResponse.json(saved, { status: 200 });
  } catch (e) {
    const msg = e instanceof Error ? e.message : "Could not save profile";
    return NextResponse.json({ error: msg }, { status: 400 });
  }
}
