"use client";

import { useState, useImperativeHandle, forwardRef, useEffect, useRef } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { MessageCircle, SkipForward, Mic, Type, Pencil, Loader2 } from "lucide-react";
import { VoiceRecorder, type VoiceRecorderHandle } from "./VoiceRecorder";
import { PiiWarning } from "./PiiWarning";
import { trackInputModeSwitched } from "@/lib/analytics";
import { MAX_ANSWER_CHARS } from "@/lib/limits";

interface FollowUpPanelProps {
  followups: string[];
  // Called immediately when each individual follow-up answer is saved/skipped.
  // The parent should persist to the backend and update its state. The
  // ``followup_*_input_mode`` fields reflect the mode (voice/text) the user
  // last interacted with for that follow-up; they're recorded so per-question
  // ``voice / text / mixed / blank`` indicators can be computed downstream.
  onAnswerSaved: (answers: {
    followup_1_answer?: string;
    followup_2_answer?: string;
    followup_1_input_mode?: string;
    followup_2_input_mode?: string;
  }) => void;
  // Called when the follow-up 1 answer is submitted so the parent can check
  // vagueness and optionally append a second follow-up question.
  onCheckFollowupVagueness?: (
    followupQuestion: string,
    followupAnswer: string,
    followupIndex: number,
  ) => Promise<string | null>; // returns a new follow-up question string or null
  // Called when a new follow-up question is dynamically added (so parent can persist it)
  onFollowupsUpdated?: (followups: string[]) => void;
  initialAnswers?: { followup_1_answer?: string; followup_2_answer?: string };
  // Whether a vagueness check is in progress (parent controls spinner)
  checkingVagueness?: boolean;
  // When true, renders all followups with inline-editable textareas (review edit mode)
  editMode?: boolean;
  // Parent question id — used for analytics tagging on sub-events.
  questionId?: string;
}

export interface FollowUpPanelHandle {
  // Returns the current answers in the panel (including any unsaved typed text)
  getCurrentAnswers: () => {
    followup_1_answer?: string;
    followup_2_answer?: string;
    followup_1_input_mode?: string;
    followup_2_input_mode?: string;
  };
}

export const FollowUpPanel = forwardRef<FollowUpPanelHandle, FollowUpPanelProps>(function FollowUpPanel({
  followups: initialFollowups,
  onAnswerSaved,
  onCheckFollowupVagueness,
  onFollowupsUpdated,
  initialAnswers,
  checkingVagueness = false,
  editMode = false,
  questionId,
}, ref) {
  const followupQid = (index: number) =>
    questionId ? `${questionId}_followup_${index + 1}` : `followup_${index + 1}`;
  // Mirrors the OpenEndedQuestion pattern: holds the active follow-up
  // VoiceRecorder so we can flush an in-flight transcript before it
  // unmounts on voice → text. Without this, a participant who is
  // mid-recording on a follow-up and switches to Type loses everything
  // they just spoke.
  const followupRecorderRef = useRef<VoiceRecorderHandle | null>(null);
  const switchMode = (idx: number, mode: "text" | "voice") => {
    setInputMode((prev) => {
      if (prev === "voice" && mode === "text" && followupRecorderRef.current) {
        const pending = followupRecorderRef.current.flushCurrentTranscript();
        // Always adopt the recorder's transcript when it differs from
        // the current answer — the recorder is the source of truth for
        // what voice has captured, including a re-recording on top of a
        // previously confirmed value. Refusing to overwrite when
        // ``answers[idx]`` was non-empty caused: re-record → switch to
        // text shows the OLD answer → switch back to voice resets to the
        // OLD answer via ``initialTranscript`` and silently discards
        // the new recording.
        if (pending && pending.trim()) {
          setAnswers((prevAnswers) => {
            const existing = prevAnswers[idx] ?? "";
            if (existing === pending) return prevAnswers;
            return { ...prevAnswers, [idx]: pending.slice(0, MAX_ANSWER_CHARS) };
          });
        }
      }
      if (prev !== mode) {
        try {
          trackInputModeSwitched(followupQid(idx), prev, mode, "followup");
        } catch {
          // ignore
        }
      }
      return mode;
    });
  };
  const initialMap: Record<number, string> = {};
  if (initialAnswers?.followup_1_answer) initialMap[0] = initialAnswers.followup_1_answer;
  if (initialAnswers?.followup_2_answer) initialMap[1] = initialAnswers.followup_2_answer;

  // followups list can grow if vagueness check adds a 2nd follow-up
  const [followups, setFollowups] = useState<string[]>(initialFollowups);
  const [answers, setAnswers] = useState<Record<number, string>>(initialMap);
  // Indices that have been explicitly submitted by the user (via Next/Done or
  // Skip), or that were already answered when the panel mounted. This is how
  // we tell a *fresh* voice transcription that has just populated answers[i]
  // (button should read "Next"/"Done") from a *re-edit* of an already-
  // submitted follow-up (button should read "Save" and skip the vagueness
  // check). Without this distinction, voice answers on follow-up 1 would land
  // on the Save path and never trigger the follow-up 2 check.
  const [committedIndices, setCommittedIndices] = useState<Set<number>>(
    () => new Set(Object.keys(initialMap).map(Number)),
  );
  // Per-follow-up input mode the participant actually used. Recorded when
  // each follow-up is committed so the backend can stamp
  // ``followup_N_input_mode`` and downstream exports / sync can compute
  // ``voice / text / mixed / blank`` per question.
  const [committedModes, setCommittedModes] = useState<Record<number, "text" | "voice">>({});

  // Which index is active. Start at first unanswered, or null if all answered.
  const firstUnanswered = initialFollowups.findIndex((_, i) => !initialMap[i]);
  const [activeIndex, setActiveIndex] = useState<number | null>(
    editMode ? null : (firstUnanswered >= 0 ? firstUnanswered : null)
  );
  const [inputMode, setInputMode] = useState<"text" | "voice">("voice");

  // Focus management: when a new follow-up becomes active, move focus to its
  // input area so screen-reader and keyboard users land on it without having
  // to tab through the whole page.
  const activeQuestionRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    if (activeIndex === null || editMode) return;
    // Defer until after render so the element exists in the DOM.
    const id = window.setTimeout(() => {
      const root = activeQuestionRef.current;
      if (!root) return;
      const focusable = root.querySelector<HTMLElement>(
        'textarea, button[type="button"]:not([aria-pressed="false"])'
      );
      // Prefer the textarea when present; otherwise the first action button
      // inside the voice recorder (Start/Stop/Use this response).
      (focusable ?? root.querySelector<HTMLElement>("textarea, button"))?.focus();
    }, 50);
    return () => window.clearTimeout(id);
  }, [activeIndex, editMode]);

  // Expose current answers to parent so it can flush unsaved typed text on Next click.
  // B8: preserve empty strings so that a cleared follow-up answer propagates
  // to the parent (and to sessionStorage) instead of being lost.
  useImperativeHandle(ref, () => ({
    getCurrentAnswers: () => ({
      followup_1_answer: 0 in answers ? answers[0] : undefined,
      followup_2_answer: 1 in answers ? answers[1] : undefined,
      followup_1_input_mode: committedModes[0],
      followup_2_input_mode: committedModes[1],
    }),
  }));

  const buildAnswerPayload = (
    updatedAnswers: Record<number, string>,
    modesOverride?: Record<number, "text" | "voice">,
  ) => {
    const modes = modesOverride ?? committedModes;
    return {
      followup_1_answer: 0 in updatedAnswers ? updatedAnswers[0] : undefined,
      followup_2_answer: 1 in updatedAnswers ? updatedAnswers[1] : undefined,
      followup_1_input_mode: modes[0],
      followup_2_input_mode: modes[1],
    };
  };

  const saveAndAdvance = async (savedAnswers: Record<number, string>, idx: number) => {
    // Capture the mode the participant just used for this follow-up so
    // downstream consumers can compute ``voice / text / mixed / blank``
    // per question. Only recorded when the slot has actual content —
    // skips (empty answers) shouldn't claim a mode.
    const nextModes = { ...committedModes };
    if (savedAnswers[idx]?.trim()) {
      nextModes[idx] = inputMode;
      setCommittedModes(nextModes);
    }
    // Save immediately to the backend via parent callback
    onAnswerSaved(buildAnswerPayload(savedAnswers, nextModes));
    // Mark this slot as committed so a subsequent re-open via Edit falls
    // into the Save path instead of re-running the vagueness check.
    setCommittedIndices((prev) => {
      if (prev.has(idx)) return prev;
      const next = new Set(prev);
      next.add(idx);
      return next;
    });

    const isLast = idx >= followups.length - 1;

    // If this is follow-up 0 (first), check vagueness of its answer to decide
    // whether to generate a follow-up 2. Only do this if there's no follow-up 2
    // yet and we have a vagueness checker. Skip in edit mode — the thread is complete.
    if (!editMode && idx === 0 && followups.length < 2 && savedAnswers[0] && onCheckFollowupVagueness) {
      const newFollowup = await onCheckFollowupVagueness(
        followups[0],
        savedAnswers[0],
        0,
      );
      if (newFollowup) {
        // Append the new follow-up question and open it
        const updated = [...followups, newFollowup];
        setFollowups(updated);
        setActiveIndex(1);
        setInputMode("voice");
        // Notify parent so it persists the updated followups list
        onFollowupsUpdated?.(updated);
        return;
      }
    }

    if (isLast) {
      setActiveIndex(null);
    } else {
      setActiveIndex(idx + 1);
      setInputMode("voice");
    }
  };

  const handleAnswer = async (idx: number) => {
    const updatedAnswers = { ...answers };
    // Ensure the current answer is in the map (it might have been typed)
    const saved = { ...updatedAnswers };
    await saveAndAdvance(saved, idx);
  };

  const handleSkip = async (idx: number) => {
    // Remove the answer for this index (skipped)
    const updated = { ...answers };
    delete updated[idx];
    setAnswers(updated);
    await saveAndAdvance(updated, idx);
  };

  const handleTranscriptComplete = (transcript: string) => {
    if (activeIndex === null) return;
    // Keep the Type/Voice toggle on Voice after confirm — the VoiceRecorder
    // stays mounted in its confirmed state so the participant can still
    // tweak the transcript there, and the panel-level Next button below
    // picks up the newly populated answers[activeIndex].
    setAnswers((prev) => ({ ...prev, [activeIndex]: transcript }));
  };

  const handleEdit = (i: number) => {
    setActiveIndex(i);
    setInputMode("text");
  };

  // When editing an already-answered follow-up, save on confirm
  const handleEditSave = async (idx: number) => {
    const nextModes = answers[idx]?.trim()
      ? { ...committedModes, [idx]: inputMode }
      : committedModes;
    if (nextModes !== committedModes) setCommittedModes(nextModes);
    onAnswerSaved(buildAnswerPayload(answers, nextModes));
    setActiveIndex(null);
  };

  // ── Edit mode: inline-editable thread view with Type/Voice toggle ──
  // Track input mode per followup index so each can independently use voice or text
  const [editModes, setEditModes] = useState<Record<number, "text" | "voice">>({});

  if (editMode) {
    const handleEditModeChange = (idx: number, value: string) => {
      const updated = { ...answers, [idx]: value.slice(0, MAX_ANSWER_CHARS) };
      setAnswers(updated);
      // Edit-mode typing implies text input for that follow-up
      const nextModes = updated[idx]?.trim()
        ? { ...committedModes, [idx]: "text" as const }
        : committedModes;
      if (nextModes !== committedModes) setCommittedModes(nextModes);
      // Auto-save to parent on every change so "Back to Review" picks up edits
      onAnswerSaved(buildAnswerPayload(updated, nextModes));
    };

    const handleEditModeTranscript = (idx: number, transcript: string) => {
      const updated = { ...answers, [idx]: transcript };
      setAnswers(updated);
      const nextModes = transcript?.trim()
        ? { ...committedModes, [idx]: "voice" as const }
        : committedModes;
      if (nextModes !== committedModes) setCommittedModes(nextModes);
      onAnswerSaved(buildAnswerPayload(updated, nextModes));
      // Switch to text mode so user can see and edit the transcript
      setEditModes((prev) => ({ ...prev, [idx]: "text" }));
    };

    const getEditInputMode = (idx: number) => editModes[idx] || "text";

    return (
      <div className="relative border-l-2 border-brand-yellow/50 pl-5 ml-4 mt-2 space-y-5">
        <div className="absolute -left-[7px] top-0 w-3 h-3 rounded-full bg-brand-yellow" />

        <p className="text-sm font-medium text-brand-dark-yellow flex items-center gap-2">
          <MessageCircle className="h-4 w-4" />
          Follow-up questions
        </p>

        {followups.map((fq, i) => {
          const mode = getEditInputMode(i);
          return (
            <div key={i} className="space-y-3">
              <p
                id={`followup-question-${followupQid(i)}`}
                className="text-sm font-medium text-brand-blue/70"
              >
                {fq}
              </p>

              <div
                role="group"
                aria-label="Follow-up response input mode"
                className="inline-flex rounded-lg border bg-muted p-1 gap-1"
              >
                <Button
                  type="button"
                  variant={mode === "text" ? "default" : "ghost"}
                  size="sm"
                  onClick={() => setEditModes((prev) => ({ ...prev, [i]: "text" }))}
                  aria-pressed={mode === "text"}
                  aria-label="Type your follow-up response"
                  className="gap-1.5 !rounded-md text-xs"
                >
                  <Type className="h-3.5 w-3.5" aria-hidden="true" />
                  Type
                </Button>
                <Button
                  type="button"
                  variant={mode === "voice" ? "default" : "ghost"}
                  size="sm"
                  onClick={() => setEditModes((prev) => ({ ...prev, [i]: "voice" }))}
                  aria-pressed={mode === "voice"}
                  aria-label="Speak your follow-up response"
                  className="gap-1.5 !rounded-md text-xs"
                >
                  <Mic className="h-3.5 w-3.5" aria-hidden="true" />
                  Voice
                </Button>
              </div>

              {mode === "text" ? (
                <div className="space-y-2">
                  <Textarea
                    value={answers[i] || ""}
                    onChange={(e) => handleEditModeChange(i, e.target.value)}
                    placeholder="Type your response (optional)..."
                    className="min-h-[80px] resize-y text-sm"
                    maxLength={MAX_ANSWER_CHARS}
                    aria-labelledby={`followup-question-${followupQid(i)}`}
                  />
                  <PiiWarning text={answers[i] || ""} />
                  <p className={`text-xs text-right ${(answers[i]?.length || 0) >= MAX_ANSWER_CHARS - 20 ? "text-brand-red" : "text-brand-blue/60"}`}>
                    {answers[i]?.length || 0}/{MAX_ANSWER_CHARS}
                  </p>
                </div>
              ) : (
                <div className="space-y-2">
                  <VoiceRecorder
                    onTranscriptComplete={(transcript) => handleEditModeTranscript(i, transcript)}
                    initialTranscript={answers[i] || ""}
                    questionId={followupQid(i)}
                  />
                  <PiiWarning text={answers[i] || ""} />
                </div>
              )}
            </div>
          );
        })}
      </div>
    );
  }

  // ── Normal mode: sequential answering flow ──
  return (
    <div className="relative border-l-2 border-brand-yellow/50 pl-5 ml-4 mt-2 space-y-4">
      <div className="absolute -left-[7px] top-0 w-3 h-3 rounded-full bg-brand-yellow" />

      <p className="text-sm font-medium text-brand-dark-yellow flex items-center gap-2">
        <MessageCircle className="h-4 w-4" />
        Follow-up questions
      </p>

      {followups.map((fq, i) => {
        const isActive = activeIndex === i;
        const answered = answers[i];
        // Show: the active question, any already-answered/skipped questions before it,
        // and all questions when activeIndex is null (all done).
        const isVisible = isActive || i < (activeIndex ?? followups.length);
        if (!isVisible) return null;

        if (!isActive) {
          return (
            <div key={i} className="space-y-1">
              <p className="text-sm text-brand-blue/60 font-medium">{fq}</p>
              <div className="flex items-start justify-between gap-2">
                {answered ? (
                  <p className="text-sm text-brand-blue/70 bg-white border border-brand-blue/10 rounded-lg px-3 py-2 flex-1">
                    {answered}
                  </p>
                ) : (
                  <p className="text-xs italic text-brand-blue/60 pl-1 flex-1 self-center">Skipped</p>
                )}
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => handleEdit(i)}
                  className="shrink-0 gap-1 text-brand-blue/60 hover:text-brand-blue/80 text-xs"
                >
                  <Pencil className="h-3 w-3" />
                  Edit
                </Button>
              </div>
            </div>
          );
        }

        // Active input. Only treat as "editing existing" when this index has
        // actually been submitted before (or was pre-populated on mount) —
        // not just because ``answers[i]`` was populated by an in-flight
        // voice transcription. That distinction is what keeps the button as
        // "Next" on a fresh voice answer, which in turn lets
        // ``saveAndAdvance`` run the follow-up-2 vagueness check.
        const isEditingExisting = committedIndices.has(i);

        return (
          <div
            key={i}
            ref={isActive ? activeQuestionRef : undefined}
            className="space-y-3"
            role="region"
            aria-live="polite"
            aria-labelledby={`followup-question-${followupQid(i)}`}
          >
            <p
              id={`followup-question-${followupQid(i)}`}
              className="text-sm font-medium text-foreground"
            >
              {fq}
            </p>

            <div
              role="group"
              aria-label="Follow-up response input mode"
              className="inline-flex rounded-lg border bg-muted p-1 gap-1"
            >
              <Button
                type="button"
                variant={inputMode === "text" ? "default" : "ghost"}
                size="sm"
                onClick={() => switchMode(i, "text")}
                aria-pressed={inputMode === "text"}
                aria-label="Type your follow-up response"
                className="gap-1.5 !rounded-md text-xs"
              >
                <Type className="h-3.5 w-3.5" aria-hidden="true" />
                Type
              </Button>
              <Button
                type="button"
                variant={inputMode === "voice" ? "default" : "ghost"}
                size="sm"
                onClick={() => switchMode(i, "voice")}
                aria-pressed={inputMode === "voice"}
                aria-label="Speak your follow-up response"
                className="gap-1.5 !rounded-md text-xs"
              >
                <Mic className="h-3.5 w-3.5" aria-hidden="true" />
                Voice
              </Button>
            </div>

            {inputMode === "text" ? (
              <div className="space-y-2">
                <Textarea
                  value={answers[i] || ""}
                  onChange={(e) =>
                    setAnswers((prev) => ({ ...prev, [i]: e.target.value.slice(0, MAX_ANSWER_CHARS) }))
                  }
                  placeholder="Type your response (optional)..."
                  className="min-h-[80px] resize-y"
                  maxLength={MAX_ANSWER_CHARS}
                  aria-labelledby={`followup-question-${followupQid(i)}`}
                />
                <PiiWarning text={answers[i] || ""} />
                <p className={`text-xs text-right ${(answers[i]?.length || 0) >= MAX_ANSWER_CHARS - 20 ? "text-brand-red" : "text-brand-blue/60"}`}>
                  {answers[i]?.length || 0}/{MAX_ANSWER_CHARS}
                </p>
              </div>
            ) : (
              <div className="space-y-2">
                <VoiceRecorder
                  ref={followupRecorderRef}
                  onTranscriptComplete={handleTranscriptComplete}
                  initialTranscript={answers[i] || ""}
                  questionId={followupQid(i)}
                />
                <PiiWarning text={answers[i] || ""} />
              </div>
            )}

            <div className="flex gap-2 justify-end">
              {!isEditingExisting && (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => handleSkip(i)}
                  disabled={checkingVagueness}
                  className="gap-1 text-muted-foreground"
                >
                  <SkipForward className="h-3 w-3" />
                  Skip
                </Button>
              )}
              <Button
                type="button"
                size="sm"
                onClick={() => isEditingExisting ? handleEditSave(i) : handleAnswer(i)}
                disabled={!answers[i]?.trim() || checkingVagueness}
                className="bg-brand-blue hover:bg-brand-blue/90 gap-1.5"
              >
                {checkingVagueness && i === 0 && <Loader2 className="h-3 w-3 motion-safe:animate-spin" />}
                {isEditingExisting ? "Save" : "Next"}
              </Button>
            </div>
          </div>
        );
      })}
    </div>
  );
});
