"use client";

import { useState, useEffect, useRef } from "react";
import { useParams, useRouter } from "next/navigation";
import { InnovateLogo } from "@/components/InnovateLogo";
import { ExtractionCard } from "@/components/ExtractionCard";
import { CheckCircle2 } from "lucide-react";
import type { ExtractionResult } from "@/lib/api";
import { initSession, trackPageView } from "@/lib/analytics";

export default function DonePage() {
  const params = useParams();
  const router = useRouter();
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

  const headingRef = useRef<HTMLHeadingElement | null>(null);

  useEffect(() => {
    initSession();
    trackPageView("done", cohortId);
    // Focus the Thank You heading so screen-reader users hear the page change.
    headingRef.current?.focus();
  }, [cohortId]);

  // Hijack the browser back button while the user is on /done. Without this,
  // pressing Back lands the user on /review (or /survey) in a half-completed,
  // already-submitted state, which is confusing. Instead we send them to the
  // consent page, which clears all session state and shows a fresh form so
  // they can take the survey again if they want.
  useEffect(() => {
    if (typeof window === "undefined") return;
    // Push a sentinel history entry so a single Back press fires popstate
    // here instead of actually navigating to the previous page.
    window.history.pushState(null, "", window.location.href);
    const handlePopstate = () => {
      // Tell the consent page this navigation came from a successful
      // submission so it knows to wipe any leftover in-progress state.
      // Without this flag, the consent page leaves state alone (so that
      // pressing Back during the survey is non-destructive).
      try {
        sessionStorage.setItem(`just_submitted_${cohortId}`, "1");
      } catch {
        // sessionStorage may be disabled (e.g. private mode); silently skip.
      }
      router.replace(`/c/${cohortId}`);
    };
    window.addEventListener("popstate", handlePopstate);
    return () => window.removeEventListener("popstate", handlePopstate);
  }, [cohortId, router]);

  return (
    <div className="min-h-screen bg-brand-light-blue/40">
      <header className="bg-white/60 backdrop-blur-sm border-b border-brand-blue/5 px-6 py-4">
        <div className="max-w-3xl mx-auto">
          <InnovateLogo size="sm" className="text-brand-blue" />
        </div>
      </header>

      <main id="main" tabIndex={-1} className="max-w-2xl mx-auto px-4 py-12 space-y-6 focus:outline-none">
        {/* Thank You */}
        <div className="text-center space-y-4">
          <div className="mx-auto w-16 h-16 rounded-full bg-brand-teal/10 flex items-center justify-center">
            <CheckCircle2 className="h-8 w-8 text-brand-teal" />
          </div>
          <h1
            ref={headingRef}
            tabIndex={-1}
            className="text-3xl font-serif text-brand-blue focus:outline-none"
          >
            Thank You!
          </h1>
          <p className="text-brand-blue/60">
            Your feedback has been submitted successfully. It will help us improve future courses for public service professionals.
          </p>
        </div>

        {/* Extraction Summary */}
        {extraction && <ExtractionCard extraction={extraction} />}
      </main>
    </div>
  );
}
