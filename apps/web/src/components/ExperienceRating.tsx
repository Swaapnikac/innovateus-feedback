"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Loader2, SkipForward, Send } from "lucide-react";

interface ExperienceRatingProps {
  onSubmit: (rating: number, feedback?: string) => void;
  onSkip: () => void;
  isSubmitting: boolean;
}

const EMOJI_OPTIONS = [
  { value: 1, emoji: "😣", label: "Difficult" },
  { value: 2, emoji: "😐", label: "Okay" },
  { value: 3, emoji: "🙂", label: "Good" },
  { value: 4, emoji: "😊", label: "Great" },
  { value: 5, emoji: "🤩", label: "Loved it!" },
];

export function ExperienceRating({ onSubmit, onSkip, isSubmitting }: ExperienceRatingProps) {
  const [rating, setRating] = useState<number | null>(null);
  const [feedback, setFeedback] = useState("");

  return (
    <div className="fixed inset-0 z-50 bg-brand-light-blue/95 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-xl max-w-md w-full p-8 space-y-6">
        <div className="text-center space-y-2">
          <h2 className="text-xl font-serif text-brand-blue">How was your feedback experience?</h2>
          <p className="text-sm text-brand-blue/50">This helps us improve the feedback tool.</p>
        </div>

        <div className="flex justify-center gap-3">
          {EMOJI_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              type="button"
              onClick={() => setRating(opt.value)}
              className={`flex flex-col items-center gap-1.5 p-3 rounded-xl transition-all cursor-pointer ${
                rating === opt.value
                  ? "bg-brand-blue/10 ring-2 ring-brand-blue scale-110"
                  : "hover:bg-brand-light-blue"
              }`}
            >
              <span className="text-2xl">{opt.emoji}</span>
              <span className="text-[10px] font-semibold text-brand-blue/50 uppercase tracking-wider">
                {opt.label}
              </span>
            </button>
          ))}
        </div>

        <div className="space-y-1.5">
          <p className="text-xs text-brand-blue/40">Any quick thoughts? (optional)</p>
          <Textarea
            value={feedback}
            onChange={(e) => setFeedback(e.target.value.slice(0, 500))}
            placeholder="What worked well? What could be better?"
            className="min-h-[60px] resize-none text-sm"
            maxLength={500}
          />
          <p className={`text-xs text-right ${feedback.length >= 450 ? "text-brand-red" : "text-brand-blue/30"}`}>
            {feedback.length}/500
          </p>
        </div>

        <div className="flex gap-3">
          <Button
            variant="ghost"
            onClick={onSkip}
            disabled={isSubmitting}
            className="flex-1 gap-1.5 text-brand-blue/50"
          >
            <SkipForward className="h-4 w-4" />
            Skip
          </Button>
          <Button
            onClick={() => rating && onSubmit(rating, feedback || undefined)}
            disabled={!rating || isSubmitting}
            className="flex-1 gap-1.5 bg-brand-blue hover:bg-brand-blue/90"
          >
            {isSubmitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
            {isSubmitting ? "Saving..." : "Submit"}
          </Button>
        </div>
      </div>
    </div>
  );
}
