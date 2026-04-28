"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Sparkles } from "lucide-react";

const ROTATING_MESSAGES = [
  "Reading your responses...",
  "Identifying themes and barriers...",
  "Drafting your summary...",
];

const ROTATION_INTERVAL_MS = 3000;

interface SummarySkeletonProps {
  title?: string;
}

export function SummarySkeleton({ title = "What We Heard" }: SummarySkeletonProps) {
  const [messageIndex, setMessageIndex] = useState(0);

  useEffect(() => {
    const id = setInterval(() => {
      setMessageIndex((i) => (i + 1) % ROTATING_MESSAGES.length);
    }, ROTATION_INTERVAL_MS);
    return () => clearInterval(id);
  }, []);

  return (
    <Card className="bg-white border-0 shadow-sm rounded-2xl">
      <CardHeader className="pb-3">
        <CardTitle className="text-base font-serif-text text-brand-blue flex items-center gap-2">
          <Sparkles className="h-4 w-4 text-brand-dark-yellow" />
          {title}
        </CardTitle>
        {/* Live region: announces each rotating phrase to screen readers as it updates */}
        <p
          className="text-xs text-brand-blue/60 mt-1"
          role="status"
          aria-live="polite"
        >
          {ROTATING_MESSAGES[messageIndex]}
        </p>
      </CardHeader>
      <CardContent className="space-y-4" aria-hidden="true">
        {[0, 1, 2].map((row) => (
          <div key={row} className="flex gap-3">
            <div className="w-8 h-8 rounded-lg bg-brand-blue/10 motion-safe:animate-pulse shrink-0" />
            <div className="flex-1 space-y-2 pt-1">
              <div className="h-2.5 w-24 rounded-full bg-brand-blue/10 motion-safe:animate-pulse" />
              <div className="h-3 w-full rounded-full bg-brand-blue/5 motion-safe:animate-pulse" />
              <div className="h-3 w-4/5 rounded-full bg-brand-blue/5 motion-safe:animate-pulse" />
            </div>
          </div>
        ))}
        <div className="pt-3 border-t border-brand-blue/5 space-y-2">
          <div className="h-2.5 w-16 rounded-full bg-brand-blue/10 motion-safe:animate-pulse" />
          <div className="flex flex-wrap gap-1.5">
            {[56, 72, 48, 88, 64].map((width, i) => (
              <div
                key={i}
                className="h-5 rounded-full bg-brand-light-blue motion-safe:animate-pulse"
                style={{ width: `${width}px` }}
              />
            ))}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
