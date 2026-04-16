"use client";

import { useState, useEffect } from "react";
import { useRouter, useParams } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { InnovateLogo } from "@/components/InnovateLogo";
import { ExtractionCard } from "@/components/ExtractionCard";
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
  const [extraction, setExtraction] = useState<ExtractionResult | null>(null);
  const [loadingExtraction, setLoadingExtraction] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [showRating, setShowRating] = useState(false);
  const [ratingSubmitting, setRatingSubmitting] = useState(false);
  const [loading, setLoading] = useState(() => loadStoredQuestions().length === 0);

  const submissionId = typeof window !== "undefined" ? sessionStorage.getItem("submission_id") : null;

  useEffect(() => {
    if (!submissionId) {
      router.replace(`/c/${cohortId}`);
      return;
    }

    initSession();
    setContext(cohortId, submissionId);
    trackPageView("review", cohortId);

    // Fetch preview extraction
    api.previewExtraction(submissionId).then((result) => {
      setExtraction(result.extraction);
      setLoadingExtraction(false);
    }).catch(() => {
      setLoadingExtraction(false);
    });
  }, [cohortId, submissionId, router]);

  useEffect(() => {
    if (!submissionId || questions.length > 0) return;
    api.getSurvey(cohortId).then((data) => {
      setQuestions(data.survey.questions);
      setLoading(false);
    }).catch(() => {
      setLoading(false);
    });
  }, [cohortId, submissionId, questions.length]);

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
    setSubmitting(true);
    try {
      const result = await api.completeSubmission(submissionId);
      sessionStorage.setItem("extraction", JSON.stringify(result.extraction));
      sessionStorage.removeItem("review_answers");
      trackEvent("survey_complete", {
        questions_answered: answeredQuestions.length,
        total_questions: visibleQuestions.length,
      }, cohortId);
      setSubmitting(false);
      setShowRating(true);
    } catch {
      alert("Failed to submit. Please try again.");
      setSubmitting(false);
    }
  };

  const handleRatingSubmit = async (rating: number, feedback?: string) => {
    if (!submissionId) return;
    setRatingSubmitting(true);
    trackEvent("experience_rating", { rating, has_feedback: !!feedback }, cohortId);
    try {
      await api.submitExperienceRating(submissionId, rating, feedback);
    } catch {
      // Rating save failed silently, don't block the user
    }
    setRatingSubmitting(false);
    router.push(`/c/${cohortId}/done`);
  };

  const handleRatingSkip = () => {
    router.push(`/c/${cohortId}/done`);
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-brand-light-blue/40 flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-brand-blue" />
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

      <div className="max-w-3xl mx-auto px-4 space-y-6">
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
                      <p className="text-xs font-semibold text-brand-blue/40 uppercase tracking-wider mb-1">
                        Question {i + 1}
                      </p>
                      <p className="text-sm font-medium text-brand-blue mb-3">{q.text}</p>
                      {hasAnswer ? (
                        <>
                          <p className="text-xs font-semibold text-brand-teal/60 uppercase tracking-wider mb-1">Your Answer</p>
                          <p className="text-sm text-brand-blue/70 whitespace-pre-wrap bg-brand-light-blue/40 rounded-lg px-3 py-2">{displayAnswer}</p>
                          {ans?.followupAnswers?.followup_1_answer && (
                            <div className="mt-2 pl-3 border-l-2 border-brand-yellow/40">
                              <p className="text-xs text-brand-blue/40 mb-0.5">Follow-up</p>
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
                        <p className="text-sm italic text-brand-blue/30">Skipped</p>
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
          <Card className="bg-white border-0 shadow-sm rounded-2xl">
            <CardContent className="py-10 flex flex-col items-center gap-3">
              <Loader2 className="h-6 w-6 animate-spin text-brand-blue/40" />
              <p className="text-sm text-brand-blue/40">Generating summary...</p>
            </CardContent>
          </Card>
        ) : extraction ? (
          <ExtractionCard
            extraction={extraction}
            title="What We Heard"
            subtitle="A preview of the AI-generated summary of your feedback"
          />
        ) : (
          <Card className="bg-white border-0 shadow-sm rounded-2xl">
            <CardContent className="py-8 text-center">
              <p className="text-sm text-brand-blue/40">Summary unavailable</p>
            </CardContent>
          </Card>
        )}

      </div>

      {/* Fixed bottom submit bar */}
      {!showRating && (
        <div className="fixed bottom-0 left-0 right-0 bg-white/90 backdrop-blur-md border-t border-brand-blue/10 py-4 px-6 z-50">
          <div className="max-w-3xl mx-auto flex justify-center">
            <Button
              onClick={handleSubmit}
              disabled={submitting}
              size="lg"
              className="text-base bg-brand-blue hover:bg-brand-blue/90 shadow-lg gap-2 px-10"
            >
              {submitting ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Send className="h-4 w-4" />
              )}
              {submitting ? "Submitting..." : "Submit Feedback"}
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
