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
import { NpsQuestion } from "@/components/NpsQuestion";
import { SliderQuestion } from "@/components/SliderQuestion";
import { MatrixQuestion } from "@/components/MatrixQuestion";
import { RankingQuestion } from "@/components/RankingQuestion";
import { YesNoQuestion } from "@/components/YesNoQuestion";
import { DropdownQuestion, ShortTextQuestion, DateQuestion } from "@/components/SimpleQuestions";
import { FollowUpPanel, type FollowUpPanelHandle } from "@/components/FollowUpPanel";
import { PrivacyFooter } from "@/components/PrivacyFooter";
import { api, type SurveyQuestion } from "@/lib/api";
import {
  initSession,
  sendClientEnv,
  setContext,
  trackDropout,
  trackEvent,
  trackInputModeSwitched,
  trackPageView,
  trackQuestionStarted,
} from "@/lib/analytics";
import { detectPii, summarisePii, summariseCategoryList } from "@/lib/pii";

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
  // Surfaces a "Couldn't load — Retry" shell when GET /v1/survey fails.
  // Without this, a single bad request leaves the user staring at an
  // infinite spinner with no way to recover short of a full reload.
  const [loadError, setLoadError] = useState(false);
  // Bumping this re-runs the mount effect (which is the load path) so the
  // Retry button doesn't need its own duplicate fetch logic.
  const [retryCount, setRetryCount] = useState(0);
  const [saving, setSaving] = useState(false);
  const [showFollowups, setShowFollowups] = useState(false);
  const [checkingVagueness, setCheckingVagueness] = useState(false);
  const [checkingFollowupVagueness, setCheckingFollowupVagueness] = useState(false);
  // Single in-flight guard for the entire ``handleNext`` pipeline so a
  // user double-clicking Next during the PII / vagueness AI gate can't
  // fire two parallel runs. Uses BOTH a ref (synchronous re-entry block)
  // and a state (so the Button can re-render disabled). ``checkingVagueness``
  // alone wasn't enough because it isn't set until after ``api.checkPii``
  // resolves, leaving a ~1-2s window where Next remained clickable.
  const nextInFlightRef = useRef(false);
  const [nextInFlight, setNextInFlight] = useState(false);
  // F8: surface silent saveAnswer failures so a user whose connection
  // dropped mid-survey doesn't sail through to the review screen
  // believing every answer was persisted. Auto-clears on the next
  // successful save.
  const [saveError, setSaveError] = useState(false);
  const [editReturnMode, setEditReturnMode] = useState(false);
  const [irrelevantError, setIrrelevantError] = useState("");
  // Surface when an AI check fails so the user can retry instead of silently
  // advancing past follow-up questions they never got to see.
  const [aiCheckError, setAiCheckError] = useState("");
  // Informational amber banner used for "we removed personal info" notices.
  // Kept separate from irrelevantError so it survives step advances — otherwise
  // a complete-answer-with-PII would flash the notice for ~1s during the AI
  // spinner, then have it wiped by the step-change clear effect before the
  // user could read it.
  const [piiNotice, setPiiNotice] = useState("");
  // pendingFollowups holds followup questions between state-setting and render
  const pendingFollowupsRef = useRef<string[] | null>(null);
  // answersRef always points to the latest answers — used in effects that must
  // not re-run on every keystroke but still need fresh answer data.
  const answersRef = useRef<Record<string, AnswerState>>({});
  // Ref to the FollowUpPanel so we can flush any unsaved typed text on Next click
  const followUpPanelRef = useRef<FollowUpPanelHandle>(null);
  // Idempotency guard for the mount effect. React Strict Mode invokes mount
  // effects twice in dev, and the second invocation must NOT undo the first
  // run's edit-target navigation. Without this, the second pass falls into
  // the "existingData" branch below and overwrites currentStep with
  // firstUnanswered — which made every Edit button open the same question.
  const mountInitDoneRef = useRef(false);

  const submissionId = typeof window !== "undefined" ? sessionStorage.getItem("submission_id") : null;

  // Canonicalize the URL when the user reached us via a historical alias
  // (an old slug stored in ``previous_slugs``). The survey API echoes the
  // current slug back, so a mismatch with the URL param means we should
  // ``router.replace()`` to the canonical URL. Runs once per mount and is
  // independent of the question-loading logic below.
  const canonicalizedRef = useRef(false);
  useEffect(() => {
    if (canonicalizedRef.current) return;
    canonicalizedRef.current = true;
    api
      .getSurvey(cohortId)
      .then((cfg) => {
        if (cfg.slug && cfg.slug !== cohortId) {
          router.replace(`/c/${cfg.slug}/survey`);
        }
      })
      .catch(() => {
        // Network failure here is non-fatal — the main load logic below
        // surfaces its own retry UI.
      });
  }, [cohortId, router]);

  useEffect(() => {
    if (!submissionId) {
      router.replace(`/c/${cohortId}`);
      return;
    }

    if (mountInitDoneRef.current) return;
    mountInitDoneRef.current = true;

    // Clear any prior load error so the spinner shows on retry instead of
    // the error shell.
    setLoadError(false);

    const editMode = typeof window !== "undefined" ? sessionStorage.getItem("edit_mode") : null;
    const editQuestionId = typeof window !== "undefined" ? sessionStorage.getItem("edit_question_id") : null;

    if (editMode === "true" && editQuestionId) {
      // Restore answers from sessionStorage
      let restoredAnswers: Record<string, AnswerState> = {};
      const savedAnswers = sessionStorage.getItem("review_answers");
      if (savedAnswers) {
        try {
          restoredAnswers = JSON.parse(savedAnswers);
          setAnswers(restoredAnswers);
          answersRef.current = restoredAnswers;
        } catch {}
      }

      // We deliberately leave ``edit_mode`` / ``edit_question_id`` in
      // sessionStorage until the edit-return Save handler runs (handleNext),
      // so a refresh mid-edit lands the user back on the same question
      // rather than jumping to firstUnanswered.

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
      }).catch(() => {
        // Network/server failure: surface a Retry shell instead of a
        // permanent spinner. The retry button bumps retryCount which
        // re-runs this effect.
        setLoading(false);
        setLoadError(true);
      });
      return;
    }

    // If question_data already exists (e.g. React Strict Mode double-invoke,
    // or returning from edit), reuse it — never call the API again, which
    // would re-randomize the question order.
    const existingData = sessionStorage.getItem("question_data");
    if (existingData) {
      try {
        const parsedQuestions: SurveyQuestion[] = JSON.parse(existingData);
        setQuestions(parsedQuestions);

        // Restore in-progress answers when the user returns to /survey via
        // the browser (e.g. Back to consent → Forward, or Back from
        // /review). The survey page's `answers` and `currentStep` live in
        // React state, so without an explicit restore the user would land
        // back on Q1 with an empty form even though `review_answers` is
        // still in sessionStorage. Jump them to the first unanswered
        // visible question so they can continue right where they left off.
        const savedAnswers = sessionStorage.getItem("review_answers");
        if (savedAnswers) {
          try {
            const restored: Record<string, AnswerState> = JSON.parse(savedAnswers);
            setAnswers(restored);
            answersRef.current = restored;
            const visible = parsedQuestions.filter((q) => {
              if (!q.condition) return true;
              const dep = restored[q.condition.question_id];
              if (!dep) return false;
              if (q.condition.operator === "not_equals") {
                return dep.value !== q.condition.value;
              }
              return dep.value === q.condition.value;
            });
            const firstUnanswered = visible.findIndex((q) => {
              const a = restored[q.id];
              if (!a) return true;
              if (q.type === "multi" || q.type === "ranking") {
                return !a.multiValues || a.multiValues.length === 0;
              }
              return !a.value;
            });
            setCurrentStep(
              firstUnanswered >= 0
                ? firstUnanswered
                : Math.max(visible.length - 1, 0)
            );
          } catch {
            // Corrupted review_answers — ignore and start fresh on Q1.
          }
        }

        setLoading(false);
        return;
      } catch {
        // Corrupted question_data — fall through to fetch fresh.
        sessionStorage.removeItem("question_data");
      }
    }

    api.getSurvey(cohortId).then(async (data) => {
      setQuestions(data.survey.questions);
      sessionStorage.setItem("question_order", JSON.stringify(data.survey.questions.map((q: SurveyQuestion) => q.id)));
      sessionStorage.setItem("question_data", JSON.stringify(data.survey.questions));

      // Resume after tab close: sessionStorage is empty (so we landed in
      // this fresh-load branch instead of the existingData branch above)
      // but the DB may still have answers from an earlier in-progress
      // attempt. Pull them back and rebuild ``review_answers`` so the form
      // shows what the learner already wrote, and the review page's
      // summary stays in sync with the form.
      try {
        const saved = await api.getSubmissionAnswers(submissionId);
        if (saved.answers && saved.answers.length > 0) {
          const restored: Record<string, AnswerState> = {};
          for (const a of saved.answers) {
            const inputMode: "text" | "voice" = a.input_mode === "text" ? "text" : "voice";
            const followupAnswers = a.followup_1_answer || a.followup_2_answer
              ? {
                  followup_1_answer: a.followup_1_answer || undefined,
                  followup_2_answer: a.followup_2_answer || undefined,
                }
              : undefined;
            restored[a.question_id] = {
              value: a.value || "",
              multiValues: a.multi_values || [],
              inputMode,
              transcript: a.transcript || undefined,
              isVague: a.is_vague ?? undefined,
              followups: a.followups && a.followups.length > 0 ? a.followups : undefined,
              followupAnswers,
            };
          }
          setAnswers(restored);
          answersRef.current = restored;
          try {
            sessionStorage.setItem("review_answers", JSON.stringify(restored));
          } catch {}

          // Place the learner on the first unanswered visible question so
          // they pick up where they left off rather than re-typing Q1.
          const visible = data.survey.questions.filter((q: SurveyQuestion) => {
            if (!q.condition) return true;
            const dep = restored[q.condition.question_id];
            if (!dep) return false;
            if (q.condition.operator === "not_equals") return dep.value !== q.condition.value;
            return dep.value === q.condition.value;
          });
          const firstUnanswered = visible.findIndex((q) => {
            const a = restored[q.id];
            if (!a) return true;
            if (q.type === "multi" || q.type === "ranking") {
              return !a.multiValues || a.multiValues.length === 0;
            }
            return !a.value;
          });
          setCurrentStep(firstUnanswered >= 0 ? firstUnanswered : Math.max(visible.length - 1, 0));
        }
      } catch {
        // 404/409/network — nothing to resume from, start with a blank form.
        // The /complete and /preview-extraction paths share the same token
        // gate so a sealed submission can't reach this branch anyway.
      }

      setLoading(false);
    }).catch(() => {
      // First-load failure → show Retry shell. Without this catch, the
      // page would hang on the loading spinner forever on a single bad
      // network request.
      setLoading(false);
      setLoadError(true);
    });

    initSession();
    setContext(cohortId, submissionId || undefined);
    trackPageView("survey", cohortId);
    if (submissionId) {
      // Fire-and-forget — captures browser/OS/device for H6 compatibility.
      void sendClientEnv(submissionId);
    }
  // retryCount is here so the Retry button can re-run this whole effect
  // without us having to duplicate the load logic in a separate handler.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cohortId, submissionId, router, retryCount]);

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
  // had follow-ups generated (e.g. user went Back, or is editing from review).
  //
  // Reads from `answers` state (not `answersRef`) because on edit-mode
  // restoration the ref gets overwritten by the sync effect below before this
  // effect runs on the post-restore render. The render closure's `answers`
  // value, however, always reflects the current render's state — so it has
  // the restored data when this effect re-runs after the question id changes.
  useEffect(() => {
    if (!currentQuestion) return;
    const defaultAns: AnswerState = { value: "", multiValues: [], inputMode: "voice" };
    const ans = answers[currentQuestion.id] ?? defaultAns;
    if (
      currentQuestion.type === "open" &&
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
    trackQuestionStarted(currentQuestion.id, currentStep, currentQuestion.type);

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

  // Clear transient error banners when the user moves between questions so a
  // "network hiccup" or "does not seem to answer" message from question N
  // doesn't hang around on question N+1. ``piiNotice`` is intentionally
  // NOT cleared here — we want the "we removed personal info" banner to
  // stay visible on the next question so the user actually sees it (for
  // complete answers we advance immediately after the AI check, which was
  // wiping the banner before anyone could read it). It's cleared elsewhere
  // when the user dismisses it or edits the PII out.
  useEffect(() => {
    setIrrelevantError("");
    setAiCheckError("");
  }, [currentStep]);

  const updateAnswer = (qId: string, update: Partial<AnswerState>) => {
    if (irrelevantError && update.value !== undefined) setIrrelevantError("");
    // If the answer text changed, re-scan for PII so the notice clears as
    // soon as the user edits the offending bit out (and refreshes if they
    // swap one piece of PII for another).
    if (update.value !== undefined) {
      const matches = detectPii(update.value);
      if (matches.length === 0) {
        if (piiNotice) setPiiNotice("");
      } else {
        setPiiNotice(
          `Your response contains personal information (${summarisePii(matches)}). We'll remove it before saving on our end — you can keep going.`,
        );
      }
    }
    setAnswers((prev) => {
      const existing = prev[qId] || defaultAnswer;
      // If the answer text changed, wipe vagueness/followup state so the next
      // Next click re-runs the check against the new text.
      // In edit-return mode, preserve followup data — the user is editing within
      // an existing conversation thread (e.g. fixing a typo) and followups should
      // stay visible. Vagueness will be re-checked on "Back to Review" if needed.
      const textChanged = update.value !== undefined && update.value !== existing.value;
      if (textChanged && !editReturnMode) {
        setShowFollowups(false);
        pendingFollowupsRef.current = null;
      }
      const reset = (textChanged && !editReturnMode) ? { isVague: undefined, followups: undefined, followupAnswers: undefined, missingInfoTypes: undefined } : {};
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
      // Successful save — clear any previously surfaced save error.
      setSaveError(false);
      trackEvent("question_answer", {
        question_id: currentQuestion.id,
        question_type: currentQuestion.type,
        input_mode: currentQuestion.type === "open" ? ans.inputMode : "none",
        has_answer: !!rawValue,
      }, cohortId);
    } catch {
      // F8: surface the failure so the user knows the answer didn't
      // persist. We still let them advance — the next save will retry
      // and clear the banner if it succeeds.
      setSaveError(true);
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
      sessionStorage.setItem("review_answers", JSON.stringify(updatedAnswers));
      // Edit complete — clear the targeting flags so a subsequent /survey
      // visit (e.g. browser Back) doesn't reopen this question, and signal
      // that the review page must regenerate the AI summary because
      // answers actually changed.
      sessionStorage.removeItem("edit_mode");
      sessionStorage.removeItem("edit_question_id");
      sessionStorage.setItem("extraction_dirty", "1");
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
    // Synchronous re-entry block: the second click of a double-click
    // arrives in the same tick before React has had a chance to flip
    // ``nextInFlight`` to true and re-render the disabled button.
    if (nextInFlightRef.current) return;
    nextInFlightRef.current = true;
    setNextInFlight(true);
    try {
      await runHandleNext();
    } finally {
      nextInFlightRef.current = false;
      setNextInFlight(false);
    }
  };

  const runHandleNext = async () => {
    if (!currentQuestion) return;
    setIrrelevantError("");
    setAiCheckError("");

    // Flush any unsaved typed text from the panel before proceeding.
    // B8: always propagate the panel state (even when all fields are empty)
    // so cleared follow-up answers don't leave stale text in sessionStorage.
    if (showFollowups && followUpPanelRef.current) {
      const panelAnswers = followUpPanelRef.current.getCurrentAnswers();
      updateAnswer(currentQuestion.id, { followupAnswers: panelAnswers });
    }

    const ans = getAnswer(currentQuestion.id);

    // Client-side PII scan: if the answer contains email / phone / address /
    // SSN / etc., surface a friendly notice in the dedicated ``piiNotice``
    // amber banner. We deliberately do NOT use ``irrelevantError`` for this
    // — that banner is cleared on every step change (see the effect on
    // ``currentStep``), which meant the PII notice only stayed visible for
    // the ~1-2s the AI spinner was running for "complete" answers before
    // being wiped. The backend strips PII on every save, so this is purely
    // informational and never blocks.
    // PII scan on Next: client regex first (catches obvious cases even if
    // the backend is slow/down), then AI-backed check for names and soft
    // addresses that regex can't reach. Merge the two category sets so the
    // banner lists everything we'd scrub on save.
    if (currentQuestion.type === "open" && ans.value.trim().length > 0) {
      const localMatches = detectPii(ans.value);
      const merged = new Set<string>(localMatches.map((m) => m.category));
      try {
        const remote = await api.checkPii(ans.value);
        if (remote.found) {
          for (const cat of remote.categories) merged.add(cat);
        }
      } catch {
        // Transport / 5xx — fall back to client regex only. Do not block;
        // the authoritative scrub still runs on save.
      }
      if (merged.size > 0) {
        setPiiNotice(
          `Your response contains personal information (${summariseCategoryList(Array.from(merged))}). We'll remove it before saving on our end — you can keep going.`,
        );
      } else {
        setPiiNotice("");
      }
    }

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

        // Backend returns `error: true` when the AI call itself failed
        // (timeout, rate limit, malformed JSON). Surface it so the user can
        // retry rather than being silently pushed past a follow-up that
        // never got the chance to load. See B1/B3 in plan.
        if (result.error) {
          setAiCheckError(
            "We couldn't analyse your answer right now. Please try again, or continue to submit as-is."
          );
          updateAnswer(currentQuestion.id, { isVague: undefined });
          trackEvent("ai_check_failed", {
            question_id: currentQuestion.id,
            stage: "initial",
          }, cohortId);
          setCheckingVagueness(false);
          return;
        }

        // is_irrelevant used to block with a red "does not seem to answer"
        // banner. We intentionally no longer block here: a re-recorded voice
        // answer that the model misclassifies, or a PII-heavy answer that
        // looks like "*** *** ***" after server-side stripping, should flow
        // through the same paths as vague-with-followups or accept-as-is.
        // Any PII notice has already been surfaced above via detectPii.

        // Treat is_vague and is_irrelevant the same way from the
        // follow-up perspective: both mean "we need another chance to
        // hear more". The only reason to skip a follow-up is when the
        // participant explicitly declined ("nothing", "not sure"),
        // which the backend flags as declined=true.
        const needsClarification =
          (result.is_vague || result.is_irrelevant) && !result.declined;

        if (needsClarification) {
          // Use AI-generated follow-ups when they exist; otherwise drop
          // in a single generic clarifier so the user isn't silently
          // advanced past what they expected to be a chance to
          // elaborate. This covers the case where the model classifies
          // a re-recorded voice answer as is_irrelevant (no follow-ups
          // generated per prompt rules) — the user expects the same
          // clarification prompt they got the first time.
          const aiFollowups = result.followups;
          const followups = aiFollowups.length > 0
            ? aiFollowups
            : ["Could you share a bit more detail about what you mean — a specific example, outcome, or challenge?"];

          pendingFollowupsRef.current = followups;
          updateAnswer(currentQuestion.id, {
            isVague: true,
            missingInfoTypes: result.missing_info_types,
            followups,
          });
          setShowFollowups(true);
          setCheckingVagueness(false);
          trackEvent(
            "followup_triggered",
            {
              question_id: currentQuestion.id,
              num_followups: followups.length,
              source: aiFollowups.length > 0 ? "ai" : "fallback_irrelevant",
            },
            cohortId,
          );
          return;
        }

        // Declined or complete — accept as-is and fall through to
        // advanceToNext(). Preserve the "needs clarification" signal for
        // review/analytics by folding is_irrelevant into isVague: a user
        // who declined after an irrelevant classification still had an
        // answer the model couldn't make sense of, and the review page
        // should reflect that.
        updateAnswer(currentQuestion.id, {
          isVague: Boolean(result.is_vague || result.is_irrelevant),
          missingInfoTypes: result.missing_info_types,
        });
      } catch (err) {
        // Transport-level failure (network, 5xx). Don't silently advance —
        // let the user see the issue and decide to retry.
        setAiCheckError(
          "Network hiccup while checking your answer. Tap Next again to retry, or continue."
        );
        trackEvent("ai_check_failed", {
          question_id: currentQuestion.id,
          stage: "initial",
          error_message: err instanceof Error ? err.message.slice(0, 120) : "unknown",
        }, cohortId);
        // Mark as "checked" so a second Next click proceeds without looping.
        updateAnswer(currentQuestion.id, { isVague: false });
        setCheckingVagueness(false);
        return;
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
    followup_1_input_mode?: string;
    followup_2_input_mode?: string;
  }) => {
    if (!currentQuestion || !submissionId) return;
    // Use answersRef (always current) so we never read a stale closure value
    const defaultAns = { value: "", multiValues: [], inputMode: "voice" as const };
    const currentAns = answersRef.current[currentQuestion.id] ?? defaultAns;
    const ans = { ...currentAns, followupAnswers };
    updateAnswer(currentQuestion.id, { followupAnswers });

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
        followup_1_input_mode: followupAnswers.followup_1_input_mode,
        followup_2: ans.followups?.[1],
        followup_2_answer: followupAnswers.followup_2_answer,
        followup_2_input_mode: followupAnswers.followup_2_input_mode,
      });
      setSaveError(false);
    } catch {
      // F8: same banner as the main save site so a follow-up that
      // failed to persist (e.g. mid-survey network drop) is visible to
      // the participant rather than silently lost.
      setSaveError(true);
    }
  }, [currentQuestion, submissionId, cohortId]);

  // Called by FollowUpPanel after follow-up 1 is answered, to check if follow-up 2 is needed.
  // Returns a new follow-up question string if vague, or null if not.
  //
  // Uses the context-aware ``/v1/ai/check-followup`` endpoint (not the generic
  // ``/v1/ai/check``) so the model receives the original main question +
  // answer alongside the follow-up Q+A. This lets the server-side prompt
  // apply a stricter bar — the participant has already had one clarification
  // chance, so we only ask again if another round would genuinely add signal.
  const handleCheckFollowupVagueness = useCallback(async (
    followupQuestion: string,
    followupAnswer: string,
    _followupIndex: number,
  ): Promise<string | null> => {
    if (!currentQuestion) return null;
    // Read from answersRef for the freshest original-answer text — handles
    // the user switching input modes mid-followup etc.
    const originalAnswer = answersRef.current[currentQuestion.id]?.value ?? "";
    setCheckingFollowupVagueness(true);
    try {
      const result = await api.checkFollowupForClarification({
        original_question: currentQuestion.text,
        original_answer: originalAnswer,
        followup_question: followupQuestion,
        followup_answer: followupAnswer,
      });
      // `error: true` means the AI call failed (timeout / rate limit /
      // malformed JSON). Surface it so the user can retry instead of
      // silently losing their shot at a second follow-up — the main
      // question path does the same via ``aiCheckError``.
      if (result.error) {
        setAiCheckError(
          "We couldn't check if a second follow-up is needed. You can continue, or retry.",
        );
        trackEvent("ai_check_failed", {
          question_id: currentQuestion.id,
          stage: "followup",
        }, cohortId);
        return null;
      }
      // Align F2 gating with the main-question branch in ``handleNext``:
      // treat ``is_irrelevant`` the same as ``is_vague`` and only bail
      // out when the participant explicitly declined. Previously a PII-
      // heavy or terse F1 answer that the model marked irrelevant
      // silently suppressed F2.
      if (result.declined) return null;
      const needsClarification = result.is_vague || result.is_irrelevant;
      if (!needsClarification) return null;
      return result.followups[0] ?? null;
    } catch (err) {
      // Transport-level failure — don't fail silently, mirror the main
      // question's "network hiccup" banner.
      setAiCheckError(
        "Network hiccup while checking for a second follow-up. You can continue, or retry.",
      );
      trackEvent("ai_check_failed", {
        question_id: currentQuestion.id,
        stage: "followup",
        error_message: err instanceof Error ? err.message.slice(0, 120) : "unknown",
      }, cohortId);
      return null;
    } finally {
      setCheckingFollowupVagueness(false);
    }
  }, [currentQuestion, cohortId]);

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
    if (currentQuestion.type === "matrix") {
      // Matrix requires every row answered
      try {
        const parsed = ans.value ? JSON.parse(ans.value) : {};
        const rowCount = currentQuestion.rows?.length ?? 0;
        return Object.keys(parsed).length >= rowCount && rowCount > 0;
      } catch {
        return false;
      }
    }
    if (currentQuestion.type === "ranking") {
      // Ranking: always has a default order once rendered
      return (currentQuestion.options?.length ?? 0) > 0;
    }
    return ans.value.trim().length > 0;
  };

  // Resolve followups: prefer live answer state, fall back to ref (handles render timing)
  const resolvedFollowups =
    (currentQuestion ? getAnswer(currentQuestion.id).followups : undefined) ??
    pendingFollowupsRef.current ??
    undefined;

  if (loadError) {
    return (
      <div className="min-h-screen bg-brand-light-blue/40 flex items-center justify-center px-6">
        <div role="alert" className="max-w-md text-center space-y-4">
          <h1 className="text-xl font-serif text-brand-blue">
            We couldn&apos;t load the survey
          </h1>
          <p className="text-sm text-brand-blue/70">
            Check your connection and try again. Your progress is saved.
          </p>
          <Button
            type="button"
            onClick={() => {
              setLoadError(false);
              setLoading(true);
              mountInitDoneRef.current = false;
              setRetryCount((n) => n + 1);
            }}
            className="bg-brand-blue hover:bg-brand-blue/90"
          >
            Try again
          </Button>
        </div>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-brand-light-blue/40 flex items-center justify-center">
        <Loader2 className="h-8 w-8 motion-safe:animate-spin text-brand-blue" />
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
      <main id="main" tabIndex={-1} className="max-w-3xl mx-auto px-4 space-y-6 focus:outline-none">
        <h1 className="sr-only">Course feedback survey</h1>
        <ProgressBar current={currentStep + 1} total={visibleQuestions.length} />

        {currentQuestion && (
          <QuestionCard
            text={currentQuestion.text}
            description={currentQuestion.description}
            required={currentQuestion.required}
            headingId={`question-heading-${currentQuestion.id}`}
            descriptionId={currentQuestion.description ? `question-desc-${currentQuestion.id}` : undefined}
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

            {currentQuestion.type === "nps" && (
              <NpsQuestion
                value={getAnswer(currentQuestion.id).value}
                onChange={(v) => updateAnswer(currentQuestion.id, { value: v })}
                labels={currentQuestion.labels}
              />
            )}

            {currentQuestion.type === "slider" && (
              <SliderQuestion
                value={getAnswer(currentQuestion.id).value}
                onChange={(v) => updateAnswer(currentQuestion.id, { value: v })}
                min={currentQuestion.scale_min}
                max={currentQuestion.scale_max}
                step={currentQuestion.scale_step}
                labels={currentQuestion.labels}
              />
            )}

            {currentQuestion.type === "matrix" && (
              <MatrixQuestion
                rows={currentQuestion.rows || []}
                columns={currentQuestion.options || []}
                value={getAnswer(currentQuestion.id).value}
                onChange={(v) => updateAnswer(currentQuestion.id, { value: v })}
              />
            )}

            {currentQuestion.type === "ranking" && (
              <RankingQuestion
                options={currentQuestion.options || []}
                value={getAnswer(currentQuestion.id).value}
                onChange={(v) => updateAnswer(currentQuestion.id, { value: v })}
              />
            )}

            {currentQuestion.type === "yesno" && (
              <YesNoQuestion
                value={getAnswer(currentQuestion.id).value}
                onChange={(v) => updateAnswer(currentQuestion.id, { value: v })}
              />
            )}

            {currentQuestion.type === "dropdown" && (
              <DropdownQuestion
                options={currentQuestion.options || []}
                value={getAnswer(currentQuestion.id).value}
                onChange={(v) => updateAnswer(currentQuestion.id, { value: v })}
                labelledById={`question-heading-${currentQuestion.id}`}
              />
            )}

            {currentQuestion.type === "short_text" && (
              <ShortTextQuestion
                value={getAnswer(currentQuestion.id).value}
                onChange={(v) => updateAnswer(currentQuestion.id, { value: v })}
                labelledById={`question-heading-${currentQuestion.id}`}
              />
            )}

            {currentQuestion.type === "date" && (
              <DateQuestion
                value={getAnswer(currentQuestion.id).value}
                onChange={(v) => updateAnswer(currentQuestion.id, { value: v })}
                labelledById={`question-heading-${currentQuestion.id}`}
              />
            )}

            {currentQuestion.type === "open" && (
              <OpenEndedQuestion
                key={currentQuestion.id}
                questionId={currentQuestion.id}
                labelledById={`question-heading-${currentQuestion.id}`}
                describedById={
                  irrelevantError
                    ? "survey-irrelevant-error"
                    : currentQuestion.description
                      ? `question-desc-${currentQuestion.id}`
                      : undefined
                }
                invalid={Boolean(irrelevantError)}
                value={getAnswer(currentQuestion.id).value}
                onChange={(v) => updateAnswer(currentQuestion.id, { value: v })}
                voiceEligible={currentQuestion.voice_eligible}
                initialInputMode={getAnswer(currentQuestion.id).inputMode}
                onInputModeChange={(mode) => {
                  const prev = getAnswer(currentQuestion.id).inputMode;
                  if (prev !== mode) {
                    trackInputModeSwitched(currentQuestion.id, prev, mode, "main");
                  }
                  updateAnswer(currentQuestion.id, { inputMode: mode, voiceConfirmed: undefined });
                }}
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
                questionId={currentQuestion.id}
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
                editMode={editReturnMode}
              />
            )}
          </QuestionCard>
        )}

        {irrelevantError && (
          <div
            id="survey-irrelevant-error"
            role="alert"
            aria-live="assertive"
            className="max-w-3xl mx-auto bg-brand-red/5 border border-brand-red/20 rounded-xl px-4 py-3 flex items-start gap-3"
          >
            <span className="text-brand-red text-lg shrink-0" aria-hidden="true">!</span>
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

        {saveError && (
          <div
            role="status"
            aria-live="polite"
            className="max-w-3xl mx-auto bg-amber-50 border border-amber-200 rounded-xl px-4 py-3 flex items-start gap-3"
          >
            <span className="text-amber-600 text-lg shrink-0" aria-hidden="true">!</span>
            <div>
              <p className="text-sm text-amber-700">
                Your last answer didn&apos;t save. Check your connection — we&apos;ll keep retrying as you continue.
              </p>
              <button
                type="button"
                onClick={() => setSaveError(false)}
                className="text-xs text-amber-500 hover:text-amber-700 mt-1 underline"
              >
                Dismiss
              </button>
            </div>
          </div>
        )}

        {aiCheckError && (
          <div
            role="alert"
            aria-live="assertive"
            className="max-w-3xl mx-auto bg-amber-50 border border-amber-200 rounded-xl px-4 py-3 flex items-start gap-3"
          >
            <span className="text-amber-600 text-lg shrink-0" aria-hidden="true">!</span>
            <div>
              <p className="text-sm text-amber-700">{aiCheckError}</p>
              <button
                type="button"
                onClick={() => setAiCheckError("")}
                className="text-xs text-amber-500 hover:text-amber-700 mt-1 underline"
              >
                Dismiss
              </button>
            </div>
          </div>
        )}

        {piiNotice && (
          <div
            role="status"
            aria-live="polite"
            className="max-w-3xl mx-auto bg-brand-red/5 border border-brand-red/20 rounded-xl px-4 py-3 flex items-start gap-3"
          >
            <span className="text-brand-red text-lg shrink-0" aria-hidden="true">!</span>
            <div>
              <p className="text-sm text-brand-red/80">{piiNotice}</p>
              <button
                type="button"
                onClick={() => setPiiNotice("")}
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
            // B4: also block Next while the F2 follow-up vagueness check is
            // in flight so users can't escape mid-evaluation.
            // F7: ``nextInFlight`` covers the whole handleNext pipeline,
            // including the early PII check window before ``checkingVagueness``
            // is set, so a double-click can't fire parallel runs.
            disabled={!isCurrentValid() || saving || checkingVagueness || checkingFollowupVagueness || nextInFlight}
            className="gap-2 bg-brand-blue hover:bg-brand-blue/90 shadow-sm"
          >
            {(checkingVagueness || checkingFollowupVagueness || nextInFlight) && <Loader2 className="h-4 w-4 motion-safe:animate-spin" />}
            {checkingVagueness || checkingFollowupVagueness || nextInFlight
              ? "Analyzing..."
              : editReturnMode
                ? "Back to Review"
                : currentStep === visibleQuestions.length - 1
                  ? "Review"
                  : "Next"}
            {!(checkingVagueness || checkingFollowupVagueness || nextInFlight) && <ChevronRight className="h-4 w-4" />}
          </Button>
        </div>
      </main>
      <PrivacyFooter />
    </div>
  );
}
