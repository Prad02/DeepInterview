import { promises as fs } from "node:fs";
import path from "node:path";
import { z } from "zod";

/**
 * Local candidate profile — the user's info saved once and auto-filled into the
 * setup screen on every run. Stored as a gitignored JSON file on disk (OSS,
 * single-user, self-hosted). When this moves to a hosted/multi-tenant domain,
 * swap the storage backend behind the same read/save functions.
 */
export const ProfileSchema = z.object({
  // Display name / candidate name (optional).
  name: z.string().max(200).default(""),
  // The CV / background text used to tailor the interview.
  cvText: z.string().max(2_000_000).default(""),
  // ISO timestamp of the last save (informational).
  updatedAt: z.string().optional(),
});
export type Profile = z.infer<typeof ProfileSchema>;

const EMPTY_PROFILE: Profile = { name: "", cvText: "" };

/**
 * Resolve the profile file path. Defaults to `profile.json` at the repo root
 * (one level above `apps/`), overridable with PROFILE_PATH. The dev server runs
 * with cwd = `apps/web`, so we walk up to the workspace root; if that lookup
 * fails we fall back to cwd so a read/write never throws on path resolution.
 */
export function profilePath(): string {
  if (process.env.PROFILE_PATH) return path.resolve(process.env.PROFILE_PATH);
  // apps/web -> repo root
  const guess = path.resolve(process.cwd(), "..", "..", "profile.json");
  return guess;
}

/** Read the saved profile, or an empty profile if none exists / is unreadable. */
export async function readProfile(): Promise<Profile> {
  try {
    const raw = await fs.readFile(profilePath(), "utf8");
    const parsed = ProfileSchema.safeParse(JSON.parse(raw));
    return parsed.success ? parsed.data : EMPTY_PROFILE;
  } catch {
    // Missing file / bad JSON — treat as "no profile yet", never throw.
    return EMPTY_PROFILE;
  }
}

/** Persist the profile to disk, stamping updatedAt. Returns the saved profile. */
export async function saveProfile(input: unknown): Promise<Profile> {
  const parsed = ProfileSchema.parse(input);
  const toSave: Profile = { ...parsed, updatedAt: new Date().toISOString() };
  await fs.writeFile(profilePath(), JSON.stringify(toSave, null, 2), "utf8");
  return toSave;
}
