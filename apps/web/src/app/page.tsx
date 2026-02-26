import Link from "next/link";
import { Button } from "@/components/ui/button";
import { InnovateLogo } from "@/components/InnovateLogo";
import {
  ArrowRight,
  Mic,
  BarChart3,
  Shield,
  FileText,
  MessageSquare,
  CheckCircle2,
  Globe,
  Clock,
  Sparkles,
} from "lucide-react";

export default function HomePage() {
  return (
    <div className="min-h-screen bg-white">
      {/* ───── Navbar ───── */}
      <nav className="sticky top-0 z-50 bg-white/80 backdrop-blur-md border-b border-[#E4EFFC]">
        <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
          <InnovateLogo size="md" />
          <div className="flex items-center gap-3">
            <Link href="/c/00000000-0000-0000-0000-000000000001">
              <Button
                variant="outline"
                size="sm"
                className="rounded-full border-[#124D8F]/20 text-[#124D8F] hover:bg-[#E4EFFC] hidden sm:flex"
              >
                Take Survey
              </Button>
            </Link>
            <Link href="/admin/login">
              <Button
                size="sm"
                className="rounded-full bg-[#124D8F] hover:bg-[#124D8F]/90 text-white"
              >
                Manager Login
              </Button>
            </Link>
          </div>
        </div>
      </nav>

      {/* ───── Hero ───── */}
      <section className="relative overflow-hidden bg-gradient-to-br from-[#E4EFFC] via-[#E4EFFC]/60 to-white">
        <div className="absolute top-0 right-0 w-1/2 h-full bg-[radial-gradient(ellipse_at_70%_30%,rgba(18,77,143,0.07)_0%,transparent_70%)]" />
        <div className="max-w-6xl mx-auto px-6 py-24 md:py-32 relative">
          <div className="max-w-2xl space-y-8">
            <div className="inline-flex items-center gap-2 bg-white rounded-full px-4 py-2 shadow-sm border border-[#124D8F]/5">
              <span className="w-2 h-2 rounded-full bg-[#097261] animate-pulse" />
              <span className="text-xs font-semibold text-[#124D8F]/60 uppercase tracking-wider">
                Post-Course Feedback Tool
              </span>
            </div>

            <h1 className="text-4xl md:text-[3.25rem] font-serif text-[#124D8F] leading-[1.15] tracking-tight">
              Share your voice,{" "}
              <span className="relative">
                shape the future
                <svg className="absolute -bottom-1 left-0 w-full" viewBox="0 0 200 8" fill="none">
                  <path d="M1 6C50 2 150 2 199 6" stroke="#FDCE3E" strokeWidth="3" strokeLinecap="round"/>
                </svg>
              </span>{" "}
              of public service learning
            </h1>

            <p className="text-lg text-[#124D8F]/60 leading-relaxed max-w-xl">
              A privacy-first feedback tool that makes it easy to share your course experience — 
              speak or type, in your language, in just a few minutes.
            </p>

            <div className="flex flex-col sm:flex-row gap-3">
              <Link href="/c/00000000-0000-0000-0000-000000000001">
                <Button className="h-13 px-8 text-base rounded-full bg-[#124D8F] hover:bg-[#124D8F]/90 shadow-lg shadow-[#124D8F]/20 hover:shadow-xl hover:shadow-[#124D8F]/25 transition-all gap-2 w-full sm:w-auto">
                  Start Feedback Survey
                  <ArrowRight className="h-4 w-4" />
                </Button>
              </Link>
              <Link href="/admin/login">
                <Button
                  variant="outline"
                  className="h-13 px-8 text-base rounded-full border-[#124D8F]/15 text-[#124D8F] hover:bg-[#E4EFFC]/60 gap-2 w-full sm:w-auto"
                >
                  View Dashboard
                  <ArrowRight className="h-4 w-4" />
                </Button>
              </Link>
            </div>

            <div className="flex items-center gap-6 text-sm text-[#124D8F]/40 pt-2">
              <span className="flex items-center gap-1.5">
                <Clock className="h-3.5 w-3.5" /> 2–4 min
              </span>
              <span className="flex items-center gap-1.5">
                <Shield className="h-3.5 w-3.5" /> Anonymous
              </span>
              <span className="flex items-center gap-1.5">
                <Globe className="h-3.5 w-3.5" /> 7 languages
              </span>
            </div>
          </div>
        </div>
      </section>

      {/* ───── Features ───── */}
      <section className="max-w-6xl mx-auto px-6 py-24">
        <div className="text-center max-w-xl mx-auto mb-16 space-y-4">
          <p className="text-sm font-semibold text-[#D09006] uppercase tracking-widest">
            Features
          </p>
          <h2 className="text-3xl font-serif text-[#124D8F]">
            Designed for government professionals
          </h2>
          <p className="text-[#124D8F]/50">
            Simple, accessible, and built with privacy at its core
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
          {[
            {
              icon: Mic,
              color: "bg-[#FDCE3E]/15",
              iconColor: "text-[#D09006]",
              title: "Voice & Text Input",
              desc: "Speak your feedback naturally or type it out. Real-time transcription with full editing before submission.",
            },
            {
              icon: Sparkles,
              color: "bg-[#124D8F]/8",
              iconColor: "text-[#124D8F]",
              title: "AI-Powered Insights",
              desc: "Smart follow-up questions draw out specific details. Structured extraction surfaces themes, barriers, and success stories.",
            },
            {
              icon: Shield,
              color: "bg-[#097261]/10",
              iconColor: "text-[#097261]",
              title: "Privacy First",
              desc: "Completely anonymous — no login required. Audio is never stored on servers; only your edited transcript is saved.",
            },
            {
              icon: Globe,
              color: "bg-[#124D8F]/8",
              iconColor: "text-[#124D8F]",
              title: "Multilingual Support",
              desc: "Available in English, Spanish, French, Portuguese, Chinese, Hindi, and Arabic — with voice recognition in each.",
            },
            {
              icon: BarChart3,
              color: "bg-[#FDCE3E]/15",
              iconColor: "text-[#D09006]",
              title: "Manager Dashboard",
              desc: "Real-time metrics, response browsing, and top themes at a glance. Filter by cohort and date range.",
            },
            {
              icon: FileText,
              color: "bg-[#097261]/10",
              iconColor: "text-[#097261]",
              title: "Export Reports",
              desc: "Download raw CSV, structured CSV, summary PDF, or a ready-to-present PowerPoint deck — one click.",
            },
          ].map(({ icon: Icon, color, iconColor, title, desc }) => (
            <div key={title} className="group">
              <div className="space-y-4 p-6 rounded-2xl border border-transparent hover:border-[#E4EFFC] hover:bg-[#E4EFFC]/30 transition-all">
                <div className={`w-12 h-12 rounded-xl ${color} flex items-center justify-center`}>
                  <Icon className={`h-6 w-6 ${iconColor}`} />
                </div>
                <h3 className="text-base font-semibold text-[#124D8F]">{title}</h3>
                <p className="text-sm text-[#124D8F]/50 leading-relaxed">{desc}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ───── How It Works ───── */}
      <section className="bg-[#E4EFFC]/40 py-24">
        <div className="max-w-6xl mx-auto px-6">
          <div className="text-center max-w-xl mx-auto mb-16 space-y-4">
            <p className="text-sm font-semibold text-[#D09006] uppercase tracking-widest">
              How It Works
            </p>
            <h2 className="text-3xl font-serif text-[#124D8F]">
              Four simple steps
            </h2>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
            {[
              {
                step: "1",
                icon: MessageSquare,
                title: "Open Your Link",
                desc: "Click the survey link shared by your program — no account or login needed.",
              },
              {
                step: "2",
                icon: Shield,
                title: "Review & Consent",
                desc: "Read the privacy notice and confirm your anonymous participation.",
              },
              {
                step: "3",
                icon: Mic,
                title: "Share Feedback",
                desc: "Answer questions using voice or text. AI may ask a brief follow-up if helpful.",
              },
              {
                step: "4",
                icon: CheckCircle2,
                title: "See Your Summary",
                desc: "Review an AI-generated summary of your feedback before final submission.",
              },
            ].map(({ step, icon: Icon, title, desc }, i) => (
              <div key={step} className="relative">
                {i < 3 && (
                  <div className="hidden md:block absolute top-10 left-[60%] w-[80%] border-t-2 border-dashed border-[#124D8F]/10" />
                )}
                <div className="bg-white rounded-2xl p-6 shadow-sm border border-[#124D8F]/5 relative space-y-4">
                  <div className="flex items-center gap-3">
                    <span className="w-8 h-8 rounded-full bg-[#124D8F] text-white flex items-center justify-center text-sm font-bold">
                      {step}
                    </span>
                    <div className="w-10 h-10 rounded-xl bg-[#E4EFFC] flex items-center justify-center">
                      <Icon className="h-5 w-5 text-[#124D8F]" />
                    </div>
                  </div>
                  <h3 className="font-semibold text-[#124D8F]">{title}</h3>
                  <p className="text-sm text-[#124D8F]/50 leading-relaxed">{desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ───── CTA Banner ───── */}
      <section className="bg-gradient-to-r from-[#124D8F] to-[#1a6bc4]">
        <div className="max-w-6xl mx-auto px-6 py-16 flex flex-col md:flex-row items-center justify-between gap-8">
          <div className="text-white space-y-3 text-center md:text-left">
            <h2 className="text-2xl font-serif">Ready to share your feedback?</h2>
            <p className="text-white/60 max-w-md">
              It only takes 2–4 minutes. Your anonymous input directly shapes how we improve courses for public servants.
            </p>
          </div>
          <Link href="/c/00000000-0000-0000-0000-000000000001">
            <Button className="h-13 px-10 text-base rounded-full bg-[#FDCE3E] text-[#124D8F] hover:bg-[#FDCE3E]/90 font-semibold shadow-lg gap-2">
              Take the Survey
              <ArrowRight className="h-4 w-4" />
            </Button>
          </Link>
        </div>
      </section>

      {/* ───── Footer ───── */}
      <footer className="border-t border-[#E4EFFC] py-10 px-6">
        <div className="max-w-6xl mx-auto flex flex-col sm:flex-row justify-between items-center gap-6">
          <InnovateLogo size="sm" />
          <p className="text-xs text-[#124D8F]/30 text-center sm:text-right">
            Voice-Based Feedback Tool v1.0
            <br />
            Privacy-first feedback for public service professionals
          </p>
        </div>
      </footer>
    </div>
  );
}
