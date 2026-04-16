"use client";

import { useMemo } from "react";
import { Button } from "@/components/ui/button";
import { ChevronUp, ChevronDown, GripVertical } from "lucide-react";

interface RankingQuestionProps {
  options: (string | number)[];
  value: string; // JSON array of ordered options
  onChange: (value: string) => void;
}

export function RankingQuestion({ options, value, onChange }: RankingQuestionProps) {
  const ordered = useMemo<string[]>(() => {
    if (value) {
      try {
        const parsed = JSON.parse(value);
        if (Array.isArray(parsed)) {
          // Merge with current options to handle option changes gracefully
          const known = new Set(parsed);
          const missing = options.map(String).filter((o) => !known.has(o));
          return [...parsed.filter((o) => options.map(String).includes(o)), ...missing];
        }
      } catch {
        // fall through
      }
    }
    return options.map(String);
  }, [value, options]);

  const move = (i: number, direction: -1 | 1) => {
    const target = i + direction;
    if (target < 0 || target >= ordered.length) return;
    const next = [...ordered];
    [next[i], next[target]] = [next[target], next[i]];
    onChange(JSON.stringify(next));
  };

  return (
    <div className="space-y-2">
      <p className="text-xs text-brand-blue/50">Use the arrows to reorder from most to least important.</p>
      <div className="space-y-1.5">
        {ordered.map((opt, i) => (
          <div
            key={opt}
            className="flex items-center gap-2 bg-white border border-brand-blue/10 rounded-lg px-3 py-2"
          >
            <span className="text-xs font-mono text-brand-blue/30 w-6">{i + 1}.</span>
            <GripVertical className="h-4 w-4 text-brand-blue/20" />
            <span className="flex-1 text-sm text-brand-blue">{opt}</span>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => move(i, -1)}
              disabled={i === 0}
              className="h-7 w-7 p-0"
            >
              <ChevronUp className="h-4 w-4" />
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => move(i, 1)}
              disabled={i === ordered.length - 1}
              className="h-7 w-7 p-0"
            >
              <ChevronDown className="h-4 w-4" />
            </Button>
          </div>
        ))}
      </div>
    </div>
  );
}
