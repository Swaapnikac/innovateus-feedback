"use client";

import { useState, useEffect } from "react";
import { useRouter, useParams } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { InnovateLogo } from "@/components/InnovateLogo";
import { Shield, ArrowRight, CheckCircle2, Clock } from "lucide-react";
import { api } from "@/lib/api";
import { initSession, trackPageView, trackEvent, setContext } from "@/lib/analytics";

const PRIVACY_ITEMS = [
  "Your responses are completely anonymous",
  "No audio is stored. Only transcript text is saved",
  "No identifying information is collected",
  "Responses are used only to improve the program",
];

export default function ConsentPage() {
  const router = useRouter();
  const params = useParams();
  const cohortId = params.cohortId as string;
  const [agreed, setAgreed] = useState(false);
  const [loading, setLoading] = useState(false);
  const [alreadySubmitted, setAlreadySubmitted] = useState(false);

  useEffect(() => {
    // Reset the analytics session and all submission state for a fresh visit.
    // Without this, a second form submission in the same tab reuses the old
    // session token and looks like the same user in the funnel.
    sessionStorage.removeItem("analytics_session");
    sessionStorage.removeItem("submission_id");
    sessionStorage.removeItem("question_data");
    sessionStorage.removeItem("question_order");
    sessionStorage.removeItem("review_answers");
    sessionStorage.removeItem("extraction");
    sessionStorage.removeItem("edit_mode");
    sessionStorage.removeItem("edit_question_id");

    initSession();
    // Track both landing and consent — this page serves as the entry point.
    trackPageView("landing", cohortId);
    trackPageView("consent", cohortId);
  }, [cohortId]);

  const handleStart = async () => {
    setLoading(true);
    try {
      const { submission_id } = await api.startSubmission(cohortId);
      sessionStorage.setItem("submission_id", submission_id);
      setContext(cohortId, submission_id);
      trackEvent("survey_start", {}, cohortId, submission_id);
      router.push(`/c/${cohortId}/survey`);
    } catch (err) {
      const message = err instanceof Error ? err.message : "";
      if (message.includes("already submitted")) {
        setAlreadySubmitted(true);
      } else {
        alert(message || "Failed to start survey");
      }
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

      <div className="max-w-2xl mx-auto px-4 py-10 space-y-6">
        {alreadySubmitted ? (
          <>
            <div className="text-center space-y-3">
              <h1 className="text-3xl font-serif text-brand-blue">Thank You!</h1>
              <p className="text-brand-blue/60">Your feedback has already been recorded.</p>
            </div>
            <Card className="bg-white border-0 shadow-sm rounded-2xl">
              <CardContent className="py-10 text-center space-y-4">
                <CheckCircle2 className="h-12 w-12 text-brand-teal mx-auto" />
                <p className="text-sm text-brand-blue/70 leading-relaxed max-w-sm mx-auto">
                  It looks like you&apos;ve already submitted feedback for this course. We appreciate your participation!
                </p>
                <p className="text-xs text-brand-blue/40">
                  If you believe this is an error, please contact your program administrator.
                </p>
              </CardContent>
            </Card>
          </>
        ) : (
          <>
            <div className="text-center space-y-3">
              <div className="inline-flex items-center gap-2 bg-brand-yellow/15 text-brand-dark-yellow text-xs font-semibold uppercase tracking-widest px-4 py-1.5 rounded-full">
                <Clock className="h-3 w-3" />
                This takes about 2–4 minutes
              </div>
              <h1 className="text-3xl font-serif text-brand-blue">Post-Course Feedback</h1>
              <p className="text-brand-blue/60">Help us improve this course for future learners.</p>
            </div>

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
                  size="lg"
                  className="w-full text-base bg-brand-blue hover:bg-brand-blue/90 gap-2 shadow-md hover:shadow-lg transition-all"
                >
                  {loading ? "Starting..." : "Begin Survey"}
                  <ArrowRight className="h-4 w-4" />
                </Button>
              </CardContent>
            </Card>
          </>
        )}
      </div>
    </div>
  );
}
