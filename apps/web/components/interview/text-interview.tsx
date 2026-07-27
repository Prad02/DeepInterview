"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Eyebrow } from "@/components/ui/eyebrow";
import { Badge } from "@/components/ui/badge";
import { buttonClasses } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

export interface TextQuestion {
  id: string;
  text: string;
  section: string;
  difficulty: number;
  target_competency: string;
  followups: string[];
}

interface TextInterviewProps {
  sessionId: string;
  role: string | null;
  company: string | null;
  questions: TextQuestion[];
}

/**
 * Text-mode interview: one question at a time, type an answer, get scored.
 * The no-voice practice path — submits each answer to the agent via our proxy
 * routes, then triggers scoring and hands off to the report page.
 */
export function TextInterview({
  sessionId,
  role,
  company,
  questions,
}: TextInterviewProps) {
  const router = useRouter();
  const [index, setIndex] = React.useState(0);
  const [answer, setAnswer] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [scoring, setScoring] = React.useState(false);

  const total = questions.length;
  const q = questions[index];
  const isLast = index === total - 1;
  const answeredCount = index; // questions submitted so far

  async function submitAnswer(transcript: string) {
    const res = await fetch(
      `/api/session/${encodeURIComponent(sessionId)}/answer`,
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ question_id: q!.id, transcript }),
      },
    );
    if (!res.ok) {
      const body = (await res.json().catch(() => null)) as {
        error?: string;
      } | null;
      throw new Error(body?.error ?? `Could not save answer (${res.status})`);
    }
  }

  async function handleNext(skip = false) {
    if (busy || !q) return;
    const transcript = skip ? "" : answer.trim();
    setError(null);
    setBusy(true);
    try {
      // Only record non-empty answers; a skip just advances (unanswered
      // questions are excluded from the score by the agent).
      if (transcript) await submitAnswer(transcript);

      if (!isLast) {
        setIndex((i) => i + 1);
        setAnswer("");
        setBusy(false);
        return;
      }

      // Last question → trigger scoring, then hand off to the report page,
      // which polls until the scorecard is ready.
      setScoring(true);
      await fetch(`/api/session/${encodeURIComponent(sessionId)}/score`, {
        method: "POST",
        headers: { "content-type": "application/json" },
      }).catch(() => {
        // Even if this request times out, scoring is running agent-side and the
        // report page will poll for the result — so proceed to the report.
      });
      router.push(`/report/${encodeURIComponent(sessionId)}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
      setBusy(false);
      setScoring(false);
    }
  }

  if (scoring) {
    return (
      <StatusShell>
        <Card className="max-w-md text-center">
          <CardContent className="flex flex-col items-center gap-3 py-10">
            <span
              className="h-7 w-7 animate-spin rounded-full border-2 border-accent border-t-transparent"
              aria-hidden
            />
            <h1 className="font-serif text-2xl text-ink">
              Scoring your interview…
            </h1>
            <p className="max-w-sm text-sm leading-relaxed text-muted">
              Analyzing every answer against the rubric. Taking you to your
              report — it updates automatically when ready.
            </p>
          </CardContent>
        </Card>
      </StatusShell>
    );
  }

  if (!q) {
    return (
      <StatusShell>
        <Card className="max-w-md text-center">
          <CardContent className="py-10">
            <p className="text-sm text-muted">
              This interview has no planned questions yet.
            </p>
          </CardContent>
        </Card>
      </StatusShell>
    );
  }

  return (
    <main className="mx-auto max-w-[760px] px-6 py-10">
      <header className="flex items-center justify-between">
        <Link href="/" className="no-underline">
          <Eyebrow>DeepInterview · Text mode</Eyebrow>
        </Link>
        <Badge variant="outline">
          Question {index + 1} of {total}
        </Badge>
      </header>

      {(role || company) && (
        <p className="mt-4 text-[13px] text-muted">
          {role ?? "Interview"}
          {company ? ` · ${company}` : ""}
        </p>
      )}

      {/* Progress bar */}
      <div className="mt-3 h-1.5 w-full overflow-hidden rounded-full bg-line">
        <div
          className="h-full rounded-full bg-accent transition-all"
          style={{ width: `${(answeredCount / total) * 100}%` }}
        />
      </div>

      <section className="mt-8">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="outline" className="capitalize">
            {q.section}
          </Badge>
          <Badge variant="outline">Level {q.difficulty}</Badge>
          <span className="text-[12px] text-muted">{q.target_competency}</span>
        </div>

        <h1 className="mt-4 font-serif text-2xl leading-snug text-ink">
          {q.text}
        </h1>

        {q.followups.length > 0 && (
          <p className="mt-3 text-[13px] leading-relaxed text-muted">
            Possible follow-up: {q.followups[0]}
          </p>
        )}

        <textarea
          value={answer}
          onChange={(e) => setAnswer(e.target.value)}
          rows={9}
          autoFocus
          placeholder="Type your answer as if you were speaking it out loud…"
          className="mt-6 w-full resize-y rounded-[10px] border border-line bg-surface px-4 py-3 text-[15px] leading-relaxed text-ink outline-none focus:border-accent"
        />

        {error && (
          <p className="mt-3 text-sm text-red-600" role="alert">
            {error}
          </p>
        )}

        <div className="mt-5 flex flex-wrap items-center justify-between gap-3">
          <button
            type="button"
            onClick={() => void handleNext(true)}
            disabled={busy}
            className="text-[13px] text-muted underline underline-offset-4 hover:text-ink disabled:opacity-50"
          >
            Skip this question
          </button>
          <button
            type="button"
            onClick={() => void handleNext(false)}
            disabled={busy || answer.trim().length === 0}
            className={buttonClasses()}
          >
            {busy
              ? "Saving…"
              : isLast
                ? "Finish & get my score"
                : "Submit & next question"}
          </button>
        </div>
      </section>
    </main>
  );
}

function StatusShell({ children }: { children: React.ReactNode }) {
  return (
    <main className="mx-auto max-w-[760px] px-6 py-12">
      <header className="flex items-center justify-between">
        <Link href="/" className="no-underline">
          <Eyebrow>DeepInterview</Eyebrow>
        </Link>
      </header>
      <div className="mt-16 flex justify-center">{children}</div>
    </main>
  );
}
