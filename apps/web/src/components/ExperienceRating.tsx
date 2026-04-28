"use client";

import { useEffect, useRef, useState } from "react";
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
  const dialogRef = useRef<HTMLDivElement | null>(null);
  const firstStarRef = useRef<HTMLButtonElement | null>(null);

  // Focus the first emoji button when the dialog opens, and trap Tab inside
  // until the user submits or skips.
  useEffect(() => {
    firstStarRef.current?.focus();

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key !== "Tab" || !dialogRef.current) return;
      const focusables = dialogRef.current.querySelectorAll<HTMLElement>(
        'button:not([disabled]), [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
      );
      if (focusables.length === 0) return;
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      const active = document.activeElement as HTMLElement | null;
      if (e.shiftKey && active === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && active === last) {
        e.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, []);

  return (
    <div
      ref={dialogRef}
      role="dialog"
      aria-modal="true"
      aria-labelledby="rating-dialog-title"
      aria-describedby="rating-dialog-description"
      className="fixed inset-0 z-50 bg-brand-light-blue/95 backdrop-blur-sm flex items-center justify-center p-4"
    >
      <div className="bg-white rounded-2xl shadow-xl max-w-md w-full p-8 space-y-6">
        <div className="text-center space-y-2">
          <h2 id="rating-dialog-title" className="text-xl font-serif text-brand-blue">How was your feedback experience?</h2>
          <p id="rating-dialog-description" className="text-sm text-brand-blue/50">This helps us improve the feedback tool.</p>
        </div>

        <div className="flex justify-center gap-3" role="radiogroup" aria-label="Rate your experience">
          {EMOJI_OPTIONS.map((opt, i) => (
            <button
              key={opt.value}
              ref={i === 0 ? firstStarRef : undefined}
              type="button"
              role="radio"
              aria-checked={rating === opt.value}
              aria-label={opt.label}
              onClick={() => setRating(opt.value)}
              className={`flex flex-col items-center gap-1.5 p-3 rounded-xl transition-all cursor-pointer focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-blue ${
                rating === opt.value
                  ? "bg-brand-blue/10 ring-2 ring-brand-blue scale-110"
                  : "hover:bg-brand-light-blue"
              }`}
            >
              <span className="text-2xl" aria-hidden="true">{opt.emoji}</span>
              <span className="text-[10px] font-semibold text-brand-blue/50 uppercase tracking-wider">
                {opt.label}
              </span>
            </button>
          ))}
        </div>

        <div className="space-y-1.5">
          <p className="text-xs text-brand-blue/60">Any quick thoughts? (optional)</p>
          <Textarea
            value={feedback}
            onChange={(e) => setFeedback(e.target.value.slice(0, 500))}
            placeholder="What worked well? What could be better?"
            className="min-h-[60px] resize-none text-sm"
            maxLength={500}
          />
          <p className={`text-xs text-right ${feedback.length >= 450 ? "text-brand-red" : "text-brand-blue/60"}`}>
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
            {isSubmitting ? <Loader2 className="h-4 w-4 motion-safe:animate-spin" /> : <Send className="h-4 w-4" />}
            {isSubmitting ? "Saving..." : "Submit"}
          </Button>
        </div>
      </div>
    </div>
  );
}
