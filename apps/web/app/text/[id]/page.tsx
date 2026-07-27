import { notFound } from "next/navigation";
import Link from "next/link";
import { serverEnv } from "@/lib/env";
import { SessionViewSchema } from "@/lib/session";
import { Eyebrow } from "@/components/ui/eyebrow";
import { buttonClasses } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  TextInterview,
  type TextQuestion,
} from "@/components/interview/text-interview";

// Reads server-only config and calls the agent API per request; never prerender.
export const dynamic = "force-dynamic";

/**
 * Text-mode interview screen — the no-voice practice path. Loads the prepped
 * session from the agent, then renders one question at a time for the candidate
 * to type answers, submit, and get scored. Mirrors the live room's data flow
 * (answers → agent → scoring → report) without needing LiveKit/STT/TTS keys.
 */
async function loadSession(id: string) {
  try {
    const res = await fetch(
      `${serverEnv.agentApiUrl}/api/session/${encodeURIComponent(id)}`,
      { cache: "no-store", signal: AbortSignal.timeout(15_000) },
    );
    if (!res.ok) return null;
    const parsed = SessionViewSchema.safeParse(await res.json());
    return parsed.success ? parsed.data : null;
  } catch {
    return null;
  }
}

export default async function TextInterviewPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const view = await loadSession(id);

  if (!view) notFound();

  // Prep still running (or no context yet) — send them to the briefing screen,
  // which shows prep progress and links back here once ready.
  if (!view.context) {
    return (
      <main className="mx-auto max-w-[760px] px-6 py-12">
        <header>
          <Link href="/" className="no-underline">
            <Eyebrow>DeepInterview · Text mode</Eyebrow>
          </Link>
        </header>
        <div className="mt-16 flex justify-center">
          <Card className="max-w-md text-center">
            <CardContent className="flex flex-col items-center gap-4 py-10">
              <h1 className="font-serif text-2xl text-ink">
                Still preparing your interview
              </h1>
              <p className="max-w-sm text-sm leading-relaxed text-muted">
                We’re still reading your CV and the role. Give it a moment, then
                start.
              </p>
              <Link
                href={`/session/${encodeURIComponent(id)}`}
                className={buttonClasses()}
              >
                View prep progress
              </Link>
            </CardContent>
          </Card>
        </div>
      </main>
    );
  }

  const questions: TextQuestion[] = view.context.plan.questions.map((q) => ({
    id: q.id,
    text: q.text.en ?? "",
    section: q.section,
    difficulty: q.difficulty,
    target_competency: q.target_competency,
    followups: q.followups,
  }));

  return (
    <TextInterview
      sessionId={id}
      role={view.context.job.title ?? null}
      company={view.context.job.company_name ?? null}
      questions={questions}
    />
  );
}
