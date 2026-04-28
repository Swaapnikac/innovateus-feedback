"use client";

import { cn } from "@/lib/utils";

interface NpsQuestionProps {
  value: string;
  onChange: (value: string) => void;
  labels?: { low?: string; high?: string };
}

export function NpsQuestion({ value, onChange, labels }: NpsQuestionProps) {
  const selected = value === "" ? null : Number(value);
  const lowLabel = labels?.low ?? "Not at all likely";
  const highLabel = labels?.high ?? "Extremely likely";

  return (
    <div className="space-y-3">
      <div className="flex gap-1.5 flex-wrap">
        {Array.from({ length: 11 }, (_, i) => i).map((n) => (
          <button
            key={n}
            type="button"
            onClick={() => onChange(String(n))}
            className={cn(
              "w-10 h-10 rounded-lg border text-sm font-medium transition-all",
              selected === n
                ? "bg-brand-blue border-brand-blue text-white shadow-sm"
                : "bg-white border-brand-blue/15 text-brand-blue/70 hover:border-brand-blue/40 hover:bg-brand-blue/5"
            )}
          >
            {n}
          </button>
        ))}
      </div>
      <div className="flex justify-between text-xs text-brand-blue/60">
        <span>0 — {lowLabel}</span>
        <span>10 — {highLabel}</span>
      </div>
    </div>
  );
}
