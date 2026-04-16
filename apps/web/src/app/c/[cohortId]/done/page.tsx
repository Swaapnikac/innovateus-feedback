"use client";

import { useState, useEffect } from "react";
import { useParams } from "next/navigation";
import { InnovateLogo } from "@/components/InnovateLogo";
import { ExtractionCard } from "@/components/ExtractionCard";
import { CheckCircle2 } from "lucide-react";
import type { ExtractionResult } from "@/lib/api";
import { initSession, trackPageView } from "@/lib/analytics";

export default function DonePage() {
  const params = useParams();
  const cohortId = params.cohortId as string;
  const [extraction] = useState<ExtractionResult | null>(() => {
    if (typeof window === "undefined") return null;
    const stored = sessionStorage.getItem("extraction");
    if (!stored) return null;
    try {
      return JSON.parse(stored);
    } catch {
      return null;
    }
  });

  useEffect(() => {
    initSession();
    trackPageView("done", cohortId);
  }, [cohortId]);

  return (
    <div className="min-h-screen bg-brand-light-blue/40">
      <header className="bg-white/60 backdrop-blur-sm border-b border-brand-blue/5 px-6 py-4">
        <div className="max-w-3xl mx-auto">
          <InnovateLogo size="sm" className="text-brand-blue" />
        </div>
      </header>

      <div className="max-w-2xl mx-auto px-4 py-12 space-y-6">
        {/* Thank You */}
        <div className="text-center space-y-4">
          <div className="mx-auto w-16 h-16 rounded-full bg-brand-teal/10 flex items-center justify-center">
            <CheckCircle2 className="h-8 w-8 text-brand-teal" />
          </div>
          <h1 className="text-3xl font-serif text-brand-blue">Thank You!</h1>
          <p className="text-brand-blue/60">
            Your feedback has been submitted successfully. It will help us improve future courses for public service professionals.
          </p>
        </div>

        {/* Extraction Summary */}
        {extraction && <ExtractionCard extraction={extraction} />}
      </div>
    </div>
  );
}
