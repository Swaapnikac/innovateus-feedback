"use client";

import { useState, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { InnovateLogo } from "@/components/InnovateLogo";
import { CheckCircle2, Sparkles, Target, AlertTriangle, Lightbulb, Users } from "lucide-react";
import type { ExtractionResult } from "@/lib/api";

export default function DonePage() {
  const [extraction, setExtraction] = useState<ExtractionResult | null>(null);

  useEffect(() => {
    const stored = sessionStorage.getItem("extraction");
    if (stored) {
      try { setExtraction(JSON.parse(stored)); } catch {}
    }
  }, []);

  return (
    <div className="min-h-screen bg-brand-light-blue/40">
      <header className="bg-white/60 backdrop-blur-sm border-b border-brand-blue/5 px-6 py-4">
        <div className="max-w-2xl mx-auto">
          <InnovateLogo size="sm" className="text-brand-blue" />
        </div>
      </header>

      <div className="max-w-lg mx-auto px-4 py-12 space-y-6">
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
        {extraction && (
          <Card className="bg-white border-0 shadow-sm rounded-2xl">
            <CardHeader className="pb-3">
              <CardTitle className="text-base font-serif text-brand-blue flex items-center gap-2">
                <Sparkles className="h-4 w-4 text-brand-dark-yellow" />
                What We Heard
              </CardTitle>
              <p className="text-xs text-brand-blue/40">
                A de-identified summary of your feedback
              </p>
            </CardHeader>
            <CardContent className="space-y-4">
              {extraction.planned_task_or_workflow && (
                <div className="flex gap-3">
                  <div className="w-8 h-8 rounded-lg bg-brand-blue/8 flex items-center justify-center shrink-0">
                    <Target className="h-4 w-4 text-brand-blue" />
                  </div>
                  <div>
                    <p className="text-xs font-semibold text-brand-blue/40 uppercase tracking-wider">Planned Task</p>
                    <p className="text-sm text-brand-blue/80 mt-0.5">{extraction.planned_task_or_workflow}</p>
                  </div>
                </div>
              )}

              {extraction.what_was_tried && (
                <div className="flex gap-3">
                  <div className="w-8 h-8 rounded-lg bg-brand-yellow/15 flex items-center justify-center shrink-0">
                    <Lightbulb className="h-4 w-4 text-brand-dark-yellow" />
                  </div>
                  <div>
                    <p className="text-xs font-semibold text-brand-blue/40 uppercase tracking-wider">What Was Tried</p>
                    <p className="text-sm text-brand-blue/80 mt-0.5">{extraction.what_was_tried}</p>
                  </div>
                </div>
              )}

              {extraction.barriers && extraction.barriers.length > 0 && (
                <div className="flex gap-3">
                  <div className="w-8 h-8 rounded-lg bg-brand-red/8 flex items-center justify-center shrink-0">
                    <AlertTriangle className="h-4 w-4 text-brand-red" />
                  </div>
                  <div>
                    <p className="text-xs font-semibold text-brand-blue/40 uppercase tracking-wider">Barriers</p>
                    <div className="flex flex-wrap gap-1.5 mt-1">
                      {extraction.barriers.map((b) => (
                        <Badge key={b} variant="outline" className="text-xs rounded-full border-brand-blue/10 text-brand-blue/60">{b}</Badge>
                      ))}
                    </div>
                  </div>
                </div>
              )}

              {extraction.public_benefit && (
                <div className="flex gap-3">
                  <div className="w-8 h-8 rounded-lg bg-brand-teal/10 flex items-center justify-center shrink-0">
                    <Users className="h-4 w-4 text-brand-teal" />
                  </div>
                  <div>
                    <p className="text-xs font-semibold text-brand-blue/40 uppercase tracking-wider">Public Benefit</p>
                    <p className="text-sm text-brand-blue/80 mt-0.5">{extraction.public_benefit}</p>
                  </div>
                </div>
              )}

              {extraction.top_themes && extraction.top_themes.length > 0 && (
                <div className="pt-2 border-t border-brand-blue/5">
                  <p className="text-xs font-semibold text-brand-blue/40 uppercase tracking-wider mb-2">Themes</p>
                  <div className="flex flex-wrap gap-1.5">
                    {extraction.top_themes.map((t) => (
                      <span key={t} className="bg-brand-light-blue text-brand-blue text-xs px-3 py-1 rounded-full">{t}</span>
                    ))}
                  </div>
                </div>
              )}

              {extraction.success_story_candidate && (
                <div className="bg-brand-light-blue/50 rounded-xl p-4 mt-2">
                  <p className="text-xs font-semibold text-brand-blue/40 uppercase tracking-wider mb-1">Your Success Story</p>
                  <p className="text-sm italic text-brand-blue/70">&ldquo;{extraction.success_story_candidate}&rdquo;</p>
                </div>
              )}
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}
