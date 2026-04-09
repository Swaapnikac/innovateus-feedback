"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter, useParams } from "next/navigation";
import { Button } from "@/components/ui/button";
import { ChevronLeft, ChevronRight, Loader2 } from "lucide-react";
import { ProgressBar } from "@/components/ProgressBar";
import { InnovateLogo } from "@/components/InnovateLogo";
import { QuestionCard } from "@/components/QuestionCard";
import { ChoiceQuestion } from "@/components/ChoiceQuestion";
import { MultiSelectQuestion } from "@/components/MultiSelectQuestion";
import { OpenEndedQuestion } from "@/components/OpenEndedQuestion";
import { FollowUpPanel } from "@/components/FollowUpPanel";
import { PrivacyFooter } from "@/components/PrivacyFooter";
import { api, type SurveyQuestion } from "@/lib/api";
import { initSession, trackPageView, trackEvent, trackDropout, setContext } from "@/lib/analytics";

interface AnswerState {
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

export default function SurveyPage() {
  const router = useRouter();
  const params = useParams();
  const cohortId = params.cohortId as string;

  const [questions, setQuestions] = useState<SurveyQuestion[]>([]);
  const [currentStep, setCurrentStep] = useState(0);
  const [answers, setAnswers] = useState<Record<string, AnswerState>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [showFollowups, setShowFollowups] = useState(false);
  const [checkingVagueness, setCheckingVagueness] = useState(false);
  const [completing, setCompleting] = useState(false);
  const [editReturnMode, setEditReturnMode] = useState(false);

  const submissionId = typeof window !== "undefined" ? sessionStorage.getItem("submission_id") : null;

  useEffect(() => {
    if (!submissionId) {
      router.replace(`/c/${cohortId}`);
      return;
    }

    const editMode = typeof window !== "undefined" ? sessionStorage.getItem("edit_mode") : null;
    const editQuestionId = typeof window !== "undefined" ? sessionStorage.getItem("edit_question_id") : null;

    if (editMode === "true" && editQuestionId) {
      // Restore answers from sessionStorage
      const savedAnswers = sessionStorage.getItem("review_answers");
      if (savedAnswers) {
        try { setAnswers(JSON.parse(savedAnswers)); } catch {}
      }

      sessionStorage.removeItem("edit_mode");
      sessionStorage.removeItem("edit_question_id");

      api.getSurvey(cohortId).then((data) => {
        setQuestions(data.survey.questions);
        const visibleQs = data.survey.questions.filter((q: SurveyQuestion) => {
          if (!q.condition) return true;
          return true; // Show all in edit mode — condition checked after answers loaded
        });
        const qIndex = visibleQs.findIndex((q: SurveyQuestion) => q.id === editQuestionId);
        if (qIndex >= 0) setCurrentStep(qIndex);
        setEditReturnMode(true);
        setLoading(false);
      });
      return;
    }

    api.getSurvey(cohortId).then((data) => {
      setQuestions(data.survey.questions);
      setLoading(false);
    });

    initSession();
    setContext(cohortId, submissionId || undefined);
    trackPageView("survey", cohortId);
  }, [cohortId, submissionId, router]);

  const visibleQuestions = questions.filter((q) => {
    if (!q.condition) return true;
    const depAnswer = answers[q.condition.question_id];
    if (!depAnswer) return false;
    if (q.condition.operator === "not_equals") {
      return depAnswer.value !== q.condition.value;
    }
    return depAnswer.value === q.condition.value;
  });

  const currentQuestion = visibleQuestions[currentStep];
  const currentAnswer = currentQuestion ? answers[currentQuestion.id] : undefined;

  // Track question views and register dropout handler
  useEffect(() => {
    if (!currentQuestion) return;
    trackEvent("question_view", {
      question_id: currentQuestion.id,
      question_index: currentStep,
      question_type: currentQuestion.type,
    }, cohortId);

    const handleBeforeUnload = () => {
      const answeredCount = Object.keys(answers).filter((k) => {
        const a = answers[k];
        return a.value.trim().length > 0 || a.multiValues.length > 0;
      }).length;
      trackDropout(cohortId, submissionId, currentQuestion.id, answeredCount);
    };
    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => window.removeEventListener("beforeunload", handleBeforeUnload);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentStep, currentQuestion?.id]);

  const defaultAnswer: AnswerState = { value: "", multiValues: [], inputMode: "voice" };

  const getAnswer = (qId: string): AnswerState =>
    answers[qId] || defaultAnswer;

  const updateAnswer = (qId: string, update: Partial<AnswerState>) => {
    setAnswers((prev) => ({
      ...prev,
      [qId]: { ...(prev[qId] || defaultAnswer), ...update },
    }));
  };

  const saveCurrentAnswer = useCallback(async (overrides?: Partial<AnswerState>) => {
    if (!currentQuestion || !submissionId) return;
    const ans = { ...getAnswer(currentQuestion.id), ...overrides };
    const rawValue = currentQuestion.type === "multi"
      ? JSON.stringify(ans.multiValues)
      : ans.value;

    if (!rawValue && currentQuestion.required) return;

    setSaving(true);
    try {
      await api.saveAnswer(submissionId, {
        question_id: currentQuestion.id,
        question_type: currentQuestion.type,
        answer_raw: rawValue || undefined,
        input_mode: currentQuestion.type === "open" ? ans.inputMode : "none",
        transcript: ans.transcript,
        is_vague: ans.isVague,
        followups_asked: ans.followups?.length || 0,
        followup_1: ans.followups?.[0],
        followup_1_answer: ans.followupAnswers?.followup_1_answer,
        followup_2: ans.followups?.[1],
        followup_2_answer: ans.followupAnswers?.followup_2_answer,
      });
      trackEvent("question_answer", {
        question_id: currentQuestion.id,
        question_type: currentQuestion.type,
        input_mode: currentQuestion.type === "open" ? ans.inputMode : "none",
        has_answer: !!rawValue,
      }, cohortId);
    } catch {
      // Silently fail — answer will be retried on next navigation
    } finally {
      setSaving(false);
    }
  }, [currentQuestion, submissionId, answers]);

  const advanceToNext = useCallback(async (overrides?: Partial<AnswerState>) => {
    await saveCurrentAnswer(overrides);

    // Edit-return mode: go back to review page after saving
    if (editReturnMode) {
      const updatedAnswers = { ...answers };
      if (currentQuestion && overrides) {
        updatedAnswers[currentQuestion.id] = { ...(updatedAnswers[currentQuestion.id] || defaultAnswer), ...overrides };
      }
      sessionStorage.setItem("review_answers", JSON.stringify(updatedAnswers));
      setEditReturnMode(false);
      router.push(`/c/${cohortId}/review`);
      return;
    }

    if (currentStep < visibleQuestions.length - 1) {
      setCurrentStep(currentStep + 1);
    } else {
      // Last question: save answers and go to review page
      const allAnswers = { ...answers };
      if (currentQuestion && overrides) {
        allAnswers[currentQuestion.id] = { ...(allAnswers[currentQuestion.id] || defaultAnswer), ...overrides };
      }
      sessionStorage.setItem("review_answers", JSON.stringify(allAnswers));
      router.push(`/c/${cohortId}/review`);
    }
  }, [saveCurrentAnswer, currentStep, visibleQuestions.length, submissionId, cohortId, router, editReturnMode, answers, currentQuestion, defaultAnswer]);

  const handleNext = async () => {
    if (!currentQuestion) return;
    const ans = getAnswer(currentQuestion.id);

    const needsVaguenessCheck =
      currentQuestion.type === "open" &&
      currentQuestion.voice_eligible &&
      ans.value.trim() &&
      ans.isVague === undefined &&
      !ans.followups &&
      !showFollowups;

    if (needsVaguenessCheck) {
      setCheckingVagueness(true);
      try {
        const result = await api.checkVagueness(currentQuestion.text, ans.value);

        if (result.is_vague) {
          const followupResult = await api.getFollowups(
            currentQuestion.text,
            ans.value,
            result.missing_info_types,
          );
          if (followupResult.followups.length > 0) {
            updateAnswer(currentQuestion.id, {
              isVague: true,
              missingInfoTypes: result.missing_info_types,
              followups: followupResult.followups,
            });
            setShowFollowups(true);
            trackEvent("followup_triggered", {
              question_id: currentQuestion.id,
              num_followups: followupResult.followups.length,
            }, cohortId);
            setCheckingVagueness(false);
            return;
          }
        }

        updateAnswer(currentQuestion.id, {
          isVague: result.is_vague,
          missingInfoTypes: result.missing_info_types,
        });
      } catch {
        updateAnswer(currentQuestion.id, { isVague: false });
      }
      setCheckingVagueness(false);
    }

    setShowFollowups(false);
    await advanceToNext();
  };

  const handleFollowupComplete = async (followupAnswers: {
    followup_1_answer?: string;
    followup_2_answer?: string;
  }) => {
    if (currentQuestion) {
      updateAnswer(currentQuestion.id, { followupAnswers });
      trackEvent("followup_answered", {
        question_id: currentQuestion.id,
        followup_1_answered: !!followupAnswers.followup_1_answer,
        followup_2_answered: !!followupAnswers.followup_2_answer,
      }, cohortId);
    }
    setShowFollowups(false);
    await advanceToNext({ followupAnswers });
  };

  const handlePrev = () => {
    if (currentStep > 0) {
      setShowFollowups(false);
      setCurrentStep(currentStep - 1);
    }
  };

  const isCurrentValid = () => {
    if (!currentQuestion) return false;
    const ans = getAnswer(currentQuestion.id);

    // For voice-eligible open questions in voice mode:
    // Only block Next when voiceConfirmed is explicitly false (user started recording
    // but hasn't clicked "Use This Response" yet). When voiceConfirmed is undefined
    // (user hasn't interacted), allow Next since questions aren't mandatory.
    if (
      currentQuestion.type === "open" &&
      currentQuestion.voice_eligible &&
      ans.inputMode === "voice" &&
      ans.voiceConfirmed === false
    ) {
      return false;
    }

    if (!currentQuestion.required) return true;
    if (currentQuestion.type === "multi") return ans.multiValues.length > 0;
    return ans.value.trim().length > 0;
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-brand-light-blue/40 flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-brand-blue" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-brand-light-blue/40 pb-16">
      <header className="bg-white/80 backdrop-blur-md border-b border-[#E4EFFC] px-6 py-3 mb-6">
        <div className="max-w-3xl mx-auto">
          <InnovateLogo size="sm" />
        </div>
      </header>
      <div className="max-w-3xl mx-auto px-4 space-y-6">
        <ProgressBar current={currentStep + 1} total={visibleQuestions.length} />

        {currentQuestion && (
          <QuestionCard
            text={currentQuestion.text}
            description={currentQuestion.description}
            required={currentQuestion.required}
          >
            {!showFollowups && (
              <>
                {(currentQuestion.type === "rating" || currentQuestion.type === "mcq") && (
                  <ChoiceQuestion
                    type={currentQuestion.type}
                    options={currentQuestion.options || []}
                    value={getAnswer(currentQuestion.id).value}
                    onChange={(v) => updateAnswer(currentQuestion.id, { value: v })}
                  />
                )}

                {currentQuestion.type === "multi" && (
                  <MultiSelectQuestion
                    options={(currentQuestion.options as string[]) || []}
                    value={getAnswer(currentQuestion.id).multiValues}
                    onChange={(v) => updateAnswer(currentQuestion.id, { multiValues: v })}
                  />
                )}

                {currentQuestion.type === "open" && (
                  <OpenEndedQuestion
                    key={currentQuestion.id}
                    value={getAnswer(currentQuestion.id).value}
                    onChange={(v) => updateAnswer(currentQuestion.id, { value: v })}
                    voiceEligible={currentQuestion.voice_eligible}
                    onInputModeChange={(mode) =>
                      updateAnswer(currentQuestion.id, { inputMode: mode, voiceConfirmed: mode === "text" ? undefined : false })
                    }
                    onTranscriptReady={(transcript) =>
                      updateAnswer(currentQuestion.id, { transcript, value: transcript, voiceConfirmed: true })
                    }
                    onRecordingStarted={() =>
                      updateAnswer(currentQuestion.id, { voiceConfirmed: false })
                    }
                  />
                )}
              </>
            )}

            {showFollowups && (
              <div className="rounded-lg bg-brand-light-blue/40 px-4 py-3 text-sm text-brand-blue/70 italic">
                &ldquo;{getAnswer(currentQuestion.id).value}&rdquo;
              </div>
            )}

            {showFollowups && getAnswer(currentQuestion.id).followups && (
              <FollowUpPanel
                followups={getAnswer(currentQuestion.id).followups!}
                onComplete={handleFollowupComplete}
              />
            )}
          </QuestionCard>
        )}

        <div className="flex justify-between max-w-3xl mx-auto">
          <Button
            variant="outline"
            onClick={handlePrev}
            disabled={currentStep === 0 || saving || editReturnMode}
            className="gap-2 border-brand-blue/15 text-brand-blue/70 hover:bg-brand-blue/5"
          >
            <ChevronLeft className="h-4 w-4" />
            Back
          </Button>

          <Button
            onClick={handleNext}
            disabled={!isCurrentValid() || saving || checkingVagueness || showFollowups}
            className="gap-2 bg-brand-blue hover:bg-brand-blue/90 shadow-sm"
          >
            {checkingVagueness && <Loader2 className="h-4 w-4 animate-spin" />}
            {checkingVagueness
              ? "Analyzing..."
              : editReturnMode
                ? "Back to Review"
                : currentStep === visibleQuestions.length - 1
                  ? "Review"
                  : "Next"}
            {!checkingVagueness && <ChevronRight className="h-4 w-4" />}
          </Button>
        </div>
      </div>
      <PrivacyFooter />
    </div>
  );
}
