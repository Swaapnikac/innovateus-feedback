"use client";

import { useState } from "react";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Mic, Type } from "lucide-react";
import { VoiceRecorder } from "./VoiceRecorder";

interface OpenEndedQuestionProps {
  value: string;
  onChange: (value: string) => void;
  voiceEligible: boolean;
  onInputModeChange?: (mode: "text" | "voice") => void;
  onTranscriptReady?: (transcript: string) => void;
}

export function OpenEndedQuestion({
  value,
  onChange,
  voiceEligible,
  onInputModeChange,
  onTranscriptReady,
}: OpenEndedQuestionProps) {
  const [inputMode, setInputMode] = useState<"text" | "voice">(voiceEligible ? "voice" : "text");

  const handleModeSwitch = (mode: "text" | "voice") => {
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
        <div className="inline-flex rounded-lg border bg-muted p-1 gap-1">
          <Button
            type="button"
            variant={inputMode === "text" ? "default" : "ghost"}
            size="sm"
            onClick={() => handleModeSwitch("text")}
            className="gap-2 rounded-md"
          >
            <Type className="h-4 w-4" />
            Type
          </Button>
          <Button
            type="button"
            variant={inputMode === "voice" ? "default" : "ghost"}
            size="sm"
            onClick={() => handleModeSwitch("voice")}
            className="gap-2 rounded-md"
          >
            <Mic className="h-4 w-4" />
            Voice
          </Button>
        </div>
      )}

      {inputMode === "text" ? (
        <Textarea
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder="Type your response here..."
          className="min-h-[120px] resize-y text-base"
        />
      ) : (
        <VoiceRecorder
          onTranscriptComplete={handleTranscriptComplete}
          initialTranscript={value}
        />
      )}
    </div>
  );
}
