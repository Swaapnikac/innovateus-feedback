"use client";

import { cn } from "@/lib/utils";
import { Check, X } from "lucide-react";

interface YesNoQuestionProps {
  value: string;
  onChange: (value: string) => void;
}

export function YesNoQuestion({ value, onChange }: YesNoQuestionProps) {
  return (
    <div className="flex gap-3">
      <button
        type="button"
        onClick={() => onChange("yes")}
        className={cn(
          "flex-1 flex items-center justify-center gap-2 h-14 rounded-xl border-2 text-base font-medium transition-all",
          value === "yes"
            ? "bg-brand-teal/10 border-brand-teal text-brand-teal"
            : "bg-white border-brand-blue/15 text-brand-blue/70 hover:border-brand-teal/40 hover:bg-brand-teal/5"
        )}
      >
        <Check className="h-5 w-5" />
        Yes
      </button>
      <button
        type="button"
        onClick={() => onChange("no")}
        className={cn(
          "flex-1 flex items-center justify-center gap-2 h-14 rounded-xl border-2 text-base font-medium transition-all",
          value === "no"
            ? "bg-brand-red/5 border-brand-red text-brand-red"
            : "bg-white border-brand-blue/15 text-brand-blue/70 hover:border-brand-red/40 hover:bg-brand-red/5"
        )}
      >
        <X className="h-5 w-5" />
        No
      </button>
    </div>
  );
}
