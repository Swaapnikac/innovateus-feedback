"use client";

import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

interface ChoiceQuestionProps {
  type: "rating" | "mcq";
  options: (string | number)[];
  value: string;
  onChange: (value: string) => void;
}

export function ChoiceQuestion({ type, options, value, onChange }: ChoiceQuestionProps) {
  if (type === "rating") {
    return (
      <Select value={value} onValueChange={onChange}>
        <SelectTrigger className="w-full max-w-xs">
          <SelectValue placeholder="Select a rating..." />
        </SelectTrigger>
        <SelectContent>
          {options.map((opt) => (
            <SelectItem key={String(opt)} value={String(opt)}>
              {opt}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    );
  }

  return (
    <RadioGroup value={value} onValueChange={onChange} className="space-y-3">
      {options.map((opt) => (
        <div key={String(opt)} className="flex items-start space-x-3">
          <RadioGroupItem value={String(opt)} id={String(opt)} className="mt-0.5" />
          <Label htmlFor={String(opt)} className="text-sm font-normal leading-relaxed cursor-pointer">
            {opt}
          </Label>
        </div>
      ))}
    </RadioGroup>
  );
}
