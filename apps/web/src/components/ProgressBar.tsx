"use client";

import { Progress } from "@/components/ui/progress";

interface ProgressBarProps {
  current: number;
  total: number;
}

export function ProgressBar({ current, total }: ProgressBarProps) {
  const percent = Math.round((current / total) * 100);

  return (
    <div className="w-full space-y-2">
      <div className="flex justify-between items-center">
        <span className="text-xs font-semibold text-brand-blue/40 uppercase tracking-widest">
          Question {current} of {total}
        </span>
        <span className="text-xs font-semibold text-brand-blue bg-brand-light-blue px-2.5 py-0.5 rounded-full">
          {percent}%
        </span>
      </div>
      <Progress value={percent} className="h-1.5 bg-brand-blue/10 [&>div]:bg-brand-blue [&>div]:rounded-full rounded-full" />
    </div>
  );
}
