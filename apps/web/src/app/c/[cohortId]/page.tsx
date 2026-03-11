"use client";

import { useState } from "react";
import { useRouter, useParams } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { InnovateLogo } from "@/components/InnovateLogo";
import { Shield, ArrowRight, CheckCircle2, Clock } from "lucide-react";
import { api } from "@/lib/api";

const PRIVACY_ITEMS = [
  "Your responses are completely anonymous",
  "No audio is stored — only transcript text is saved",
  "No identifying information is collected",
  "Responses are used only to improve the program",
];

export default function ConsentPage() {
  const router = useRouter();
  const params = useParams();
  const cohortId = params.cohortId as string;
  const [agreed, setAgreed] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleStart = async () => {
    setLoading(true);
    try {
      const { submission_id } = await api.startSubmission(cohortId);
      sessionStorage.setItem("submission_id", submission_id);
      router.push(`/c/${cohortId}/survey`);
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to start survey");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-brand-light-blue/40">
      {/* Header */}
      <header className="bg-white/60 backdrop-blur-sm border-b border-brand-blue/5 px-6 py-4">
        <div className="max-w-2xl mx-auto">
          <InnovateLogo size="sm" className="text-brand-blue" />
        </div>
      </header>

      <div className="max-w-lg mx-auto px-4 py-10 space-y-6">
        {/* Title Card */}
        <div className="text-center space-y-3">
          <div className="inline-flex items-center gap-2 bg-brand-yellow/15 text-brand-dark-yellow text-xs font-semibold uppercase tracking-widest px-4 py-1.5 rounded-full">
            <Clock className="h-3 w-3" />
            This takes about 2–4 minutes
          </div>
          <h1 className="text-3xl font-serif text-brand-blue">Post-Course Feedback</h1>
          <p className="text-brand-blue/60">Help us improve this course for future learners.</p>
        </div>

        {/* Privacy Card */}
        <Card className="bg-white border-0 shadow-sm rounded-2xl">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold text-brand-blue flex items-center gap-2">
              <Shield className="h-4 w-4 text-brand-teal" />
              Your Privacy
            </CardTitle>
          </CardHeader>
          <CardContent className="pt-0">
            <ul className="space-y-2.5">
              {PRIVACY_ITEMS.map((item, i) => (
                <li key={i} className="flex items-start gap-2.5 text-sm text-brand-blue/60">
                  <CheckCircle2 className="h-4 w-4 text-brand-teal shrink-0 mt-0.5" />
                  {item}
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>

        {/* Consent + Start */}
        <Card className="bg-white border-0 shadow-sm rounded-2xl">
          <CardContent className="pt-5 space-y-5">
            <label className="flex items-start gap-3 cursor-pointer">
              <Checkbox
                checked={agreed}
                onCheckedChange={(checked) => setAgreed(checked === true)}
                className="mt-0.5"
              />
              <span className="text-sm leading-relaxed text-brand-blue/70">
                I understand that my responses are anonymous and I consent to participate in this feedback survey.
              </span>
            </label>

            <Button
              onClick={handleStart}
              disabled={!agreed || loading}
              className="w-full h-12 text-base rounded-full bg-brand-blue hover:bg-brand-blue/90 gap-2 shadow-md hover:shadow-lg transition-all"
            >
              {loading ? "Starting..." : "Begin Survey"}
              <ArrowRight className="h-4 w-4" />
            </Button>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
