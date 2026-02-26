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

interface AnswerState {
  value: string;
  multiValues: string[];
  inputMode: "text" | "voice";
  transcript?: string;
  isVague?: boolean;
  followups?: string[];
  followupAnswers?: { followup_1_answer?: string; followup_2_answer?: string };
  missingInfoTypes?: string[];
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

  const submissionId = typeof window !== "undefined" ? sessionStorage.getItem("submission_id") : null;
  const language = typeof window !== "undefined" ? sessionStorage.getItem("survey_language") || "en" : "en";

  useEffect(() => {
    if (!submissionId) {
      router.replace(`/c/${cohortId}`);
      return;
    }
    api.getSurvey(cohortId, language).then((data) => {
      setQuestions(data.survey.questions);
      setLoading(false);
    });
  }, [cohortId, language, submissionId, router]);

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

  const defaultAnswer: AnswerState = { value: "", multiValues: [], inputMode: "text" };

  const getAnswer = (qId: string): AnswerState =>
    answers[qId] || defaultAnswer;

  const updateAnswer = (qId: string, update: Partial<AnswerState>) => {
    setAnswers((prev) => ({
      ...prev,
      [qId]: { ...(prev[qId] || defaultAnswer), ...update },
    }));
  };

  const saveCurrentAnswer = useCallback(async () => {
    if (!currentQuestion || !submissionId) return;
    const ans = getAnswer(currentQuestion.id);
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
    } catch {
      // Silently fail — answer will be retried on next navigation
    } finally {
      setSaving(false);
    }
  }, [currentQuestion, submissionId, answers]);

  const advanceToNext = useCallback(async () => {
    await saveCurrentAnswer();

    if (currentStep < visibleQuestions.length - 1) {
      setCurrentStep(currentStep + 1);
    } else {
      setCompleting(true);
      try {
        const result = await api.completeSubmission(submissionId!);
        sessionStorage.setItem("extraction", JSON.stringify(result.extraction));
        router.push(`/c/${cohortId}/done`);
      } catch {
        alert("Failed to complete survey. Please try again.");
      } finally {
        setCompleting(false);
      }
    }
  }, [saveCurrentAnswer, currentStep, visibleQuestions.length, submissionId, cohortId, router]);

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
        const result = await api.checkVagueness(currentQuestion.text, ans.value, language);

        if (result.is_vague) {
          const followupResult = await api.getFollowups(
            currentQuestion.text,
            ans.value,
            result.missing_info_types,
            language
          );
          if (followupResult.followups.length > 0) {
            updateAnswer(currentQuestion.id, {
              isVague: true,
              missingInfoTypes: result.missing_info_types,
              followups: followupResult.followups,
            });
            setShowFollowups(true);
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
    }
    setShowFollowups(false);
    await advanceToNext();
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
        <div className="max-w-2xl mx-auto">
          <InnovateLogo size="sm" />
        </div>
      </header>
      <div className="max-w-2xl mx-auto px-4 space-y-6">
        <ProgressBar current={currentStep + 1} total={visibleQuestions.length} />

        {currentQuestion && !showFollowups && (
          <QuestionCard
            text={currentQuestion.text}
            description={currentQuestion.description}
            required={currentQuestion.required}
          >
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
                value={getAnswer(currentQuestion.id).value}
                onChange={(v) => updateAnswer(currentQuestion.id, { value: v })}
                voiceEligible={currentQuestion.voice_eligible}
                onInputModeChange={(mode) =>
                  updateAnswer(currentQuestion.id, { inputMode: mode })
                }
                onTranscriptReady={(transcript) =>
                  updateAnswer(currentQuestion.id, { transcript, value: transcript })
                }
                language={language}
              />
            )}
          </QuestionCard>
        )}

        {showFollowups && currentQuestion && getAnswer(currentQuestion.id).followups && (
          <FollowUpPanel
            followups={getAnswer(currentQuestion.id).followups!}
            onComplete={handleFollowupComplete}
            language={language}
          />
        )}

        <div className="flex justify-between max-w-2xl mx-auto">
          <Button
            variant="outline"
            onClick={handlePrev}
            disabled={currentStep === 0 || saving || completing}
            className="gap-2 rounded-full border-brand-blue/15 text-brand-blue/70 hover:bg-brand-blue/5"
          >
            <ChevronLeft className="h-4 w-4" />
            Back
          </Button>

          <Button
            onClick={handleNext}
            disabled={!isCurrentValid() || saving || checkingVagueness || completing || showFollowups}
            className="gap-2 bg-brand-blue hover:bg-brand-blue/90 rounded-full px-6 shadow-sm"
          >
            {checkingVagueness && <Loader2 className="h-4 w-4 animate-spin" />}
            {completing && <Loader2 className="h-4 w-4 animate-spin" />}
            {completing
              ? "Finishing..."
              : checkingVagueness
                ? "Analyzing..."
                : currentStep === visibleQuestions.length - 1
                  ? "Submit"
                  : "Next"}
            {!checkingVagueness && !completing && <ChevronRight className="h-4 w-4" />}
          </Button>
        </div>
      </div>
      <PrivacyFooter />
    </div>
  );
}
