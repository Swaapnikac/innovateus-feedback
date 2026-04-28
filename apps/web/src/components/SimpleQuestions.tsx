"use client";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Input } from "@/components/ui/input";

// ── Dropdown ──
export function DropdownQuestion({
  options,
  value,
  onChange,
  placeholder = "Select an option...",
  labelledById,
}: {
  options: (string | number)[];
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  labelledById?: string;
}) {
  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger className="w-full max-w-md" aria-labelledby={labelledById}>
        <SelectValue placeholder={placeholder} />
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

// ── Short text ──
export function ShortTextQuestion({
  value,
  onChange,
  placeholder = "Your answer...",
  labelledById,
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  labelledById?: string;
}) {
  return (
    <Input
      value={value}
      onChange={(e) => onChange(e.target.value.slice(0, 200))}
      placeholder={placeholder}
      className="max-w-md text-base"
      maxLength={200}
      aria-labelledby={labelledById}
    />
  );
}

// ── Date ──
export function DateQuestion({
  value,
  onChange,
  labelledById,
}: {
  value: string;
  onChange: (value: string) => void;
  labelledById?: string;
}) {
  return (
    <Input
      type="date"
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="max-w-xs text-base"
      aria-labelledby={labelledById}
    />
  );
}
