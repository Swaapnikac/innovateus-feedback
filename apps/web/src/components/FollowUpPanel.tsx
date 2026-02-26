"use client";

import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { MessageCircle, SkipForward, Mic, Type } from "lucide-react";
import { VoiceRecorder } from "./VoiceRecorder";

interface FollowUpPanelProps {
  followups: string[];
  onComplete: (answers: { followup_1_answer?: string; followup_2_answer?: string }) => void;
  language?: string;
}

export function FollowUpPanel({ followups, onComplete, language = "en" }: FollowUpPanelProps) {
  const [currentIndex, setCurrentIndex] = useState(0);
  const [answers, setAnswers] = useState<Record<number, string>>({});
  const [inputMode, setInputMode] = useState<"text" | "voice">("text");

  const currentQuestion = followups[currentIndex];
  const isLast = currentIndex >= followups.length - 1;

  const handleAnswer = () => {
    if (isLast) {
      onComplete({
        followup_1_answer: answers[0] || undefined,
        followup_2_answer: answers[1] || undefined,
      });
    } else {
      setCurrentIndex(currentIndex + 1);
      setInputMode("text");
    }
  };

  const handleSkip = () => {
    if (isLast) {
      onComplete({
        followup_1_answer: answers[0] || undefined,
        followup_2_answer: answers[1] || undefined,
      });
    } else {
      setCurrentIndex(currentIndex + 1);
      setInputMode("text");
    }
  };

  const handleTranscriptComplete = (transcript: string) => {
    setAnswers({ ...answers, [currentIndex]: transcript });
    setInputMode("text");
  };

  if (!currentQuestion) return null;

  return (
    <Card className="w-full max-w-2xl mx-auto border-brand-yellow/30 bg-brand-yellow/5">
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-sans font-medium text-brand-dark-yellow flex items-center gap-2">
          <MessageCircle className="h-4 w-4" />
          Follow-up Question ({currentIndex + 1} of {followups.length})
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-sm font-medium text-foreground">{currentQuestion}</p>

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
            language={language}
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
      </CardContent>
    </Card>
  );
}
