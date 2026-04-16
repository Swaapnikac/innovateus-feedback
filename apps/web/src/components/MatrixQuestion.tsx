"use client";

import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { useMemo } from "react";

interface MatrixQuestionProps {
  rows: string[];
  columns: (string | number)[];
  value: string; // JSON: {row_label: column_value}
  onChange: (value: string) => void;
}

export function MatrixQuestion({ rows, columns, value, onChange }: MatrixQuestionProps) {
  const parsed = useMemo<Record<string, string>>(() => {
    if (!value) return {};
    try {
      return JSON.parse(value);
    } catch {
      return {};
    }
  }, [value]);

  const setRow = (row: string, col: string) => {
    const next = { ...parsed, [row]: col };
    onChange(JSON.stringify(next));
  };

  if (rows.length === 0 || columns.length === 0) {
    return (
      <p className="text-xs text-brand-blue/40 italic">
        Matrix question missing rows or columns.
      </p>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-brand-blue/10">
            <th className="text-left py-2 px-2 font-normal text-xs text-brand-blue/40 uppercase tracking-wider"></th>
            {columns.map((col) => (
              <th
                key={String(col)}
                className="text-center py-2 px-2 font-normal text-xs text-brand-blue/60"
              >
                {col}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, ri) => (
            <tr key={row + ri} className="border-b border-brand-blue/5 last:border-0">
              <td className="py-3 px-2 text-brand-blue font-medium">{row}</td>
              <RadioGroup
                value={parsed[row] || ""}
                onValueChange={(v) => setRow(row, v)}
                className="contents"
              >
                {columns.map((col) => (
                  <td key={String(col)} className="text-center py-3 px-2">
                    <RadioGroupItem
                      value={String(col)}
                      id={`${row}-${col}`}
                      className="mx-auto"
                    />
                  </td>
                ))}
              </RadioGroup>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
