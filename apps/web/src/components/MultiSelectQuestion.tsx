"use client";

import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";

interface MultiSelectQuestionProps {
  options: string[];
  value: string[];
  onChange: (value: string[]) => void;
}

export function MultiSelectQuestion({ options, value, onChange }: MultiSelectQuestionProps) {
  const handleToggle = (option: string) => {
    if (value.includes(option)) {
      onChange(value.filter((v) => v !== option));
    } else {
      onChange([...value, option]);
    }
  };

  return (
    <div className="space-y-3">
      {options.map((opt) => (
        <div key={opt} className="flex items-start space-x-3">
          <Checkbox
            id={opt}
            checked={value.includes(opt)}
            onCheckedChange={() => handleToggle(opt)}
            className="mt-0.5"
          />
          <Label htmlFor={opt} className="text-sm font-normal leading-relaxed cursor-pointer">
            {opt}
          </Label>
        </div>
      ))}
    </div>
  );
}
