"use client";

import { useMemo } from "react";
import { AlertCircle } from "lucide-react";
import { detectPii, summarisePii } from "@/lib/pii";

interface PiiWarningProps {
  text: string | null | undefined;
  className?: string;
}

/**
 * Shows a friendly warning when the current answer contains recognisable
 * PII (SSN, phone, address, etc.). The backend will always strip PII on
 * save so this never *blocks* submission — it just nudges the user to
 * edit their response before sending it.
 */
export function PiiWarning({ text, className }: PiiWarningProps) {
  const matches = useMemo(() => detectPii(text ?? ""), [text]);
  if (matches.length === 0) return null;

  const summary = summarisePii(matches);

  return (
    <div
      role="status"
      aria-live="polite"
      className={`flex items-start gap-2 rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900 ${className ?? ""}`}
    >
      <AlertCircle className="mt-0.5 h-4 w-4 flex-shrink-0" aria-hidden="true" />
      <div>
        <p className="font-medium">Possible personal information detected ({summary}).</p>
        <p className="mt-1 text-amber-800">
          Please don&apos;t include names, phone numbers, addresses, or other identifying
          details. We&apos;ll automatically remove them before saving, but editing first keeps
          your feedback focused on your experience.
        </p>
      </div>
    </div>
  );
}
