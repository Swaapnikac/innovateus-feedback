"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { MessageCircle, SkipForward, Mic, Type, CheckCircle2 } from "lucide-react";
import { VoiceRecorder } from "./VoiceRecorder";

interface FollowUpPanelProps {
  followups: string[];
  onComplete: (answers: { followup_1_answer?: string; followup_2_answer?: string }) => void;
}

export function FollowUpPanel({ followups, onComplete }: FollowUpPanelProps) {
  const [currentIndex, setCurrentIndex] = useState(0);
  const [answers, setAnswers] = useState<Record<number, string>>({});
  const [inputMode, setInputMode] = useState<"text" | "voice">("voice");

  const isLast = currentIndex >= followups.length - 1;

  const finish = () => {
    onComplete({
      followup_1_answer: answers[0] || undefined,
      followup_2_answer: answers[1] || undefined,
    });
  };

  const handleAnswer = () => {
    if (isLast) {
      finish();
    } else {
      setCurrentIndex(currentIndex + 1);
      setInputMode("voice");
    }
  };

  const handleSkip = () => {
    if (isLast) {
      finish();
    } else {
      setCurrentIndex(currentIndex + 1);
      setInputMode("voice");
    }
  };

  const handleTranscriptComplete = (transcript: string) => {
    setAnswers({ ...answers, [currentIndex]: transcript });
    setInputMode("text");
  };

  return (
    <div className="relative border-l-2 border-brand-yellow/50 pl-5 ml-4 mt-2 space-y-4">
      <div className="absolute -left-[7px] top-0 w-3 h-3 rounded-full bg-brand-yellow" />

      <p className="text-sm font-medium text-brand-dark-yellow flex items-center gap-2">
        <MessageCircle className="h-4 w-4" />
        We&apos;d love a bit more detail
      </p>

      {followups.slice(0, currentIndex).map((fq, i) => (
        <div key={i} className="space-y-1">
          <p className="text-sm text-brand-blue/50">{fq}</p>
          {answers[i] ? (
            <div className="flex items-start gap-2 rounded-lg bg-white border border-brand-blue/10 px-3 py-2">
              <CheckCircle2 className="h-4 w-4 text-brand-teal shrink-0 mt-0.5" />
              <p className="text-sm text-brand-blue/80">{answers[i]}</p>
            </div>
          ) : (
            <p className="text-xs italic text-brand-blue/30 pl-1">Skipped</p>
          )}
        </div>
      ))}

      {currentIndex < followups.length && (
        <div className="space-y-3">
          <p className="text-sm font-medium text-foreground">
            {followups[currentIndex]}
          </p>

          <div className="inline-flex rounded-lg border bg-muted p-1 gap-1">
            <Button
              type="button"
              variant={inputMode === "text" ? "default" : "ghost"}
              size="sm"
              onClick={() => setInputMode("text")}
              className="gap-1.5 rounded-md h-8 text-xs"
            >
              <Type className="h-3.5 w-3.5" />
              Type
            </Button>
            <Button
              type="button"
              variant={inputMode === "voice" ? "default" : "ghost"}
              size="sm"
              onClick={() => setInputMode("voice")}
              className="gap-1.5 rounded-md h-8 text-xs"
            >
              <Mic className="h-3.5 w-3.5" />
              Voice
            </Button>
          </div>

          {inputMode === "text" ? (
            <Textarea
              value={answers[currentIndex] || ""}
              onChange={(e) =>
                setAnswers({ ...answers, [currentIndex]: e.target.value })
              }
              placeholder="Type your response (optional)..."
              className="min-h-[80px] resize-y"
            />
          ) : (
            <VoiceRecorder
              onTranscriptComplete={handleTranscriptComplete}
              initialTranscript={answers[currentIndex] || ""}
            />
          )}

          <div className="flex gap-2 justify-end">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={handleSkip}
              className="gap-1 text-muted-foreground"
            >
              <SkipForward className="h-3 w-3" />
              Skip
            </Button>
            <Button
              type="button"
              size="sm"
              onClick={handleAnswer}
              disabled={!answers[currentIndex]?.trim()}
              className="bg-brand-blue hover:bg-brand-blue/90"
            >
              {isLast ? "Continue" : "Next"}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
