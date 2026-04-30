"use client";

import { useState, useEffect, useRef } from "react";
import { useRouter, useParams } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { InnovateLogo } from "@/components/InnovateLogo";
import { ExtractionCard } from "@/components/ExtractionCard";
import { SummarySkeleton } from "@/components/SummarySkeleton";
import { ExperienceRating } from "@/components/ExperienceRating";
import { Loader2, Pencil, Send, CheckCircle2 } from "lucide-react";
import { api, type SurveyQuestion, type ExtractionResult } from "@/lib/api";
import { initSession, trackPageView, trackEvent, setContext } from "@/lib/analytics";

interface StoredAnswer {
  value: string;
  multiValues: string[];
  inputMode: "text" | "voice";
  transcript?: string;
  isVague?: boolean;
  followups?: string[];
  followupAnswers?: { followup_1_answer?: string; followup_2_answer?: string };
  missingInfoTypes?: string[];
  voiceConfirmed?: boolean;
}

function loadStoredAnswers(): Record<string, StoredAnswer> {
  if (typeof window === "undefined") return {};
  const savedAnswers = sessionStorage.getItem("review_answers");
  if (!savedAnswers) return {};
  try {
    return JSON.parse(savedAnswers);
  } catch {
    return {};
  }
}

function loadStoredQuestions(): SurveyQuestion[] {
  if (typeof window === "undefined") return [];
  const storedData = sessionStorage.getItem("question_data");
  if (!storedData) return [];
  try {
    return JSON.parse(storedData);
  } catch {
    return [];
  }
}

export default function ReviewPage() {
  const router = useRouter();
  const params = useParams();
  const cohortId = params.cohortId as string;

  const [questions, setQuestions] = useState<SurveyQuestion[]>(loadStoredQuestions);
  const [answers] = useState<Record<string, StoredAnswer>>(loadStoredAnswers);
  // Hydrate from the cached preview if we have one and it's not flagged
  // dirty (i.e. the user didn't actually edit anything since the last
  // generation). This avoids a 13-20s GPT-5 re-run every time the user
  // bounces /review → /survey → /review.
  const [extraction, setExtraction] = useState<ExtractionResult | null>(() => {
    if (typeof window === "undefined") return null;
    if (sessionStorage.getItem("extraction_dirty") === "1") return null;
    const cached = sessionStorage.getItem("review_extraction_cache");
    if (!cached) return null;
    try {
      return JSON.parse(cached) as ExtractionResult;
    } catch {
      return null;
    }
  });
  const [loadingExtraction, setLoadingExtraction] = useState(() => {
    if (typeof window === "undefined") return true;
    if (sessionStorage.getItem("extraction_dirty") === "1") return true;
    return !sessionStorage.getItem("review_extraction_cache");
  });
  const [submitting, setSubmitting] = useState(false);
  // Synchronous guard against double-submit: React state updates are batched,
  // so a second click can fire before `submitting` flips to true.
  const submitInFlightRef = useRef(false);
  // Captured at submit time so handleRatingSubmit can still hit the rating
  // endpoint after we wipe submission_id from sessionStorage post-complete.
  const submittedIdRef = useRef<string | null>(null);
  const [showRating, setShowRating] = useState(false);
  const [ratingSubmitting, setRatingSubmitting] = useState(false);
  const [loading, setLoading] = useState(() => loadStoredQuestions().length === 0);

  // Read once on mount and freeze. Reading from sessionStorage on every
  // render causes the redirect-to-consent guard in the mount useEffect to
  // fire when we wipe sessionStorage just before navigating to /done, which
  // races the actual navigation. The submitted-id ref is the source of
  // truth from submit time onward.
  const [submissionId] = useState<string | null>(() =>
    typeof window === "undefined" ? null : sessionStorage.getItem("submission_id")
  );

  useEffect(() => {
    if (!submissionId) {
      router.replace(`/c/${cohortId}`);
      return;
    }

    initSession();
    setContext(cohortId, submissionId);
    trackPageView("review", cohortId);

    // Skip the network round-trip when we already have a fresh cached
    // summary for this submission. The survey page sets
    // ``extraction_dirty`` whenever an edit-return Save mutates answers,
    // which forces a regeneration here.
    const isDirty = sessionStorage.getItem("extraction_dirty") === "1";
    const cachedRaw = sessionStorage.getItem("review_extraction_cache");
    if (!isDirty && cachedRaw) {
      try {
        const cached = JSON.parse(cachedRaw) as ExtractionResult;
        setExtraction(cached);
        setLoadingExtraction(false);
        return;
      } catch {
        // Fall through to network fetch.
      }
    }

    api.previewExtraction(submissionId).then((result) => {
      setExtraction(result.extraction);
      setLoadingExtraction(false);
      try {
        sessionStorage.setItem("review_extraction_cache", JSON.stringify(result.extraction));
        sessionStorage.removeItem("extraction_dirty");
      } catch {
        // Best-effort cache; quota errors shouldn't break the page.
      }
    }).catch(() => {
      setLoadingExtraction(false);
    });
  }, [cohortId, submissionId, router]);

  useEffect(() => {
    if (!submissionId || questions.length > 0) return;
    api.getSurvey(cohortId).then((data) => {
      setQuestions(data.survey.questions);
      setLoading(false);
      // Canonicalize the URL if the user reached us via an old/historical
      // slug (one that lives in ``previous_slugs``). The /review page is
      // typically reached after the survey, but a returning user might
      // bookmark or refresh it under the legacy URL.
      if (data.slug && data.slug !== cohortId) {
        router.replace(`/c/${data.slug}/review`);
      }
    }).catch(() => {
      setLoading(false);
    });
  }, [cohortId, submissionId, questions.length, router]);

  // Filter to visible questions (respect conditions)
  const visibleQuestions = questions.filter((q) => {
    if (!q.condition) return true;
    const depAnswer = answers[q.condition.question_id];
    if (!depAnswer) return false;
    if (q.condition.operator === "not_equals") {
      return depAnswer.value !== q.condition.value;
    }
    return depAnswer.value === q.condition.value;
  });

  const answeredQuestions = visibleQuestions.filter((q) => {
    const ans = answers[q.id];
    if (!ans) return false;
    if (q.type === "multi") return ans.multiValues.length > 0;
    if (q.type === "matrix" || q.type === "ranking") return !!ans.value && ans.value !== "{}" && ans.value !== "[]";
    return ans.value.trim().length > 0;
  });

  const formatAnswer = (q: SurveyQuestion, ans: StoredAnswer): string => {
    if (q.type === "multi") {
      return ans.multiValues.join(", ");
    }
    if (q.type === "matrix") {
      try {
        const parsed = JSON.parse(ans.value);
        return Object.entries(parsed)
          .map(([row, col]) => `${row}: ${col}`)
          .join(" • ");
      } catch {
        return ans.value;
      }
    }
    if (q.type === "ranking") {
      try {
        const parsed = JSON.parse(ans.value);
        if (Array.isArray(parsed)) {
          return parsed.map((item, i) => `${i + 1}. ${item}`).join(" • ");
        }
      } catch {
        // fall through
      }
      return ans.value;
    }
    if (q.type === "yesno") {
      return ans.value === "yes" ? "Yes" : ans.value === "no" ? "No" : ans.value;
    }
    return ans.value;
  };

  const handleEdit = (questionId: string) => {
    trackEvent("review_edit", { question_id: questionId }, cohortId);
    sessionStorage.setItem("edit_mode", "true");
    sessionStorage.setItem("edit_question_id", questionId);
    sessionStorage.setItem("review_answers", JSON.stringify(answers));
    router.push(`/c/${cohortId}/survey`);
  };

  const handleSubmit = async () => {
    if (!submissionId) return;
    // Don't allow submit until the AI summary has finished loading. The
    // backend can technically accept the submission, but submitting before the
    // user has seen / had a chance to edit their summary leads to a confusing
    // experience.
    if (loadingExtraction) return;
    // Hard guard: if a previous click is still in flight, ignore subsequent ones.
    if (submitInFlightRef.current) return;
    submitInFlightRef.current = true;
    setSubmitting(true);
    try {
      const result = await api.completeSubmission(submissionId);
      // Stash the just-completed id in a ref so handleRatingSubmit can still
      // post to the rating endpoint after we wipe sessionStorage right
      // before navigating to /done.
      submittedIdRef.current = submissionId;
      // /complete now runs the GPT-5 extraction in the background and returns
      // an empty placeholder, so prefer the preview extraction we already have
      // on this page (the one shown in the summary card). Only fall back to
      // the API result if for some reason we never got a preview.
      const extractionForDone = extraction ?? result.extraction;
      sessionStorage.setItem("extraction", JSON.stringify(extractionForDone));
      // review_answers is no longer needed and only causes confusion if the
      // user navigates back; the rest of the submission_id-keyed state stays
      // until handleRatingSubmit / handleRatingSkip wipes it right before
      // navigating to /done (clearing it here would re-trigger this effect's
      // !submissionId guard and kick the user out mid-rating overlay).
      sessionStorage.removeItem("review_answers");
      trackEvent("survey_complete", {
        questions_answered: answeredQuestions.length,
        total_questions: visibleQuestions.length,
      }, cohortId);
      // Keep `submitting` true until the rating overlay swaps the bar out, so
      // the button never re-enables for even a single render frame.
      setShowRating(true);
    } catch {
      alert("Failed to submit. Please try again.");
      setSubmitting(false);
      submitInFlightRef.current = false;
    }
  };

  // Wipe everything tied to the just-completed submission so any future
  // navigation to /survey or /review (browser back, etc.) can't re-render
  // stale data or re-fire previewExtraction against the completed id.
  // /done only needs `extraction`, so that and analytics_session survive.
  const wipeCompletedSubmissionState = () => {
    sessionStorage.removeItem("submission_id");
    sessionStorage.removeItem("question_data");
    sessionStorage.removeItem("question_order");
    sessionStorage.removeItem("edit_mode");
    sessionStorage.removeItem("edit_question_id");
    sessionStorage.removeItem("review_extraction_cache");
    sessionStorage.removeItem("extraction_dirty");
  };

  const handleRatingSubmit = async (rating: number, feedback?: string) => {
    // Read from the ref (captured at submit time, before any sessionStorage
    // wipe) so the rating still posts against the just-completed submission.
    // Falls back to sessionStorage on the off-chance handleSubmit never ran.
    const idForRating = submittedIdRef.current ?? submissionId;
    if (!idForRating) return;
    setRatingSubmitting(true);
    trackEvent("experience_rating", { rating, has_feedback: !!feedback }, cohortId);
    try {
      await api.submitExperienceRating(idForRating, rating, feedback);
    } catch {
      // Rating save failed silently, don't block the user
    }
    setRatingSubmitting(false);
    wipeCompletedSubmissionState();
    // Use replace (not push) so the now-submitted /review page is removed
    // from history. The /done page also intercepts Back to redirect users
    // to a fresh consent page rather than the half-completed review.
    router.replace(`/c/${cohortId}/done`);
  };

  const handleRatingSkip = () => {
    wipeCompletedSubmissionState();
    router.replace(`/c/${cohortId}/done`);
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-brand-light-blue/40 flex items-center justify-center">
        <Loader2 className="h-8 w-8 motion-safe:animate-spin text-brand-blue" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-brand-light-blue/40 pb-20">
      <header className="bg-white/80 backdrop-blur-md border-b border-[#E4EFFC] px-6 py-3 mb-6">
        <div className="max-w-3xl mx-auto">
          <InnovateLogo size="sm" />
        </div>
      </header>

      <main id="main" tabIndex={-1} className="max-w-3xl mx-auto px-4 space-y-6 focus:outline-none">
        {/* Header */}
        <div className="text-center space-y-2">
          <div className="mx-auto w-12 h-12 rounded-full bg-brand-blue/10 flex items-center justify-center">
            <CheckCircle2 className="h-6 w-6 text-brand-blue" />
          </div>
          <h1 className="text-2xl font-serif text-brand-blue">Review Your Responses</h1>
          <p className="text-sm text-brand-blue/50">
            Review your answers below. Click Edit to change any response, then submit when ready.
          </p>
        </div>

        {/* Answer Cards */}
        <div className="space-y-3">
          {visibleQuestions.map((q, i) => {
            const ans = answers[q.id];
            const hasAnswer = ans && (
              q.type === "multi"
                ? ans.multiValues.length > 0
                : (q.type === "matrix" || q.type === "ranking")
                  ? !!ans.value && ans.value !== "{}" && ans.value !== "[]"
                  : ans.value.trim().length > 0
            );
            const displayAnswer = hasAnswer ? formatAnswer(q, ans) : null;

            return (
              <Card key={q.id} className={`bg-white border-0 shadow-sm rounded-2xl ${!hasAnswer ? "opacity-70" : ""}`}>
                <CardContent className="pt-5 pb-4">
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex-1 min-w-0">
                      <p className="text-xs font-semibold text-brand-blue/60 uppercase tracking-wider mb-1">
                        Question {i + 1}
                      </p>
                      <p className="text-sm font-medium text-brand-blue mb-3">{q.text}</p>
                      {hasAnswer ? (
                        <>
                          <p className="text-xs font-semibold text-brand-teal/60 uppercase tracking-wider mb-1">Your Answer</p>
                          <p className="text-sm text-brand-blue/70 whitespace-pre-wrap bg-brand-light-blue/40 rounded-lg px-3 py-2">{displayAnswer}</p>
                          {ans?.followupAnswers?.followup_1_answer && (
                            <div className="mt-2 pl-3 border-l-2 border-brand-yellow/40">
                              <p className="text-xs text-brand-blue/60 mb-0.5">Follow-up</p>
                              <p className="text-sm text-brand-blue/60">{ans.followupAnswers.followup_1_answer}</p>
                            </div>
                          )}
                          {ans?.followupAnswers?.followup_2_answer && (
                            <div className="mt-1 pl-3 border-l-2 border-brand-yellow/40">
                              <p className="text-sm text-brand-blue/60">{ans.followupAnswers.followup_2_answer}</p>
                            </div>
                          )}
                        </>
                      ) : (
                        <p className="text-sm italic text-brand-blue/60">Skipped</p>
                      )}
                    </div>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleEdit(q.id)}
                      className="shrink-0 gap-1.5 border-brand-blue/15 text-brand-blue/60 hover:bg-brand-blue/5"
                    >
                      <Pencil className="h-3.5 w-3.5" />
                      {hasAnswer ? "Edit" : "Answer"}
                    </Button>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>

        {/* Extraction Preview */}
        {loadingExtraction ? (
          <SummarySkeleton title="What We Heard" />
        ) : extraction ? (
          <ExtractionCard
            extraction={extraction}
            title="What We Heard"
            subtitle="A preview of the AI-generated summary of your feedback"
          />
        ) : (
          <Card className="bg-white border-0 shadow-sm rounded-2xl">
            <CardContent className="py-8 text-center">
              <p className="text-sm text-brand-blue/60">Summary unavailable</p>
            </CardContent>
          </Card>
        )}

      </main>

      {/* Fixed bottom submit bar */}
      {!showRating && (
        <div className="fixed bottom-0 left-0 right-0 bg-white/90 backdrop-blur-md border-t border-brand-blue/10 py-4 px-6 z-50">
          <div className="max-w-3xl mx-auto flex justify-center">
            <Button
              type="button"
              onClick={(e) => {
                if (submitting || submitInFlightRef.current || loadingExtraction) {
                  e.preventDefault();
                  e.stopPropagation();
                  return;
                }
                handleSubmit();
              }}
              disabled={submitting || loadingExtraction}
              aria-busy={submitting || loadingExtraction}
              aria-disabled={submitting || loadingExtraction}
              size="lg"
              className={`text-base bg-brand-blue hover:bg-brand-blue/90 shadow-lg gap-2 px-10 disabled:opacity-60 disabled:cursor-not-allowed ${submitting || loadingExtraction ? "pointer-events-none" : ""}`}
            >
              {submitting || loadingExtraction ? (
                <Loader2 className="h-4 w-4 motion-safe:animate-spin" />
              ) : (
                <Send className="h-4 w-4" />
              )}
              {submitting
                ? "Submitting..."
                : loadingExtraction
                  ? "Preparing summary..."
                  : "Submit Feedback"}
            </Button>
          </div>
        </div>
      )}

      {/* Experience rating overlay */}
      {showRating && (
        <ExperienceRating
          onSubmit={handleRatingSubmit}
          onSkip={handleRatingSkip}
          isSubmitting={ratingSubmitting}
        />
      )}
    </div>
  );
}
