"use client";

import { useRef, useState } from "react";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Mic, Type } from "lucide-react";
import { VoiceRecorder, type VoiceRecorderHandle } from "./VoiceRecorder";
import { PiiWarning } from "./PiiWarning";
import { MAX_ANSWER_CHARS } from "@/lib/limits";

interface OpenEndedQuestionProps {
  value: string;
  onChange: (value: string) => void;
  voiceEligible: boolean;
  initialInputMode?: "text" | "voice";
  onInputModeChange?: (mode: "text" | "voice") => void;
  onTranscriptReady?: (transcript: string) => void;
  onRecordingStarted?: () => void;
  questionId?: string;
  /** id of the visible question heading, wired up via aria-labelledby */
  labelledById?: string;
  /** id of an external error / hint element to wire via aria-describedby */
  describedById?: string;
  /** when true, marks the textarea as having an associated error */
  invalid?: boolean;
}

export function OpenEndedQuestion({
  value,
  onChange,
  voiceEligible,
  initialInputMode,
  onInputModeChange,
  onTranscriptReady,
  onRecordingStarted,
  questionId,
  labelledById,
  describedById,
  invalid,
}: OpenEndedQuestionProps) {
  const [inputMode, setInputMode] = useState<"text" | "voice">(
    initialInputMode ?? (voiceEligible ? "voice" : "text")
  );

  const voiceRef = useRef<VoiceRecorderHandle>(null);

  const handleModeSwitch = (mode: "text" | "voice") => {
    // B7: when switching voice → text, pull whatever transcript the recorder
    // is holding (confirmed, enhanced, raw, or mid-recording live) before it
    // unmounts, so in-flight voice work is preserved in the text area.
    //
    // We always adopt the recorder's current transcript when it differs
    // from ``value`` — the recorder is the source of truth for what voice
    // has produced, including a re-recording on top of a previously
    // confirmed answer. Without this, switching back to text after a
    // re-record would show the OLD value, and re-entering voice would
    // then reset to the OLD value via ``initialTranscript`` and silently
    // discard the user's new recording.
    if (inputMode === "voice" && mode === "text" && voiceRef.current) {
      const pending = voiceRef.current.flushCurrentTranscript();
      if (pending && pending.trim() && pending !== value) {
        onChange(pending.slice(0, MAX_ANSWER_CHARS));
      }
    }
    setInputMode(mode);
    onInputModeChange?.(mode);
  };

  const handleTranscriptComplete = (transcript: string) => {
    onChange(transcript);
    onTranscriptReady?.(transcript);
  };

  return (
    <div className="space-y-4">
      {voiceEligible && (
        <div
          role="group"
          aria-label="Response input mode"
          className="inline-flex rounded-lg border bg-muted p-1 gap-1"
        >
          <Button
            type="button"
            variant={inputMode === "text" ? "default" : "ghost"}
            size="sm"
            onClick={() => handleModeSwitch("text")}
            aria-pressed={inputMode === "text"}
            aria-label="Type your response"
            className="gap-2 !rounded-md"
          >
            <Type className="h-4 w-4" aria-hidden="true" />
            Type
          </Button>
          <Button
            type="button"
            variant={inputMode === "voice" ? "default" : "ghost"}
            size="sm"
            onClick={() => handleModeSwitch("voice")}
            aria-pressed={inputMode === "voice"}
            aria-label="Speak your response"
            className="gap-2 !rounded-md"
          >
            <Mic className="h-4 w-4" aria-hidden="true" />
            Voice
          </Button>
        </div>
      )}

      {inputMode === "text" ? (
        <div className="space-y-2">
          <Textarea
            value={value}
            onChange={(e) => onChange(e.target.value.slice(0, MAX_ANSWER_CHARS))}
            placeholder="Type your response here..."
            className="min-h-[120px] resize-y text-base"
            maxLength={MAX_ANSWER_CHARS}
            aria-labelledby={labelledById}
            aria-describedby={describedById}
            aria-invalid={invalid || undefined}
          />
          <PiiWarning text={value} />
          <p className={`text-xs text-right ${value.length >= MAX_ANSWER_CHARS - 20 ? "text-brand-red" : "text-brand-blue/60"}`}>
            {value.length}/{MAX_ANSWER_CHARS}
          </p>
        </div>
      ) : (
        <div className="space-y-2">
          <VoiceRecorder
            ref={voiceRef}
            onTranscriptComplete={handleTranscriptComplete}
            initialTranscript={value}
            onRecordingStarted={onRecordingStarted}
            questionId={questionId}
          />
          <PiiWarning text={value} />
        </div>
      )}
    </div>
  );
}
