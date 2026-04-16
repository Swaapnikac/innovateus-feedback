"use client";

import { useState, useImperativeHandle, forwardRef } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { MessageCircle, SkipForward, Mic, Type, Pencil, Loader2 } from "lucide-react";
import { VoiceRecorder } from "./VoiceRecorder";
import { trackInputModeSwitched } from "@/lib/analytics";

interface FollowUpPanelProps {
  followups: string[];
  // Called immediately when each individual follow-up answer is saved/skipped.
  // The parent should persist to the backend and update its state.
  onAnswerSaved: (answers: { followup_1_answer?: string; followup_2_answer?: string }) => void;
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
  getCurrentAnswers: () => { followup_1_answer?: string; followup_2_answer?: string };
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
  const switchMode = (idx: number, mode: "text" | "voice") => {
    setInputMode((prev) => {
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

  // Which index is active. Start at first unanswered, or null if all answered.
  const firstUnanswered = initialFollowups.findIndex((_, i) => !initialMap[i]);
  const [activeIndex, setActiveIndex] = useState<number | null>(
    editMode ? null : (firstUnanswered >= 0 ? firstUnanswered : null)
  );
  const [inputMode, setInputMode] = useState<"text" | "voice">("voice");

  // Expose current answers to parent so it can flush unsaved typed text on Next click
  useImperativeHandle(ref, () => ({
    getCurrentAnswers: () => ({
      followup_1_answer: answers[0] || undefined,
      followup_2_answer: answers[1] || undefined,
    }),
  }));

  const buildAnswerPayload = (updatedAnswers: Record<number, string>) => ({
    followup_1_answer: updatedAnswers[0] || undefined,
    followup_2_answer: updatedAnswers[1] || undefined,
  });

  const saveAndAdvance = async (savedAnswers: Record<number, string>, idx: number) => {
    // Save immediately to the backend via parent callback
    onAnswerSaved(buildAnswerPayload(savedAnswers));

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
    setAnswers((prev) => ({ ...prev, [activeIndex]: transcript }));
    setInputMode("text");
  };

  const handleEdit = (i: number) => {
    setActiveIndex(i);
    setInputMode("text");
  };

  // When editing an already-answered follow-up, save on confirm
  const handleEditSave = async (idx: number) => {
    onAnswerSaved(buildAnswerPayload(answers));
    setActiveIndex(null);
  };

  // ── Edit mode: inline-editable thread view with Type/Voice toggle ──
  // Track input mode per followup index so each can independently use voice or text
  const [editModes, setEditModes] = useState<Record<number, "text" | "voice">>({});

  if (editMode) {
    const handleEditModeChange = (idx: number, value: string) => {
      const updated = { ...answers, [idx]: value.slice(0, 5000) };
      setAnswers(updated);
      // Auto-save to parent on every change so "Back to Review" picks up edits
      onAnswerSaved(buildAnswerPayload(updated));
    };

    const handleEditModeTranscript = (idx: number, transcript: string) => {
      const updated = { ...answers, [idx]: transcript };
      setAnswers(updated);
      onAnswerSaved(buildAnswerPayload(updated));
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
              <p className="text-sm font-medium text-brand-blue/70">{fq}</p>

              <div className="inline-flex rounded-lg border bg-muted p-1 gap-1">
                <Button
                  type="button"
                  variant={mode === "text" ? "default" : "ghost"}
                  size="sm"
                  onClick={() => setEditModes((prev) => ({ ...prev, [i]: "text" }))}
                  className="gap-1.5 !rounded-md text-xs"
                >
                  <Type className="h-3.5 w-3.5" />
                  Type
                </Button>
                <Button
                  type="button"
                  variant={mode === "voice" ? "default" : "ghost"}
                  size="sm"
                  onClick={() => setEditModes((prev) => ({ ...prev, [i]: "voice" }))}
                  className="gap-1.5 !rounded-md text-xs"
                >
                  <Mic className="h-3.5 w-3.5" />
                  Voice
                </Button>
              </div>

              {mode === "text" ? (
                <div className="space-y-1">
                  <Textarea
                    value={answers[i] || ""}
                    onChange={(e) => handleEditModeChange(i, e.target.value)}
                    placeholder="Type your response (optional)..."
                    className="min-h-[80px] resize-y text-sm"
                    maxLength={5000}
                  />
                  <p className={`text-xs text-right ${(answers[i]?.length || 0) >= 4900 ? "text-brand-red" : "text-brand-blue/40"}`}>
                    {answers[i]?.length || 0}/5000
                  </p>
                </div>
              ) : (
              <VoiceRecorder
                onTranscriptComplete={(transcript) => handleEditModeTranscript(i, transcript)}
                initialTranscript={answers[i] || ""}
                questionId={followupQid(i)}
              />
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
                  <p className="text-xs italic text-brand-blue/30 pl-1 flex-1 self-center">Skipped</p>
                )}
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => handleEdit(i)}
                  className="shrink-0 gap-1 text-brand-blue/40 hover:text-brand-blue/70 text-xs"
                >
                  <Pencil className="h-3 w-3" />
                  Edit
                </Button>
              </div>
            </div>
          );
        }

        // Active input
        const isEditingExisting = answered !== undefined || initialMap[i] !== undefined;
        const isLastFollowup = i >= followups.length - 1;

        return (
          <div key={i} className="space-y-3">
            <p className="text-sm font-medium text-foreground">{fq}</p>

            <div className="inline-flex rounded-lg border bg-muted p-1 gap-1">
              <Button
                type="button"
                variant={inputMode === "text" ? "default" : "ghost"}
                size="sm"
                onClick={() => switchMode(i, "text")}
                className="gap-1.5 !rounded-md text-xs"
              >
                <Type className="h-3.5 w-3.5" />
                Type
              </Button>
              <Button
                type="button"
                variant={inputMode === "voice" ? "default" : "ghost"}
                size="sm"
                onClick={() => switchMode(i, "voice")}
                className="gap-1.5 !rounded-md text-xs"
              >
                <Mic className="h-3.5 w-3.5" />
                Voice
              </Button>
            </div>

            {inputMode === "text" ? (
              <div className="space-y-1">
                <Textarea
                  value={answers[i] || ""}
                  onChange={(e) =>
                    setAnswers((prev) => ({ ...prev, [i]: e.target.value.slice(0, 5000) }))
                  }
                  placeholder="Type your response (optional)..."
                  className="min-h-[80px] resize-y"
                  maxLength={5000}
                />
                <p className={`text-xs text-right ${(answers[i]?.length || 0) >= 4900 ? "text-brand-red" : "text-brand-blue/40"}`}>
                  {answers[i]?.length || 0}/5000
                </p>
              </div>
            ) : (
              <VoiceRecorder
                onTranscriptComplete={handleTranscriptComplete}
                initialTranscript={answers[i] || ""}
                questionId={followupQid(i)}
              />
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
                {checkingVagueness && i === 0 && <Loader2 className="h-3 w-3 animate-spin" />}
                {isEditingExisting ? "Save" : isLastFollowup ? "Done" : "Next"}
              </Button>
            </div>
          </div>
        );
      })}
    </div>
  );
});
