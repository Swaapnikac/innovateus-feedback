"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { useRouter, useParams } from "next/navigation";
import { Button } from "@/components/ui/button";
import { ChevronLeft, ChevronRight, Loader2 } from "lucide-react";
import { ProgressBar } from "@/components/ProgressBar";
import { InnovateLogo } from "@/components/InnovateLogo";
import { QuestionCard } from "@/components/QuestionCard";
import { ChoiceQuestion } from "@/components/ChoiceQuestion";
import { MultiSelectQuestion } from "@/components/MultiSelectQuestion";
import { OpenEndedQuestion } from "@/components/OpenEndedQuestion";
import { FollowUpPanel, type FollowUpPanelHandle } from "@/components/FollowUpPanel";
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
  const [checkingFollowupVagueness, setCheckingFollowupVagueness] = useState(false);
  const [editReturnMode, setEditReturnMode] = useState(false);
  const [irrelevantError, setIrrelevantError] = useState("");
  // pendingFollowups holds followup questions between state-setting and render
  const pendingFollowupsRef = useRef<string[] | null>(null);
  // answersRef always points to the latest answers — used in effects that must
  // not re-run on every keystroke but still need fresh answer data.
  const answersRef = useRef<Record<string, AnswerState>>({});
  // Ref to the FollowUpPanel so we can flush any unsaved typed text on Next click
  const followUpPanelRef = useRef<FollowUpPanelHandle>(null);

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
      let restoredAnswers: Record<string, AnswerState> = {};
      const savedAnswers = sessionStorage.getItem("review_answers");
      console.log("[EDIT] review_answers raw:", savedAnswers);
      if (savedAnswers) {
        try {
          restoredAnswers = JSON.parse(savedAnswers);
          console.log("[EDIT] restoredAnswers for", editQuestionId, ":", JSON.stringify(restoredAnswers[editQuestionId]));
          setAnswers(restoredAnswers);
          answersRef.current = restoredAnswers;
        } catch {}
      }

      sessionStorage.removeItem("edit_mode");
      sessionStorage.removeItem("edit_question_id");

      // Use stored question data (full objects in original randomized order) so
      // we never re-randomize by calling the API again.
      const storedData = sessionStorage.getItem("question_data");
      if (storedData) {
        try {
          const storedQuestions: SurveyQuestion[] = JSON.parse(storedData);
          // Compute the correct step index right here, using the same answers
          // and questions that React is about to render with. This avoids any
          // useEffect timing race where visibleQuestions is stale.
          const visible = storedQuestions.filter((q: SurveyQuestion) => {
            if (!q.condition) return true;
            const dep = restoredAnswers[q.condition.question_id];
            if (!dep) return false;
            if (q.condition.operator === "not_equals") return dep.value !== q.condition.value;
            return dep.value === q.condition.value;
          });
          const idx = visible.findIndex((q: SurveyQuestion) => q.id === editQuestionId);
          answersRef.current = restoredAnswers;
          setQuestions(storedQuestions);
          setCurrentStep(idx >= 0 ? idx : 0);
          setEditReturnMode(true);
          setLoading(false);
          return;
        } catch {}
      }

      // Fallback: fetch from API (only if question_data missing — first-ever load)
      api.getSurvey(cohortId).then((data) => {
        const visible = data.survey.questions.filter((q: SurveyQuestion) => {
          if (!q.condition) return true;
          const dep = restoredAnswers[q.condition.question_id];
          if (!dep) return false;
          if (q.condition.operator === "not_equals") return dep.value !== q.condition.value;
          return dep.value === q.condition.value;
        });
        const idx = visible.findIndex((q: SurveyQuestion) => q.id === editQuestionId);
        answersRef.current = restoredAnswers;
        setQuestions(data.survey.questions);
        setCurrentStep(idx >= 0 ? idx : 0);
        setEditReturnMode(true);
        setLoading(false);
      });
      return;
    }

    // If question_data already exists (e.g. React Strict Mode double-invoke,
    // or returning from edit), reuse it — never call the API again, which
    // would re-randomize the question order.
    const existingData = sessionStorage.getItem("question_data");
    if (existingData) {
      try {
        setQuestions(JSON.parse(existingData));
        setLoading(false);
        return;
      } catch {
        // Corrupted — fall through to fetch fresh
        sessionStorage.removeItem("question_data");
      }
    }

    api.getSurvey(cohortId).then((data) => {
      setQuestions(data.survey.questions);
      sessionStorage.setItem("question_order", JSON.stringify(data.survey.questions.map((q: SurveyQuestion) => q.id)));
      sessionStorage.setItem("question_data", JSON.stringify(data.survey.questions));
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

  // When navigating to a question, restore follow-up panel if that question
  // had follow-ups generated but not yet completed (e.g. user went Back).
  // Uses answersRef so it always reads the latest answer state, not a stale closure.
  useEffect(() => {
    if (!currentQuestion) return;
    const defaultAns: AnswerState = { value: "", multiValues: [], inputMode: "voice" };
    const ans = answersRef.current[currentQuestion.id] ?? defaultAns;
    console.log("[FOLLOWUP-EFFECT] qId:", currentQuestion.id, "isVague:", ans.isVague, "followups:", ans.followups, "followupAnswers:", ans.followupAnswers);
    if (
      currentQuestion.type === "open" &&
      ans.isVague === true &&
      ans.followups &&
      ans.followups.length > 0
    ) {
      pendingFollowupsRef.current = ans.followups;
      setShowFollowups(true);
    } else {
      setShowFollowups(false);
      pendingFollowupsRef.current = null;
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentStep, currentQuestion?.id]);

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

  // Keep answersRef in sync so navigation effects always see the latest data.
  useEffect(() => {
    answersRef.current = answers;
  }, [answers]);

  const updateAnswer = (qId: string, update: Partial<AnswerState>) => {
    if (irrelevantError && update.value !== undefined) setIrrelevantError("");
    setAnswers((prev) => {
      const existing = prev[qId] || defaultAnswer;
      // If the answer text changed, wipe vagueness/followup state so the next
      // Next click re-runs the check against the new text.
      const textChanged = update.value !== undefined && update.value !== existing.value;
      if (textChanged) {
        setShowFollowups(false);
        pendingFollowupsRef.current = null;
      }
      const reset = textChanged ? { isVague: undefined, followups: undefined, followupAnswers: undefined, missingInfoTypes: undefined } : {};
      const next = { ...prev, [qId]: { ...existing, ...reset, ...update } };
      answersRef.current = next;
      return next;
    });
  };

  const saveCurrentAnswer = useCallback(async (overrides?: Partial<AnswerState>) => {
    if (!currentQuestion || !submissionId) return;
    const existing = answersRef.current[currentQuestion.id] || defaultAnswer;
    const ans = { ...existing, ...overrides };
    const rawValue = currentQuestion.type === "multi"
      ? (ans.multiValues.length > 0 ? JSON.stringify(ans.multiValues) : "")
      : ans.value;

    // Never save an empty answer — skipped questions should not create DB rows
    if (!rawValue || !rawValue.trim()) return;

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
  }, [currentQuestion, submissionId, defaultAnswer]);

  const advanceToNext = useCallback(async (overrides?: Partial<AnswerState>) => {
    await saveCurrentAnswer(overrides);

    // Always read from answersRef — it's kept in sync synchronously in updateAnswer,
    // so it reflects followupAnswers/isVague even if React hasn't re-rendered yet.
    const latestAnswers = answersRef.current;

    // Edit-return mode: go back to review page after saving
    if (editReturnMode) {
      const updatedAnswers = { ...latestAnswers };
      if (currentQuestion && overrides) {
        updatedAnswers[currentQuestion.id] = { ...(updatedAnswers[currentQuestion.id] || defaultAnswer), ...overrides };
      }
      console.log("[ADVANCE-EDIT] writing review_answers for", currentQuestion?.id, ":", JSON.stringify(updatedAnswers[currentQuestion?.id || ""]));
      sessionStorage.setItem("review_answers", JSON.stringify(updatedAnswers));
      setEditReturnMode(false);
      router.push(`/c/${cohortId}/review`);
      return;
    }

    if (currentStep < visibleQuestions.length - 1) {
      setCurrentStep(currentStep + 1);
    } else {
      // Last question: save answers and go to review page
      const allAnswers = { ...latestAnswers };
      if (currentQuestion && overrides) {
        allAnswers[currentQuestion.id] = { ...(allAnswers[currentQuestion.id] || defaultAnswer), ...overrides };
      }
      sessionStorage.setItem("review_answers", JSON.stringify(allAnswers));
      router.push(`/c/${cohortId}/review`);
    }
  }, [saveCurrentAnswer, currentStep, visibleQuestions.length, cohortId, router, editReturnMode, currentQuestion, defaultAnswer]);

  const handleNext = async () => {
    if (!currentQuestion) return;
    setIrrelevantError("");

    // Flush any unsaved typed text from the panel before proceeding
    if (showFollowups && followUpPanelRef.current) {
      const panelAnswers = followUpPanelRef.current.getCurrentAnswers();
      if (panelAnswers.followup_1_answer || panelAnswers.followup_2_answer) {
        updateAnswer(currentQuestion.id, { followupAnswers: panelAnswers });
      }
    }

    const ans = getAnswer(currentQuestion.id);

    // Run vagueness check whenever: open question, has text, not yet checked.
    // isVague is reset to undefined whenever the answer text changes, so editing
    // and re-typing always re-arms this check.
    const needsVaguenessCheck =
      currentQuestion.type === "open" &&
      ans.value.trim().length > 0 &&
      ans.isVague === undefined;

    if (needsVaguenessCheck) {
      setCheckingVagueness(true);
      try {
        // Single round-trip: vagueness + followups together
        const result = await api.checkWithFollowups(currentQuestion.text, ans.value);

        if (result.is_irrelevant) {
          setIrrelevantError("Your answer doesn't seem related to this question. Please try again or skip to the next question.");
          updateAnswer(currentQuestion.id, { isVague: undefined });
          setCheckingVagueness(false);
          return;
        }

        if (result.is_vague && result.followups.length > 0) {
          pendingFollowupsRef.current = result.followups;
          updateAnswer(currentQuestion.id, {
            isVague: true,
            missingInfoTypes: result.missing_info_types,
            followups: result.followups,
          });
          setShowFollowups(true);
          setCheckingVagueness(false);
          trackEvent("followup_triggered", {
            question_id: currentQuestion.id,
            num_followups: result.followups.length,
          }, cohortId);
          return;
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

    // Advance — follow-ups (if any) have already been answered or the
    // user is choosing to proceed without them.
    await advanceToNext();
  };

  // Called by FollowUpPanel immediately when any follow-up answer is saved/skipped.
  // Persists to the backend right away — no need to wait for main Next.
  const handleFollowupAnswerSaved = useCallback(async (followupAnswers: {
    followup_1_answer?: string;
    followup_2_answer?: string;
  }) => {
    if (!currentQuestion || !submissionId) return;
    // Use answersRef (always current) so we never read a stale closure value
    const defaultAns = { value: "", multiValues: [], inputMode: "voice" as const };
    const currentAns = answersRef.current[currentQuestion.id] ?? defaultAns;
    const ans = { ...currentAns, followupAnswers };
    updateAnswer(currentQuestion.id, { followupAnswers });

    console.log("[FOLLOWUP-SAVED] followupAnswers:", followupAnswers, "ans:", JSON.stringify(ans));
    // Always persist to sessionStorage immediately — don't wait for advanceToNext.
    // Read the current review_answers if it exists, merge in the updated answer.
    // This ensures the data survives even if advanceToNext has a stale closure.
    try {
      const latestForStorage = { ...answersRef.current, [currentQuestion.id]: ans };
      const existingReview = sessionStorage.getItem("review_answers");
      if (existingReview) {
        const parsed = JSON.parse(existingReview);
        sessionStorage.setItem("review_answers", JSON.stringify({ ...parsed, [currentQuestion.id]: ans }));
      } else {
        // No review_answers yet (first pass through survey) — write it anyway
        sessionStorage.setItem("review_answers", JSON.stringify(latestForStorage));
      }
    } catch { /* ignore storage errors */ }

    trackEvent("followup_answered", {
      question_id: currentQuestion.id,
      followup_1_answered: !!followupAnswers.followup_1_answer,
      followup_2_answered: !!followupAnswers.followup_2_answer,
    }, cohortId);
    // Save immediately to backend
    const rawValue = ans.value;
    if (!rawValue?.trim()) return;
    try {
      await api.saveAnswer(submissionId, {
        question_id: currentQuestion.id,
        question_type: currentQuestion.type,
        answer_raw: rawValue,
        input_mode: ans.inputMode,
        transcript: ans.transcript,
        is_vague: ans.isVague,
        followups_asked: ans.followups?.length || 0,
        followup_1: ans.followups?.[0],
        followup_1_answer: followupAnswers.followup_1_answer,
        followup_2: ans.followups?.[1],
        followup_2_answer: followupAnswers.followup_2_answer,
      });
    } catch {
      // Silently fail — will retry on main save
    }
  }, [currentQuestion, submissionId, cohortId]);

  // Called by FollowUpPanel after follow-up 1 is answered, to check if follow-up 2 is needed.
  // Returns a new follow-up question string if vague, or null if not.
  const handleCheckFollowupVagueness = useCallback(async (
    followupQuestion: string,
    followupAnswer: string,
    _followupIndex: number,
  ): Promise<string | null> => {
    if (!currentQuestion) return null;
    setCheckingFollowupVagueness(true);
    try {
      const result = await api.checkWithFollowups(followupQuestion, followupAnswer);
      if (!result.is_vague || result.is_irrelevant) return null;
      return result.followups[0] ?? null;
    } catch {
      return null;
    } finally {
      setCheckingFollowupVagueness(false);
    }
  }, [currentQuestion]);

  const handlePrev = () => {
    if (currentStep > 0) {
      setShowFollowups(false);
      pendingFollowupsRef.current = null;
      setCurrentStep(currentStep - 1);
    }
  };

  const isCurrentValid = () => {
    if (!currentQuestion) return false;
    const ans = getAnswer(currentQuestion.id);

    // Block Next only while a voice recording is actively in progress
    // (voiceConfirmed=false means recording started but not yet submitted).
    // voiceConfirmed=undefined means the user hasn't touched recording at all —
    // that's fine, they can skip forward.
    if (
      currentQuestion.type === "open" &&
      ans.voiceConfirmed === false
    ) {
      return false;
    }

    // Open questions are always skippable — never block Next just because
    // the field is empty, even if required (required only gates submission).
    if (currentQuestion.type === "open") return true;

    if (!currentQuestion.required) return true;
    if (currentQuestion.type === "multi") return ans.multiValues.length > 0;
    return ans.value.trim().length > 0;
  };

  // Resolve followups: prefer live answer state, fall back to ref (handles render timing)
  const resolvedFollowups =
    (currentQuestion ? getAnswer(currentQuestion.id).followups : undefined) ??
    pendingFollowupsRef.current ??
    undefined;

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
                initialInputMode={getAnswer(currentQuestion.id).inputMode}
                onInputModeChange={(mode) =>
                  updateAnswer(currentQuestion.id, { inputMode: mode, voiceConfirmed: undefined })
                }
                onTranscriptReady={(transcript) =>
                  updateAnswer(currentQuestion.id, { transcript, value: transcript, voiceConfirmed: true })
                }
                onRecordingStarted={() =>
                  updateAnswer(currentQuestion.id, { voiceConfirmed: false })
                }
              />
            )}

            {showFollowups && resolvedFollowups && (
              <FollowUpPanel
                key={`followup-${currentQuestion.id}`}
                ref={followUpPanelRef}
                followups={resolvedFollowups}
                onAnswerSaved={handleFollowupAnswerSaved}
                onCheckFollowupVagueness={handleCheckFollowupVagueness}
                onFollowupsUpdated={(updatedFollowups) => {
                  if (!currentQuestion) return;
                  updateAnswer(currentQuestion.id, { followups: updatedFollowups });
                  pendingFollowupsRef.current = updatedFollowups;
                }}
                initialAnswers={getAnswer(currentQuestion.id).followupAnswers}
                checkingVagueness={checkingFollowupVagueness}
              />
            )}
          </QuestionCard>
        )}

        {irrelevantError && (
          <div className="max-w-3xl mx-auto bg-brand-red/5 border border-brand-red/20 rounded-xl px-4 py-3 flex items-start gap-3">
            <span className="text-brand-red text-lg shrink-0">!</span>
            <div>
              <p className="text-sm text-brand-red/80">{irrelevantError}</p>
              <button
                type="button"
                onClick={() => setIrrelevantError("")}
                className="text-xs text-brand-red/50 hover:text-brand-red/80 mt-1 underline"
              >
                Dismiss
              </button>
            </div>
          </div>
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
            disabled={!isCurrentValid() || saving || checkingVagueness}
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
