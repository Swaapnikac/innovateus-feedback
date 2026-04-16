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
}: {
  options: (string | number)[];
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
}) {
  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger className="w-full max-w-md">
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
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
}) {
  return (
    <Input
      value={value}
      onChange={(e) => onChange(e.target.value.slice(0, 200))}
      placeholder={placeholder}
      className="max-w-md text-base"
      maxLength={200}
    />
  );
}

// ── Date ──
export function DateQuestion({
  value,
  onChange,
}: {
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <Input
      type="date"
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="max-w-xs text-base"
    />
  );
}
