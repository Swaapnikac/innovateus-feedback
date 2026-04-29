"use client";

import { useState, useEffect } from "react";
import { useRouter, useParams } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { InnovateLogo } from "@/components/InnovateLogo";
import { Shield, ArrowRight, CheckCircle2 } from "lucide-react";
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
    // Only wipe in-progress survey state when the user has just submitted
    // (we land here from /done's back-button popstate handler, which sets
    // the flag). Otherwise preserve state so pressing Back during the
    // survey doesn't destroy the user's in-progress answers — they should
    // be able to press Forward and resume right where they were.
    let justSubmitted = false;
    try {
      justSubmitted =
        sessionStorage.getItem(`just_submitted_${cohortId}`) === "1";
    } catch {
      // sessionStorage may be disabled (e.g. private mode); silently skip.
    }

    if (justSubmitted) {
      sessionStorage.removeItem("analytics_session");
      sessionStorage.removeItem("submission_id");
      sessionStorage.removeItem("question_data");
      sessionStorage.removeItem("question_order");
      sessionStorage.removeItem("review_answers");
      sessionStorage.removeItem("extraction");
      sessionStorage.removeItem("review_extraction_cache");
      sessionStorage.removeItem("extraction_dirty");
      sessionStorage.removeItem("edit_mode");
      sessionStorage.removeItem("edit_question_id");
      sessionStorage.removeItem(`just_submitted_${cohortId}`);
    }

    initSession();
    // Track both landing and consent — this page serves as the entry point.
    trackPageView("landing", cohortId);
    trackPageView("consent", cohortId);
  }, [cohortId]);

  const handleStart = async () => {
    setLoading(true);
    // Explicit Begin Survey click = fresh survey state. Clear any leftover
    // answers/extractions from a previous in-progress or submitted run in
    // this tab so a returning user doesn't see stale data attached to the
    // new submission_id we're about to create. We deliberately do NOT
    // touch analytics_session here so funnel analytics stay consistent.
    sessionStorage.removeItem("question_data");
    sessionStorage.removeItem("question_order");
    sessionStorage.removeItem("review_answers");
    sessionStorage.removeItem("extraction");
    sessionStorage.removeItem("review_extraction_cache");
    sessionStorage.removeItem("extraction_dirty");
    sessionStorage.removeItem("edit_mode");
    sessionStorage.removeItem("edit_question_id");
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
                <p className="text-xs text-brand-blue/60">
                  If you believe this is an error, please contact your program administrator.
                </p>
              </CardContent>
            </Card>
          </>
        ) : (
          <>
            <div className="text-center space-y-3">
              <h1 className="text-3xl font-serif text-brand-blue">Before You Begin</h1>
            </div>

            <Card className="bg-white border-0 shadow-sm rounded-2xl">
              <CardContent className="pt-5 space-y-4 text-sm leading-relaxed text-brand-blue/70">
                <p>
                  Thank you for taking the time to share feedback on this course. We would like to ask a few quick questions about how you used what you learned and what else would be helpful to learn next.
                </p>
                <p>
                  You may answer open-ended questions by typing or speaking. When a response could use more detail, AI may ask up to two optional follow-up questions and may help summarize responses for analysis.
                </p>
                <p>
                  Your participation is voluntary. All questions are optional and anonymous. This survey should take no more than 3–5 minutes.
                </p>
                <p>
                  This questionnaire is part of a research study conducted by the InnovateUS research team, led by Beth Noveck at Northeastern University.
                </p>
                <p>
                  Questions about the research? Contact the Northeastern University research team at{" "}
                  <a href="mailto:Innovateus_research@northeastern.edu" className="text-brand-blue underline">
                    Innovateus_research@northeastern.edu
                  </a>
                  .
                </p>
                <p>
                  Questions about your rights as a research participant? Contact the Northeastern University Department of Human Research at Tel:{" "}
                  <a href="tel:+17733962327" className="text-brand-blue underline">
                    (773) 396-2327
                  </a>
                  , or Email:{" "}
                  <a href="mailto:IRBReview@northeastern.edu" className="text-brand-blue underline">
                    IRBReview@northeastern.edu
                  </a>
                  . You may call anonymously if you want.
                </p>
              </CardContent>
            </Card>

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
