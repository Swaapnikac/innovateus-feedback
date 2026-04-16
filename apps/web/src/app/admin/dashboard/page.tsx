"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
import { useRouter } from "next/navigation";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import {
  Users,
  CheckCircle2,
  Clock,
  Star,
  Download,
  FileText,
  FileSpreadsheet,
  Presentation,
  ChevronLeft,
  ChevronRight,
  Loader2,
  LogOut,
  BarChart3,
  TrendingUp,
  Settings,
  Plus,
  Copy,
  Trash2,
  GitBranch,
  Calendar,
  Brain,
  Sparkles,
} from "lucide-react";
import {
  api,
  type AiInsights,
  type CompareInsights,
  type ExtractionResult,
  type SurveyVersionSummary,
} from "@/lib/api";
import { InnovateLogo } from "@/components/InnovateLogo";
import { NewSurveyDialog, type CreatedCohort } from "@/components/NewSurveyDialog";
import { QuestionStatsCard } from "@/components/QuestionStatsCard";
import { QRCodeSVG } from "qrcode.react";
import { BarChart, Bar, LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, CartesianGrid } from "recharts";

interface CohortItem {
  id: string;
  name: string;
  course_name: string;
  program_type: string | null;
}

interface ResponseItem {
  id: string;
  cohort_id: string;
  created_at: string;
  completed_at: string | null;
  status: string;
  time_to_complete_sec: number | null;
  survey_version: string | null;
  ip_hash: string | null;
  answers: Array<Record<string, unknown>>;
  extraction: ExtractionResult | null;
}

interface ResponsesData {
  items: ResponseItem[];
  total: number;
  page: number;
  page_size: number;
}

interface MetricsData {
  total_submissions: number;
  completed_submissions: number;
  completion_rate: number;
  avg_time_to_complete_sec: number | null;
  avg_recommend_score: number | null;
  confidence_distribution: Record<string, number>;
  vagueness_rate: number | null;
}

// ── Period preset helpers ──

function getDateRange(preset: string): { start: string; end: string } {
  const now = new Date();
  const fmt = (d: Date) => d.toISOString().split("T")[0];
  const end = fmt(now);

  switch (preset) {
    case "7d": {
      const s = new Date(now);
      s.setDate(s.getDate() - 7);
      return { start: fmt(s), end };
    }
    case "30d": {
      const s = new Date(now);
      s.setDate(s.getDate() - 30);
      return { start: fmt(s), end };
    }
    case "month": {
      const s = new Date(now.getFullYear(), now.getMonth(), 1);
      return { start: fmt(s), end };
    }
    default:
      return { start: "", end: "" };
  }
}

export default function DashboardPage() {
  const router = useRouter();
  const [metrics, setMetrics] = useState<MetricsData | null>(null);
  const [responses, setResponses] = useState<ResponsesData | null>(null);
  const [cohorts, setCohorts] = useState<CohortItem[]>([]);

  // ── Filter state ──
  const [selectedProgram, setSelectedProgram] = useState<string>("");
  const [selectedSurvey, setSelectedSurvey] = useState<string>("");
  const [periodPreset, setPeriodPreset] = useState<string>("all");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [versionFilter, setVersionFilter] = useState<string>("");
  const [versions, setVersions] = useState<SurveyVersionSummary[]>([]);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [linkCopied, setLinkCopied] = useState(false);

  // ── Segment filter state ──
  const [segmentQ, setSegmentQ] = useState<string>("");
  const [segmentV, setSegmentV] = useState<string>("");

  // ── Cross-tab state ──
  const [ctQ1, setCtQ1] = useState<string>("");
  const [ctQ2, setCtQ2] = useState<string>("");
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [crosstab, setCrosstab] = useState<any>(null);
  const [ctLoading, setCtLoading] = useState(false);
  const [showCrosstab, setShowCrosstab] = useState(false);

  // ── New survey dialog state ──
  const [showNewProgram, setShowNewProgram] = useState(false);

  // ── Extraction review state (H4 usefulness) ──
  const [reviewsBySub, setReviewsBySub] = useState<Record<string, {
    submission_id: string;
    useful_flag: boolean | null;
    accuracy_rating: number | null;
    usefulness_rating: number | null;
    accuracy_notes: string | null;
    usefulness_notes: string | null;
    reviewed_by: string;
  }>>({});
  const [reviewOpen, setReviewOpen] = useState(false);
  const [reviewSubId, setReviewSubId] = useState<string | null>(null);
  const [reviewForm, setReviewForm] = useState<{
    reviewed_by: string;
    useful_flag: boolean | null;
    accuracy_rating: number | null;
    usefulness_rating: number | null;
    accuracy_notes: string;
    usefulness_notes: string;
  }>({
    reviewed_by: "",
    useful_flag: null,
    accuracy_rating: null,
    usefulness_rating: null,
    accuracy_notes: "",
    usefulness_notes: "",
  });
  const [reviewSaving, setReviewSaving] = useState(false);

  const loadReviews = useCallback(async () => {
    if (!selectedSurvey) return;
    try {
      const res = await api.listReviews(selectedSurvey);
      const map: typeof reviewsBySub = {};
      for (const r of res.items) map[r.submission_id] = r;
      setReviewsBySub(map);
    } catch {
      // swallow — reviews optional
    }
  }, [selectedSurvey]);

  useEffect(() => {
    void loadReviews();
  }, [loadReviews]);

  const openReview = useCallback(
    (submissionId: string, existing?: typeof reviewsBySub[string]) => {
      setReviewSubId(submissionId);
      setReviewForm({
        reviewed_by: existing?.reviewed_by || localStorage.getItem("admin_reviewer_name") || "",
        useful_flag: existing?.useful_flag ?? null,
        accuracy_rating: existing?.accuracy_rating ?? null,
        usefulness_rating: existing?.usefulness_rating ?? null,
        accuracy_notes: existing?.accuracy_notes || "",
        usefulness_notes: existing?.usefulness_notes || "",
      });
      setReviewOpen(true);
    },
    [],
  );

  const saveReview = useCallback(async () => {
    if (!reviewSubId || !reviewForm.reviewed_by.trim()) return;
    setReviewSaving(true);
    try {
      localStorage.setItem("admin_reviewer_name", reviewForm.reviewed_by);
      await api.upsertReview(reviewSubId, {
        reviewed_by: reviewForm.reviewed_by,
        useful_flag: reviewForm.useful_flag ?? undefined,
        accuracy_rating: reviewForm.accuracy_rating ?? undefined,
        usefulness_rating: reviewForm.usefulness_rating ?? undefined,
        accuracy_notes: reviewForm.accuracy_notes || undefined,
        usefulness_notes: reviewForm.usefulness_notes || undefined,
      });
      await loadReviews();
      setReviewOpen(false);
    } catch (err) {
      alert(err instanceof Error ? err.message : String(err));
    } finally {
      setReviewSaving(false);
    }
  }, [reviewSubId, reviewForm, loadReviews]);

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [analytics, setAnalytics] = useState<any>(null);
  const [aiInsights, setAiInsights] = useState<AiInsights | null>(null);
  const [aiLoading, setAiLoading] = useState(false);
  const [aiError, setAiError] = useState("");
  const [compareSurvey, setCompareSurvey] = useState("");
  const [compareInsights, setCompareInsights] = useState<CompareInsights | null>(null);
  const [compareLoading, setCompareLoading] = useState(false);

  // ── Derived: surveys filtered by program type ──
  const filteredSurveys = useMemo(() => {
    if (!selectedProgram) return [];
    if (selectedProgram === "all") return cohorts;
    return cohorts.filter((c) => c.program_type === selectedProgram || !c.program_type);
  }, [cohorts, selectedProgram]);

  // ── Load data for the selected survey ──
  const loadData = useCallback(async () => {
    if (!selectedSurvey) {
      setMetrics(null);
      setResponses(null);
      setAnalytics(null);
      setAiInsights(null);
      setCompareInsights(null);
      setLoading(false);
      return;
    }

    try {
      const params = {
        cohort_id: selectedSurvey,
        start: startDate || undefined,
        end: endDate || undefined,
        survey_version: versionFilter || undefined,
        segment_q: segmentQ || undefined,
        segment_v: segmentV || undefined,
      };

      const [metricsData, responsesData, analyticsData] = await Promise.all([
        api.getMetrics(params),
        api.getResponses({ ...params, page, page_size: 10 }),
        api.getAnalytics({
          cohort_id: selectedSurvey,
          start: startDate || undefined,
          end: endDate || undefined,
          segment_q: segmentQ || undefined,
          segment_v: segmentV || undefined,
        }).catch(() => ({
          funnel: { page_views_landing: 0, page_views_consent: 0, survey_starts: 0, survey_in_progress: 0, survey_completed: 0, dropout_rate: 0 },
          per_question_dropout: [],
          voice_vs_text: { total_open_answers: 0, voice_count: 0, text_count: 0, voice_percentage: 0, per_question: [] },
          followup_effectiveness: { total_vague_detected: 0, followups_shown: 0, followups_answered: 0, followups_skipped: 0, answer_rate: 0 },
          voice_vs_text_quality: { voice_vague_rate: 0, text_vague_rate: 0, voice_avg_length: 0, text_avg_length: 0 },
          review_edits: { total_reviews: 0, reviews_with_edits: 0, edit_rate: 0, edits_per_question: [] },
          experience_rating: { total_ratings: 0, avg_rating: null, distribution: { "1": 0, "2": 0, "3": 0, "4": 0, "5": 0 }, response_rate: 0 },
          time_metrics: { avg_total_sec: null, median_total_sec: null, total_question_answers: 0 },
          per_question_stats: [],
          submissions_by_date: [],
        })),
      ]);

      setMetrics(metricsData);
      setResponses(responsesData);
      setAnalytics(analyticsData);
    } catch {
      router.push("/admin/login");
    } finally {
      setLoading(false);
    }
  }, [selectedSurvey, startDate, endDate, versionFilter, segmentQ, segmentV, page, router]);

  // Load cohorts on mount + refresh on window focus (for cross-tab sync)
  useEffect(() => {
    const fetchCohorts = () => {
      api.getCohorts().then((data) => {
        setCohorts(data as CohortItem[]);
        setLoading(false);
      }).catch(() => {
        router.push("/admin/login");
      });
    };
    fetchCohorts();
    const onFocus = () => fetchCohorts();
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [router]);

  // Reload data when survey/filters change
  useEffect(() => {
    if (selectedSurvey) {
      setLoading(true);
      loadData();
    }
  }, [selectedSurvey, startDate, endDate, versionFilter, segmentQ, segmentV, page, loadData]);

  // Load version history when survey changes
  useEffect(() => {
    if (!selectedSurvey) {
      setVersions([]);
      return;
    }
    api.getVersionHistory(selectedSurvey).then((data) => {
      setVersions(data.items);
    }).catch(() => setVersions([]));
  }, [selectedSurvey]);

  // When program changes, reset survey selection
  const handleProgramChange = (value: string) => {
    setSelectedProgram(value);
    setSelectedSurvey("");
    setVersionFilter("");
    setVersions([]);
    setMetrics(null);
    setResponses(null);
    setAnalytics(null);
    setAiInsights(null);
    setCompareInsights(null);
  };

  // When survey changes, reset filters
  const handleSurveyChange = (value: string) => {
    setSelectedSurvey(value);
    setPage(1);
    setVersionFilter("");
    setSegmentQ("");
    setSegmentV("");
    setCtQ1("");
    setCtQ2("");
    setCrosstab(null);
    setShowCrosstab(false);
    setAiInsights(null);
    setAiError("");
    setCompareSurvey("");
    setCompareInsights(null);
  };

  const clearSegment = () => {
    setSegmentQ("");
    setSegmentV("");
    setPage(1);
  };

  const loadCrosstab = async () => {
    if (!selectedSurvey || !ctQ1 || !ctQ2) return;
    setCtLoading(true);
    try {
      const data = await api.getCrosstab({
        cohort_id: selectedSurvey,
        q1: ctQ1,
        q2: ctQ2,
        start: startDate || undefined,
        end: endDate || undefined,
        survey_version: versionFilter || undefined,
      });
      setCrosstab(data);
    } catch (err) {
      console.error("Crosstab failed:", err);
      setCrosstab(null);
    } finally {
      setCtLoading(false);
    }
  };

  const loadAiInsights = async () => {
    if (!selectedSurvey) return;
    setAiLoading(true);
    setAiError("");
    try {
      const data = await api.getAiInsights({
        cohort_id: selectedSurvey,
        start: startDate || undefined,
        end: endDate || undefined,
        survey_version: versionFilter || undefined,
        segment_q: segmentQ || undefined,
        segment_v: segmentV || undefined,
      });
      setAiInsights(data);
    } catch (err) {
      setAiError(err instanceof Error ? err.message : "Failed to generate AI insights");
    } finally {
      setAiLoading(false);
    }
  };

  const loadCompareInsights = async () => {
    if (!selectedSurvey || !compareSurvey) return;
    setCompareLoading(true);
    try {
      const data = await api.getCompareInsights({
        cohort_id: selectedSurvey,
        compare_cohort_id: compareSurvey,
        start: startDate || undefined,
        end: endDate || undefined,
      });
      setCompareInsights(data);
    } catch (err) {
      setCompareInsights({
        ai_available: false,
        summary: err instanceof Error ? err.message : "Failed to compare surveys",
        wins: [],
        risks: [],
        recommendations: [],
        primary: { id: selectedSurvey, name: selectedSurveyName || "Selected survey", completed_count: 0 },
        comparison: { id: compareSurvey, name: "Comparison survey", completed_count: 0 },
      });
    } finally {
      setCompareLoading(false);
    }
  };

  // When period preset changes, compute dates
  const handlePeriodChange = (value: string) => {
    setPeriodPreset(value);
    if (value === "custom" || value === "all") {
      if (value === "all") {
        setStartDate("");
        setEndDate("");
      }
    } else {
      const { start, end } = getDateRange(value);
      setStartDate(start);
      setEndDate(end);
    }
    setPage(1);
  };

  const handleExport = async (type: "raw.csv" | "structured.csv" | "summary.pdf" | "summary.pptx" | "user-testing.csv") => {
    const url = api.exportUrl(type, {
      cohort_id: selectedSurvey || undefined,
      start: startDate || undefined,
      end: endDate || undefined,
    });
    try {
      const token = localStorage.getItem("admin_token");
      const res = await fetch(url, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        credentials: "include",
      });
      if (!res.ok) throw new Error(`Export failed: ${res.status}`);
      const blob = await res.blob();
      const blobUrl = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = blobUrl;
      const ext = type.split(".").pop();
      a.download = type.includes("summary") ? `summary_report.${ext}` : `${type.replace(".", "_")}_export.${ext}`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(blobUrl);
    } catch (err) {
      console.error("Export failed:", err);
    }
  };

  const handleLogout = () => {
    localStorage.removeItem("admin_token");
    router.push("/admin/login");
  };

  const getSurveyLink = (cohortId: string) =>
    `${window.location.origin}/c/${cohortId}`;

  const copyLink = (cohortId: string) => {
    navigator.clipboard.writeText(getSurveyLink(cohortId));
    setLinkCopied(true);
    setTimeout(() => setLinkCopied(false), 2000);
  };

  const handleSurveyCreated = (cohort: CreatedCohort) => {
    setCohorts((prev) => [cohort, ...prev]);
    if (cohort.program_type) setSelectedProgram(cohort.program_type);
    setSelectedSurvey(cohort.id);
  };

  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [showDeleteSurveyConfirm, setShowDeleteSurveyConfirm] = useState(false);
  const [deletingSurvey, setDeletingSurvey] = useState(false);

  const handleDeleteAllResponses = async () => {
    setDeleting(true);
    try {
      await api.deleteAllResponses(selectedSurvey || undefined);
      setShowDeleteConfirm(false);
      loadData();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to delete responses");
    } finally {
      setDeleting(false);
    }
  };

  const handleDeleteSurvey = async () => {
    if (!selectedSurvey) return;
    setDeletingSurvey(true);
    try {
      await api.deleteCohort(selectedSurvey);
      setCohorts((prev) => prev.filter((c) => c.id !== selectedSurvey));
      setSelectedSurvey("");
    setMetrics(null);
    setResponses(null);
    setAnalytics(null);
    setAiInsights(null);
    setCompareInsights(null);
    setVersions([]);
    setShowDeleteSurveyConfirm(false);
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to delete survey");
    } finally {
      setDeletingSurvey(false);
    }
  };


  // Use analytics data (aggregated across ALL submissions, not just current page)
  const topThemes: [string, number][] = (analytics?.top_themes ?? []).map((t: { theme: string; count: number }) => [t.theme, t.count]);
  const topBarriers: [string, number][] = (analytics?.top_barriers ?? []).map((b: { barrier: string; count: number }) => [b.barrier, b.count]);
  const successStories: string[] = analytics?.success_stories ?? [];

  // ── Question catalog from analytics' per_question_stats (used for segment + crosstab) ──
  interface QuestionMeta {
    question_id: string;
    question_type: string;
    question_text: string;
    total_responses: number;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    stats: Record<string, any>;
  }
  const perQuestionStats: QuestionMeta[] = analytics?.per_question_stats ?? [];

  // Questions eligible for segment filtering (categorical types where picking a value is meaningful)
  const SEGMENTABLE_TYPES = new Set(["rating", "nps", "mcq", "dropdown", "yesno"]);
  const segmentableQuestions = perQuestionStats.filter((q) => SEGMENTABLE_TYPES.has(q.question_type));

  // Available values for the chosen segment question (from the distribution keys)
  const segmentValues = (() => {
    if (!segmentQ) return [];
    const q = perQuestionStats.find((qq) => qq.question_id === segmentQ);
    if (!q) return [];
    const dist = (q.stats?.distribution || {}) as Record<string, number>;
    return Object.keys(dist);
  })();

  // Cross-tab eligible questions (same categorical types)
  const crosstabQuestions = segmentableQuestions;

  const selectedSurveyName = cohorts.find((c) => c.id === selectedSurvey)?.name;
  const comparableSurveys = cohorts.filter((c) => c.id !== selectedSurvey);

  if (loading && !cohorts.length) {
    return (
      <div className="min-h-screen bg-brand-light-blue/40 flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-brand-blue" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-brand-light-blue/40">
      <header className="bg-white border-b border-[#E4EFFC] px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <InnovateLogo size="sm" />
          <div className="h-6 w-px bg-[#124D8F]/10" />
          <span className="text-xs font-semibold text-[#124D8F]/40 uppercase tracking-widest">Dashboard</span>
        </div>
        <div className="flex items-center gap-2">
          <Button size="sm" onClick={() => setShowNewProgram(true)} className="bg-brand-blue hover:bg-brand-blue/90 gap-2">
            <Plus className="h-4 w-4" />
            New Survey
          </Button>
          <Button variant="outline" size="sm" onClick={() => router.push("/admin/user-testing")} className="border-brand-blue/20 text-brand-blue hover:bg-brand-blue/5 gap-2">
            <Sparkles className="h-4 w-4" />
            User Testing
          </Button>
          <Button variant="outline" size="sm" onClick={() => router.push("/admin/pipelines")} className="border-brand-teal/20 text-brand-teal hover:bg-brand-teal/5 gap-2">
            <GitBranch className="h-4 w-4" />
            Pipelines
          </Button>
          <Button variant="outline" size="sm" onClick={handleLogout} className="border-brand-blue/15 text-brand-blue/60 hover:bg-brand-blue/5 gap-2">
            <LogOut className="h-4 w-4" />
            Sign Out
          </Button>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 py-8 space-y-8">
        {/* ── Program & Survey Selectors ── */}
        <Card className="bg-white border-0 shadow-sm rounded-2xl">
          <CardContent className="pt-6">
            <div className="flex flex-wrap gap-4 items-end">
              {/* Program Type */}
              <div className="space-y-1">
                <Label className="text-xs font-semibold text-brand-blue/40 uppercase tracking-wider">Program</Label>
                <Select value={selectedProgram} onValueChange={handleProgramChange}>
                  <SelectTrigger className="w-44 rounded-xl">
                    <SelectValue placeholder="Select program..." />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All</SelectItem>
                    <SelectItem value="course">Course</SelectItem>
                    <SelectItem value="workshop">Workshop</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {/* Survey (filtered by program type) */}
              <div className="space-y-1">
                <Label className="text-xs font-semibold text-brand-blue/40 uppercase tracking-wider">Survey</Label>
                <Select
                  value={selectedSurvey}
                  onValueChange={handleSurveyChange}
                  disabled={!selectedProgram}
                >
                  <SelectTrigger className="w-64 rounded-xl">
                    <SelectValue placeholder={selectedProgram ? "Select survey..." : "Select a program first"} />
                  </SelectTrigger>
                  <SelectContent>
                    {filteredSurveys.map((c) => (
                      <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>
                    ))}
                    {filteredSurveys.length === 0 && selectedProgram && (
                      <p className="px-3 py-2 text-xs text-brand-blue/40">No surveys for this program type</p>
                    )}
                  </SelectContent>
                </Select>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* ── Survey Details (shown only when a survey is selected) ── */}
        {selectedSurvey && (
          <>
            {/* Survey Info Bar: Link, QR, Filters, Editor */}
            <Card className="bg-white border-0 shadow-sm rounded-2xl">
              <CardContent className="pt-6">
                <div className="flex flex-col lg:flex-row gap-6">
                  {/* Left: QR + Link */}
                  <div className="flex items-start gap-4">
                    <div className="bg-white rounded-xl p-2.5 border border-brand-blue/10 shadow-sm shrink-0">
                      <QRCodeSVG
                        value={getSurveyLink(selectedSurvey)}
                        size={100}
                        level="M"
                        bgColor="#ffffff"
                        fgColor="#124D8F"
                      />
                    </div>
                    <div className="space-y-2 min-w-0">
                      <p className="text-sm font-semibold text-brand-blue">{selectedSurveyName}</p>
                      <div className="flex items-center gap-2">
                        <Input
                          readOnly
                          value={getSurveyLink(selectedSurvey)}
                          className="rounded-lg text-xs font-mono h-8 w-72"
                        />
                        <Button
                          size="sm"
                          variant="outline"
                          className="rounded-lg shrink-0 gap-1.5 h-8 text-xs"
                          onClick={() => copyLink(selectedSurvey)}
                        >
                          <Copy className="h-3 w-3" />
                          {linkCopied ? "Copied!" : "Copy"}
                        </Button>
                      </div>
                      <div className="flex items-center gap-2">
                        <Button
                          size="sm"
                          variant="outline"
                          className="gap-2 border-brand-dark-yellow/20 text-brand-dark-yellow hover:bg-brand-yellow/10 text-xs"
                          onClick={() => router.push(`/admin/editor?cohort=${selectedSurvey}`)}
                        >
                          <Settings className="h-3.5 w-3.5" />
                          Survey Editor
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          className="gap-2 border-red-300 text-red-600 hover:bg-red-50 text-xs"
                          onClick={() => setShowDeleteSurveyConfirm(true)}
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                          Delete Survey
                        </Button>
                      </div>
                    </div>
                  </div>

                  {/* Right: Date / Period / Version filters */}
                  <div className="flex flex-wrap gap-3 items-end lg:ml-auto">
                    {/* Period */}
                    <div className="space-y-1">
                      <Label className="text-xs font-semibold text-brand-blue/40 uppercase tracking-wider">Period</Label>
                      <Select value={periodPreset} onValueChange={handlePeriodChange}>
                        <SelectTrigger className="w-40 rounded-xl">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="all">All Time</SelectItem>
                          <SelectItem value="7d">Last 7 Days</SelectItem>
                          <SelectItem value="30d">Last 30 Days</SelectItem>
                          <SelectItem value="month">This Month</SelectItem>
                          <SelectItem value="custom">Custom Range</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>

                    {/* Custom date range */}
                    {periodPreset === "custom" && (
                      <>
                        <div className="space-y-1">
                          <Label className="text-xs text-brand-blue/40">Start</Label>
                          <Input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} className="w-36 rounded-xl h-10" />
                        </div>
                        <div className="space-y-1">
                          <Label className="text-xs text-brand-blue/40">End</Label>
                          <Input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} className="w-36 rounded-xl h-10" />
                        </div>
                      </>
                    )}

                    {/* Version */}
                    <div className="space-y-1">
                      <Label className="text-xs font-semibold text-brand-blue/40 uppercase tracking-wider">Version</Label>
                      <Select value={versionFilter || "all"} onValueChange={(v) => { setVersionFilter(v === "all" ? "" : v); setPage(1); }}>
                        <SelectTrigger className="w-32 rounded-xl">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="all">All Versions</SelectItem>
                          {versions.map((v) => (
                            <SelectItem key={v.version_label} value={v.version_label}>
                              {v.version_label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* ── Metrics ── */}
            {loading ? (
              <div className="flex justify-center py-12">
                <Loader2 className="h-8 w-8 animate-spin text-brand-blue" />
              </div>
            ) : (
              <>
                {metrics && (
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                    <Card className="bg-white border-0 shadow-sm rounded-2xl">
                      <CardContent className="pt-6">
                        <div className="flex items-center gap-3">
                          <div className="w-10 h-10 rounded-xl bg-brand-blue/8 flex items-center justify-center">
                            <Users className="h-5 w-5 text-brand-blue" />
                          </div>
                          <div>
                            <p className="text-2xl font-bold text-brand-blue">{metrics.total_submissions}</p>
                            <p className="text-xs text-brand-blue/40">Total Submissions</p>
                          </div>
                        </div>
                      </CardContent>
                    </Card>
                    <Card className="bg-white border-0 shadow-sm rounded-2xl">
                      <CardContent className="pt-6">
                        <div className="flex items-center gap-3">
                          <div className="w-10 h-10 rounded-xl bg-brand-teal/10 flex items-center justify-center">
                            <CheckCircle2 className="h-5 w-5 text-brand-teal" />
                          </div>
                          <div>
                            <p className="text-2xl font-bold text-brand-blue">{(metrics.completion_rate * 100).toFixed(0)}%</p>
                            <p className="text-xs text-brand-blue/40">Completion Rate</p>
                          </div>
                        </div>
                      </CardContent>
                    </Card>
                    <Card className="bg-white border-0 shadow-sm rounded-2xl">
                      <CardContent className="pt-6">
                        <div className="flex items-center gap-3">
                          <div className="w-10 h-10 rounded-xl bg-brand-yellow/15 flex items-center justify-center">
                            <Star className="h-5 w-5 text-brand-dark-yellow" />
                          </div>
                          <div>
                            <p className="text-2xl font-bold text-brand-blue">
                              {metrics.avg_recommend_score?.toFixed(1) || "—"}/10
                            </p>
                            <p className="text-xs text-brand-blue/40">Avg. Recommend Score</p>
                          </div>
                        </div>
                      </CardContent>
                    </Card>
                    <Card className="bg-white border-0 shadow-sm rounded-2xl">
                      <CardContent className="pt-6">
                        <div className="flex items-center gap-3">
                          <div className="w-10 h-10 rounded-xl bg-brand-blue/8 flex items-center justify-center">
                            <Clock className="h-5 w-5 text-brand-blue" />
                          </div>
                          <div>
                            <p className="text-2xl font-bold text-brand-blue">
                              {metrics.avg_time_to_complete_sec
                                ? `${Math.round(metrics.avg_time_to_complete_sec / 60)}m`
                                : "—"}
                            </p>
                            <p className="text-xs text-brand-blue/40">Avg. Completion Time</p>
                          </div>
                        </div>
                      </CardContent>
                    </Card>
                  </div>
                )}

                {/* ── Segment Filter ── */}
                {segmentableQuestions.length > 0 && (
                  <Card className="bg-white border-0 shadow-sm rounded-2xl">
                    <CardContent className="pt-6">
                      <div className="flex flex-wrap gap-3 items-end">
                        <div className="space-y-1">
                          <Label className="text-xs font-semibold text-brand-blue/40 uppercase tracking-wider">
                            Segment: Filter By
                          </Label>
                          <Select
                            value={segmentQ || "__none__"}
                            onValueChange={(v) => {
                              setSegmentQ(v === "__none__" ? "" : v);
                              setSegmentV("");
                              setPage(1);
                            }}
                          >
                            <SelectTrigger className="w-64 rounded-xl">
                              <SelectValue placeholder="No segment" />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value="__none__">No segment</SelectItem>
                              {segmentableQuestions.map((q) => (
                                <SelectItem key={q.question_id} value={q.question_id}>
                                  {q.question_text.length > 50 ? q.question_text.slice(0, 50) + "…" : q.question_text}
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        </div>
                        {segmentQ && (
                          <div className="space-y-1">
                            <Label className="text-xs font-semibold text-brand-blue/40 uppercase tracking-wider">
                              Where Answer Is
                            </Label>
                            <Select
                              value={segmentV}
                              onValueChange={(v) => { setSegmentV(v); setPage(1); }}
                            >
                              <SelectTrigger className="w-52 rounded-xl">
                                <SelectValue placeholder="Select a value..." />
                              </SelectTrigger>
                              <SelectContent>
                                {segmentValues.map((v) => (
                                  <SelectItem key={v} value={v}>{v}</SelectItem>
                                ))}
                              </SelectContent>
                            </Select>
                          </div>
                        )}
                        {(segmentQ || segmentV) && (
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={clearSegment}
                            className="gap-1.5 text-brand-blue/50 text-xs h-10"
                          >
                            Clear
                          </Button>
                        )}
                        {segmentQ && segmentV && (
                          <p className="text-xs text-brand-teal ml-auto">
                            Scoped to {metrics?.total_submissions ?? 0} segmented responses
                          </p>
                        )}
                      </div>
                    </CardContent>
                  </Card>
                )}

                {/* ── Trend Over Time ── */}
                {analytics?.submissions_by_date && analytics.submissions_by_date.length > 0 && (
                  <Card className="bg-white border-0 shadow-sm rounded-2xl">
                    <CardHeader className="pb-3">
                      <CardTitle className="text-sm font-medium flex items-center gap-2 text-brand-blue">
                        <TrendingUp className="h-4 w-4" />
                        Responses Over Time
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="h-56">
                        <ResponsiveContainer width="100%" height="100%">
                          <LineChart data={analytics.submissions_by_date}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#E4EFFC" />
                            <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                            <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
                            <Tooltip />
                            <Line
                              type="monotone"
                              dataKey="count"
                              stroke="#124D8F"
                              strokeWidth={2}
                              dot={{ fill: "#124D8F", r: 4 }}
                              activeDot={{ r: 6 }}
                            />
                          </LineChart>
                        </ResponsiveContainer>
                      </div>
                    </CardContent>
                  </Card>
                )}

                {/* ── AI Insights ── */}
                <Card className="bg-white border-0 shadow-sm rounded-2xl">
                  <CardHeader className="pb-3 flex flex-row items-center justify-between">
                    <CardTitle className="text-sm font-medium flex items-center gap-2 text-brand-blue">
                      <Brain className="h-4 w-4" />
                      AI Insights
                    </CardTitle>
                    <Button
                      size="sm"
                      onClick={loadAiInsights}
                      disabled={aiLoading}
                      className="gap-2 bg-brand-blue hover:bg-brand-blue/90 text-xs"
                    >
                      {aiLoading ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <Sparkles className="h-4 w-4" />
                      )}
                      Generate
                    </Button>
                  </CardHeader>
                  <CardContent className="space-y-5">
                    {aiError && (
                      <p className="text-sm text-brand-red">{aiError}</p>
                    )}
                    {!aiInsights && !aiError && (
                      <p className="text-sm text-brand-blue/45">
                        Generate sentiment, topic clusters, response-quality scores, and recommendations for open-ended answers.
                      </p>
                    )}
                    {aiInsights && (
                      <>
                        {!aiInsights.ai_available && (
                          <Badge variant="outline" className="border-brand-dark-yellow/30 text-brand-dark-yellow">
                            Heuristic mode
                          </Badge>
                        )}
                        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
                          <div className="rounded-xl bg-brand-blue/5 p-3">
                            <p className="text-2xl font-bold text-brand-blue">{aiInsights.total_open_responses}</p>
                            <p className="text-xs text-brand-blue/45">Open Responses</p>
                          </div>
                          <div className="rounded-xl bg-brand-teal/8 p-3">
                            <p className="text-2xl font-bold text-brand-teal">
                              {aiInsights.average_quality_score?.toFixed(1) || "—"}
                              <span className="text-sm font-normal text-brand-blue/35">/5</span>
                            </p>
                            <p className="text-xs text-brand-blue/45">Avg Quality</p>
                          </div>
                          {["positive", "neutral"].map((key) => (
                            <div key={key} className="rounded-xl bg-gray-50 p-3">
                              <p className="text-2xl font-bold text-brand-blue">
                                {aiInsights.sentiment_distribution[key] || 0}
                              </p>
                              <p className="text-xs capitalize text-brand-blue/45">{key}</p>
                            </div>
                          ))}
                        </div>

                        {aiInsights.summary && (
                          <p className="text-sm text-brand-blue/70 leading-relaxed">
                            {aiInsights.summary}
                          </p>
                        )}

                        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
                          <div className="space-y-3">
                            <Label className="text-xs font-semibold text-brand-blue/40 uppercase tracking-wider">
                              Topic Clusters
                            </Label>
                            {aiInsights.topics.length > 0 ? (
                              aiInsights.topics.slice(0, 6).map((topic) => (
                                <div key={topic.label} className="rounded-xl border border-brand-blue/10 px-3 py-2">
                                  <div className="flex items-center justify-between gap-3">
                                    <p className="text-sm font-medium text-brand-blue">{topic.label}</p>
                                    <Badge variant="secondary" className="text-xs">{topic.count}</Badge>
                                  </div>
                                  <p className="text-xs text-brand-blue/45 mt-1">{topic.summary}</p>
                                </div>
                              ))
                            ) : (
                              <p className="text-xs text-brand-blue/35">No topic clusters yet.</p>
                            )}
                          </div>
                          <div className="space-y-3">
                            <Label className="text-xs font-semibold text-brand-blue/40 uppercase tracking-wider">
                              Recommendations
                            </Label>
                            {aiInsights.recommendations.length > 0 ? (
                              aiInsights.recommendations.slice(0, 5).map((item, i) => (
                                <p key={i} className="text-sm text-brand-blue/65 border-l-2 border-brand-teal/30 pl-3">
                                  {item}
                                </p>
                              ))
                            ) : (
                              <p className="text-xs text-brand-blue/35">No recommendations generated.</p>
                            )}
                          </div>
                        </div>

                        {aiInsights.answer_insights.length > 0 && (
                          <div className="overflow-x-auto">
                            <Table>
                              <TableHeader>
                                <TableRow>
                                  <TableHead>Question</TableHead>
                                  <TableHead>Sentiment</TableHead>
                                  <TableHead>Quality</TableHead>
                                  <TableHead>Excerpt</TableHead>
                                </TableRow>
                              </TableHeader>
                              <TableBody>
                                {aiInsights.answer_insights.slice(0, 8).map((item, i) => (
                                  <TableRow key={`${item.submission_id}-${item.question_id}-${i}`}>
                                    <TableCell className="text-xs max-w-[220px] truncate">
                                      {item.question_text || item.question_id}
                                    </TableCell>
                                    <TableCell>
                                      <Badge variant="outline" className="text-xs capitalize">
                                        {item.sentiment}
                                      </Badge>
                                    </TableCell>
                                    <TableCell className="text-xs font-semibold">
                                      {item.quality_score}/5
                                    </TableCell>
                                    <TableCell className="text-xs max-w-[360px] text-brand-blue/60">
                                      {item.answer_text || "—"}
                                    </TableCell>
                                  </TableRow>
                                ))}
                              </TableBody>
                            </Table>
                          </div>
                        )}
                      </>
                    )}
                  </CardContent>
                </Card>

                {/* ── Comparative AI Insights ── */}
                {comparableSurveys.length > 0 && (
                  <Card className="bg-white border-0 shadow-sm rounded-2xl">
                    <CardHeader className="pb-3">
                      <CardTitle className="text-sm font-medium flex items-center gap-2 text-brand-blue">
                        <Sparkles className="h-4 w-4" />
                        Compare Surveys
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      <div className="flex flex-wrap gap-3 items-end">
                        <div className="space-y-1">
                          <Label className="text-xs font-semibold text-brand-blue/40 uppercase tracking-wider">
                            Compare Against
                          </Label>
                          <Select value={compareSurvey} onValueChange={setCompareSurvey}>
                            <SelectTrigger className="w-72 rounded-xl">
                              <SelectValue placeholder="Select another survey..." />
                            </SelectTrigger>
                            <SelectContent>
                              {comparableSurveys.map((survey) => (
                                <SelectItem key={survey.id} value={survey.id}>
                                  {survey.name}
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        </div>
                        <Button
                          size="sm"
                          onClick={loadCompareInsights}
                          disabled={!compareSurvey || compareLoading}
                          className="gap-2 bg-brand-blue hover:bg-brand-blue/90"
                        >
                          {compareLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                          Compare
                        </Button>
                      </div>
                      {compareInsights && (
                        <div className="space-y-4">
                          <div className="rounded-xl bg-brand-light-blue/50 px-4 py-3">
                            <p className="text-sm text-brand-blue/75">{compareInsights.summary}</p>
                            <p className="text-xs text-brand-blue/40 mt-2">
                              {compareInsights.primary.name}: {compareInsights.primary.completed_count} completed · {compareInsights.comparison.name}: {compareInsights.comparison.completed_count} completed
                            </p>
                          </div>
                          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                            {[
                              ["Wins", compareInsights.wins],
                              ["Risks", compareInsights.risks],
                              ["Recommendations", compareInsights.recommendations],
                            ].map(([label, items]) => (
                              <div key={label as string} className="space-y-2">
                                <Label className="text-xs font-semibold text-brand-blue/40 uppercase tracking-wider">
                                  {label as string}
                                </Label>
                                {(items as string[]).length > 0 ? (
                                  (items as string[]).slice(0, 4).map((item, i) => (
                                    <p key={i} className="text-xs text-brand-blue/60">
                                      {item}
                                    </p>
                                  ))
                                ) : (
                                  <p className="text-xs text-brand-blue/30">No items.</p>
                                )}
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </CardContent>
                  </Card>
                )}

                {/* Themes & Barriers Row */}
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
                  <Card className="bg-white border-0 shadow-sm rounded-2xl">
                    <CardHeader className="pb-3">
                      <CardTitle className="text-sm font-medium flex items-center gap-2 text-brand-blue">
                        <BarChart3 className="h-4 w-4" />
                        Top Themes
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      {topThemes.length > 0 ? (
                        <div className="space-y-2">
                          {topThemes.map(([theme, count]) => (
                            <div key={theme} className="flex items-center justify-between">
                              <span className="text-sm truncate">{theme}</span>
                              <Badge variant="secondary" className="text-xs">{count}</Badge>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <p className="text-sm text-muted-foreground">No themes yet</p>
                      )}
                    </CardContent>
                  </Card>

                  <Card className="bg-white border-0 shadow-sm rounded-2xl">
                    <CardHeader className="pb-3">
                      <CardTitle className="text-sm font-medium flex items-center gap-2 text-brand-blue">
                        <TrendingUp className="h-4 w-4 text-brand-red" />
                        Top Barriers
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      {topBarriers.length > 0 ? (
                        <div className="space-y-2">
                          {topBarriers.map(([barrier, count]) => (
                            <div key={barrier} className="flex items-center justify-between">
                              <span className="text-sm truncate">{barrier}</span>
                              <Badge variant="outline" className="text-xs">{count}</Badge>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <p className="text-sm text-muted-foreground">No barriers reported</p>
                      )}
                    </CardContent>
                  </Card>

                  <Card className="bg-white border-0 shadow-sm rounded-2xl">
                    <CardHeader className="pb-3">
                      <CardTitle className="text-sm font-medium flex items-center gap-2 text-brand-blue">
                        <Star className="h-4 w-4 text-brand-dark-yellow" />
                        Success Stories
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      {successStories.length > 0 ? (
                        <div className="space-y-3">
                          {successStories.slice(0, 3).map((story, i) => (
                            <p key={i} className="text-sm italic text-muted-foreground border-l-2 border-brand-yellow pl-3">
                              &ldquo;{story}&rdquo;
                            </p>
                          ))}
                        </div>
                      ) : (
                        <p className="text-sm text-muted-foreground">No stories yet</p>
                      )}
                    </CardContent>
                  </Card>
                </div>

                {/* ── Per-Question Analytics ── */}
                {perQuestionStats.length > 0 && (
                  <>
                    <div className="pt-2">
                      <h2 className="text-lg font-serif text-brand-blue mb-1">Question Analytics</h2>
                      <p className="text-xs text-brand-blue/40">Type-specific breakdown for each question.</p>
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      {perQuestionStats.map((q) => (
                        <QuestionStatsCard key={q.question_id} question={q} />
                      ))}
                    </div>
                  </>
                )}

                {/* ── Cross-tabulation ── */}
                {crosstabQuestions.length >= 2 && (
                  <Card className="bg-white border-0 shadow-sm rounded-2xl">
                    <CardHeader
                      className="pb-3 cursor-pointer"
                      onClick={() => setShowCrosstab(!showCrosstab)}
                    >
                      <CardTitle className="text-sm font-medium text-brand-blue flex items-center justify-between">
                        <span className="flex items-center gap-2">
                          <BarChart3 className="h-4 w-4" />
                          Cross-Tabulation (Advanced)
                        </span>
                        <span className="text-xs text-brand-blue/40">
                          {showCrosstab ? "Hide" : "Show"}
                        </span>
                      </CardTitle>
                    </CardHeader>
                    {showCrosstab && (
                      <CardContent className="space-y-4">
                        <p className="text-xs text-brand-blue/50">
                          Compare how responses to one question relate to another.
                        </p>
                        <div className="flex flex-wrap gap-3 items-end">
                          <div className="space-y-1">
                            <Label className="text-xs font-semibold text-brand-blue/40 uppercase tracking-wider">
                              Question 1 (rows)
                            </Label>
                            <Select value={ctQ1} onValueChange={setCtQ1}>
                              <SelectTrigger className="w-64 rounded-xl">
                                <SelectValue placeholder="Select question..." />
                              </SelectTrigger>
                              <SelectContent>
                                {crosstabQuestions.map((q) => (
                                  <SelectItem key={q.question_id} value={q.question_id}>
                                    {q.question_text.length > 50 ? q.question_text.slice(0, 50) + "…" : q.question_text}
                                  </SelectItem>
                                ))}
                              </SelectContent>
                            </Select>
                          </div>
                          <div className="space-y-1">
                            <Label className="text-xs font-semibold text-brand-blue/40 uppercase tracking-wider">
                              Question 2 (columns)
                            </Label>
                            <Select value={ctQ2} onValueChange={setCtQ2}>
                              <SelectTrigger className="w-64 rounded-xl">
                                <SelectValue placeholder="Select question..." />
                              </SelectTrigger>
                              <SelectContent>
                                {crosstabQuestions
                                  .filter((q) => q.question_id !== ctQ1)
                                  .map((q) => (
                                    <SelectItem key={q.question_id} value={q.question_id}>
                                      {q.question_text.length > 50 ? q.question_text.slice(0, 50) + "…" : q.question_text}
                                    </SelectItem>
                                  ))}
                              </SelectContent>
                            </Select>
                          </div>
                          <Button
                            size="sm"
                            onClick={loadCrosstab}
                            disabled={!ctQ1 || !ctQ2 || ctLoading}
                            className="bg-brand-blue hover:bg-brand-blue/90 gap-2"
                          >
                            {ctLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                            Compute
                          </Button>
                        </div>

                        {crosstab && (
                          <div className="overflow-x-auto pt-2">
                            <table className="w-full text-sm">
                              <thead>
                                <tr className="border-b border-brand-blue/10">
                                  <th className="text-left py-2 px-2 text-xs text-brand-blue/40 font-normal"></th>
                                  {crosstab.q2_values.map((v: string) => (
                                    <th key={v} className="text-center py-2 px-2 text-xs text-brand-blue/60 font-normal">
                                      {v}
                                    </th>
                                  ))}
                                </tr>
                              </thead>
                              <tbody>
                                {crosstab.q1_values.map((r: string) => {
                                  const maxCount = Math.max(
                                    ...(Object.values(crosstab.matrix).flatMap((row) =>
                                      Object.values(row as Record<string, number>)
                                    ) as number[]),
                                    1
                                  );
                                  return (
                                    <tr key={r} className="border-b border-brand-blue/5 last:border-0">
                                      <td className="py-2 px-2 text-brand-blue font-medium text-xs">{r}</td>
                                      {crosstab.q2_values.map((c: string) => {
                                        const count = crosstab.matrix[r]?.[c] ?? 0;
                                        const intensity = count / maxCount;
                                        return (
                                          <td
                                            key={c}
                                            className="text-center py-2 px-2 text-brand-blue font-mono text-xs rounded"
                                            style={{
                                              backgroundColor: `rgba(18, 77, 143, ${intensity * 0.35})`,
                                            }}
                                          >
                                            {count || "—"}
                                          </td>
                                        );
                                      })}
                                    </tr>
                                  );
                                })}
                              </tbody>
                            </table>
                            <p className="text-xs text-brand-blue/40 mt-2">
                              Total: {crosstab.total} responses with both answers.
                            </p>
                          </div>
                        )}
                      </CardContent>
                    )}
                  </Card>
                )}

                {/* Exports */}
                <Card className="bg-white border-0 shadow-sm rounded-2xl">
                  <CardHeader className="pb-3">
                    <CardTitle className="text-sm font-medium flex items-center gap-2 text-brand-blue">
                      <Download className="h-4 w-4" />
                      Export Data
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="flex flex-wrap gap-2">
                      <Button variant="outline" size="sm" onClick={() => handleExport("raw.csv")} className="gap-2 border-brand-blue/15 text-brand-blue/70">
                        <FileSpreadsheet className="h-4 w-4" /> Raw CSV
                      </Button>
                      <Button variant="outline" size="sm" onClick={() => handleExport("structured.csv")} className="gap-2 border-brand-blue/15 text-brand-blue/70">
                        <FileSpreadsheet className="h-4 w-4" /> Structured CSV
                      </Button>
                      <Button variant="outline" size="sm" onClick={() => handleExport("summary.pdf")} className="gap-2 border-brand-blue/15 text-brand-blue/70">
                        <FileText className="h-4 w-4" /> Summary PDF
                      </Button>
                      <Button variant="outline" size="sm" onClick={() => handleExport("summary.pptx")} className="gap-2 border-brand-blue/15 text-brand-blue/70">
                        <Presentation className="h-4 w-4" /> Summary PPTX
                      </Button>
                      <Button variant="outline" size="sm" onClick={() => handleExport("user-testing.csv")} className="gap-2 border-brand-teal/20 text-brand-teal">
                        <FileSpreadsheet className="h-4 w-4" /> User Testing CSV
                      </Button>
                    </div>
                  </CardContent>
                </Card>

                {/* Responses Table */}
                {responses && (
                  <Card className="bg-white border-0 shadow-sm rounded-2xl">
                    <CardHeader className="pb-3 flex flex-row items-center justify-between">
                      <CardTitle className="text-sm font-medium text-brand-blue">
                        Responses ({responses.total} total)
                      </CardTitle>
                      {responses.total > 0 && (
                        <Button
                          variant="outline"
                          size="sm"
                          className="gap-2 border-red-300 text-red-600 hover:bg-red-50"
                          onClick={() => setShowDeleteConfirm(true)}
                        >
                          <Trash2 className="h-4 w-4" /> Delete All
                        </Button>
                      )}
                    </CardHeader>
                    <CardContent>
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead>Date</TableHead>
                            <TableHead>Status</TableHead>
                            <TableHead>Version</TableHead>
                            <TableHead>Time</TableHead>
                            <TableHead>Recommend</TableHead>
                            <TableHead>Planned Workflow</TableHead>
                            <TableHead>Review</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {responses.items.map((item) => {
                            const recommend = item.answers.find(
                              (a) => a.question_id === "q1_recommend"
                            );
                            const existingReview = reviewsBySub[item.id];
                            return (
                              <TableRow key={item.id}>
                                <TableCell className="text-xs">
                                  {new Date(item.created_at).toLocaleDateString()}
                                </TableCell>
                                <TableCell>
                                  <Badge
                                    variant={item.status === "completed" ? "default" : "secondary"}
                                    className="text-xs"
                                  >
                                    {item.status}
                                  </Badge>
                                </TableCell>
                                <TableCell>
                                  {item.survey_version ? (
                                    <Badge variant="outline" className="text-xs font-mono border-brand-blue/20 text-brand-blue/50">
                                      {item.survey_version}
                                    </Badge>
                                  ) : (
                                    <span className="text-xs text-brand-blue/20">—</span>
                                  )}
                                </TableCell>
                                <TableCell className="text-xs">
                                  {item.time_to_complete_sec
                                    ? `${Math.round(item.time_to_complete_sec / 60)}m`
                                    : "—"}
                                </TableCell>
                                <TableCell className="text-xs">
                                  {(recommend?.answer_raw as string) || "—"}
                                </TableCell>
                                <TableCell className="text-xs max-w-[200px] truncate">
                                  {item.extraction?.planned_task_or_workflow || "—"}
                                </TableCell>
                                <TableCell className="text-xs">
                                  <Button
                                    variant="ghost"
                                    size="sm"
                                    className="h-7 px-2 text-brand-blue"
                                    onClick={() => openReview(item.id, existingReview)}
                                    disabled={!item.extraction}
                                  >
                                    {existingReview ? (
                                      existingReview.useful_flag ? (
                                        <Badge className="bg-green-100 text-green-700 hover:bg-green-100">Useful</Badge>
                                      ) : (
                                        <Badge variant="outline" className="border-amber-500 text-amber-700">Not useful</Badge>
                                      )
                                    ) : (
                                      "Rate"
                                    )}
                                  </Button>
                                </TableCell>
                              </TableRow>
                            );
                          })}
                        </TableBody>
                      </Table>

                      {responses.total > responses.page_size && (
                        <div className="flex items-center justify-between mt-4">
                          <p className="text-xs text-muted-foreground">
                            Page {responses.page} of {Math.ceil(responses.total / responses.page_size)}
                          </p>
                          <div className="flex gap-2">
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => setPage(page - 1)}
                              disabled={page <= 1}
                            >
                              <ChevronLeft className="h-4 w-4" />
                            </Button>
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => setPage(page + 1)}
                              disabled={page * responses.page_size >= responses.total}
                            >
                              <ChevronRight className="h-4 w-4" />
                            </Button>
                          </div>
                        </div>
                      )}
                    </CardContent>
                  </Card>
                )}

                {/* ── Analytics Section ── */}
                {analytics && (
                  <>
                    <div className="pt-4">
                      <h2 className="text-lg font-serif text-brand-blue mb-4">User Testing Analytics</h2>
                    </div>

                    {/* Funnel */}
                    <Card className="bg-white border-0 shadow-sm rounded-2xl">
                      <CardHeader className="pb-3">
                        <CardTitle className="text-sm font-medium text-brand-blue flex items-center gap-2">
                          <TrendingUp className="h-4 w-4" /> Survey Funnel
                        </CardTitle>
                      </CardHeader>
                      <CardContent>
                        <div className="h-64">
                          <ResponsiveContainer width="100%" height="100%">
                            <BarChart data={[
                              { name: "Landing", value: analytics.funnel.page_views_landing },
                              { name: "Consent", value: analytics.funnel.page_views_consent },
                              { name: "Started", value: analytics.funnel.survey_starts },
                              { name: "In Progress", value: analytics.funnel.survey_in_progress },
                              { name: "Completed", value: analytics.funnel.survey_completed },
                            ]}>
                              <XAxis dataKey="name" tick={{ fontSize: 12 }} />
                              <YAxis tick={{ fontSize: 12 }} />
                              <Tooltip />
                              <Bar dataKey="value" radius={[6, 6, 0, 0]}>
                                {["#124D8F", "#124D8F", "#097261", "#097261", "#097261"].map((color, i) => (
                                  <Cell key={i} fill={color} fillOpacity={0.6 + i * 0.1} />
                                ))}
                              </Bar>
                            </BarChart>
                          </ResponsiveContainer>
                        </div>
                        <p className="text-xs text-brand-blue/40 mt-2">
                          Dropout rate: {(analytics.funnel.dropout_rate * 100).toFixed(1)}%
                        </p>
                      </CardContent>
                    </Card>

                    {/* Per-Question Dropout + Voice vs Text */}
                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
                      <Card className="bg-white border-0 shadow-sm rounded-2xl">
                        <CardHeader className="pb-3">
                          <CardTitle className="text-sm font-medium text-brand-blue">Per-Question Dropout</CardTitle>
                        </CardHeader>
                        <CardContent>
                          <Table>
                            <TableHeader>
                              <TableRow>
                                <TableHead>Question</TableHead>
                                <TableHead>Reached</TableHead>
                                <TableHead>Answered</TableHead>
                                <TableHead>Dropped</TableHead>
                              </TableRow>
                            </TableHeader>
                            <TableBody>
                              {analytics.per_question_dropout.map((q: { question_id: string; reached: number; answered: number; dropout_count: number }) => (
                                <TableRow key={q.question_id} className={q.dropout_count > 0 ? "bg-red-50/50" : ""}>
                                  <TableCell className="text-xs font-mono">{q.question_id}</TableCell>
                                  <TableCell className="text-xs">{q.reached}</TableCell>
                                  <TableCell className="text-xs">{q.answered}</TableCell>
                                  <TableCell className="text-xs text-brand-red">{q.dropout_count}</TableCell>
                                </TableRow>
                              ))}
                            </TableBody>
                          </Table>
                        </CardContent>
                      </Card>

                      <Card className="bg-white border-0 shadow-sm rounded-2xl">
                        <CardHeader className="pb-3">
                          <CardTitle className="text-sm font-medium text-brand-blue">Voice vs Text Usage</CardTitle>
                        </CardHeader>
                        <CardContent>
                          <div className="space-y-4">
                            <div className="flex items-center gap-4">
                              <div className="flex-1 text-center p-3 bg-brand-blue/5 rounded-xl">
                                <p className="text-2xl font-bold text-brand-blue">{(analytics.voice_vs_text.voice_percentage * 100).toFixed(0)}%</p>
                                <p className="text-xs text-brand-blue/40">Voice</p>
                              </div>
                              <div className="flex-1 text-center p-3 bg-brand-yellow/10 rounded-xl">
                                <p className="text-2xl font-bold text-brand-dark-yellow">{((1 - analytics.voice_vs_text.voice_percentage) * 100).toFixed(0)}%</p>
                                <p className="text-xs text-brand-blue/40">Text</p>
                              </div>
                            </div>
                            <div className="h-48">
                              <ResponsiveContainer width="100%" height="100%">
                                <BarChart data={analytics.voice_vs_text.per_question.map((q: { question_id: string; voice: number; text: number }) => ({
                                  name: q.question_id.replace("q", "Q").replace("_", " "),
                                  Voice: q.voice,
                                  Text: q.text,
                                }))}>
                                  <XAxis dataKey="name" tick={{ fontSize: 10 }} />
                                  <YAxis tick={{ fontSize: 10 }} />
                                  <Tooltip />
                                  <Bar dataKey="Voice" fill="#124D8F" radius={[4, 4, 0, 0]} />
                                  <Bar dataKey="Text" fill="#FDCE3E" radius={[4, 4, 0, 0]} />
                                </BarChart>
                              </ResponsiveContainer>
                            </div>
                          </div>
                        </CardContent>
                      </Card>
                    </div>

                    {/* Follow-up Effectiveness + Voice vs Text Quality + Review Edits + Experience Rating */}
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                      <Card className="bg-white border-0 shadow-sm rounded-2xl">
                        <CardHeader className="pb-2">
                          <CardTitle className="text-sm font-medium text-brand-blue">Follow-up Effectiveness</CardTitle>
                        </CardHeader>
                        <CardContent className="space-y-2">
                          <div className="flex justify-between text-xs">
                            <span className="text-brand-blue/50">Vague detected</span>
                            <span className="font-semibold">{analytics.followup_effectiveness.total_vague_detected}</span>
                          </div>
                          <div className="flex justify-between text-xs">
                            <span className="text-brand-blue/50">Follow-ups shown</span>
                            <span className="font-semibold">{analytics.followup_effectiveness.followups_shown}</span>
                          </div>
                          <div className="flex justify-between text-xs">
                            <span className="text-brand-blue/50">Answered</span>
                            <span className="font-semibold text-brand-teal">{analytics.followup_effectiveness.followups_answered}</span>
                          </div>
                          <div className="flex justify-between text-xs">
                            <span className="text-brand-blue/50">Skipped</span>
                            <span className="font-semibold text-brand-red">{analytics.followup_effectiveness.followups_skipped}</span>
                          </div>
                          <div className="pt-1 border-t">
                            <p className="text-xs text-brand-blue/40">Answer rate: <span className="font-semibold text-brand-blue">{(analytics.followup_effectiveness.answer_rate * 100).toFixed(0)}%</span></p>
                          </div>
                        </CardContent>
                      </Card>

                      <Card className="bg-white border-0 shadow-sm rounded-2xl">
                        <CardHeader className="pb-2">
                          <CardTitle className="text-sm font-medium text-brand-blue">Voice vs Text Quality</CardTitle>
                        </CardHeader>
                        <CardContent className="space-y-2">
                          <div className="flex justify-between text-xs">
                            <span className="text-brand-blue/50">Voice vague rate</span>
                            <span className="font-semibold">{(analytics.voice_vs_text_quality.voice_vague_rate * 100).toFixed(0)}%</span>
                          </div>
                          <div className="flex justify-between text-xs">
                            <span className="text-brand-blue/50">Text vague rate</span>
                            <span className="font-semibold">{(analytics.voice_vs_text_quality.text_vague_rate * 100).toFixed(0)}%</span>
                          </div>
                          <div className="flex justify-between text-xs">
                            <span className="text-brand-blue/50">Voice avg length</span>
                            <span className="font-semibold">{analytics.voice_vs_text_quality.voice_avg_length} chars</span>
                          </div>
                          <div className="flex justify-between text-xs">
                            <span className="text-brand-blue/50">Text avg length</span>
                            <span className="font-semibold">{analytics.voice_vs_text_quality.text_avg_length} chars</span>
                          </div>
                        </CardContent>
                      </Card>

                      <Card className="bg-white border-0 shadow-sm rounded-2xl">
                        <CardHeader className="pb-2">
                          <CardTitle className="text-sm font-medium text-brand-blue">Review Page Edits</CardTitle>
                        </CardHeader>
                        <CardContent className="space-y-2">
                          <p className="text-2xl font-bold text-brand-blue">{(analytics.review_edits.edit_rate * 100).toFixed(0)}%</p>
                          <p className="text-xs text-brand-blue/40">of reviewers edited responses</p>
                          <div className="flex justify-between text-xs pt-1">
                            <span className="text-brand-blue/50">Total reviews</span>
                            <span className="font-semibold">{analytics.review_edits.total_reviews}</span>
                          </div>
                          <div className="flex justify-between text-xs">
                            <span className="text-brand-blue/50">With edits</span>
                            <span className="font-semibold">{analytics.review_edits.reviews_with_edits}</span>
                          </div>
                        </CardContent>
                      </Card>

                      <Card className="bg-white border-0 shadow-sm rounded-2xl">
                        <CardHeader className="pb-2">
                          <CardTitle className="text-sm font-medium text-brand-blue">Experience Rating</CardTitle>
                        </CardHeader>
                        <CardContent className="space-y-2">
                          <p className="text-2xl font-bold text-brand-blue">
                            {analytics.experience_rating.avg_rating?.toFixed(1) || "N/A"}<span className="text-sm font-normal text-brand-blue/40">/5</span>
                          </p>
                          <div className="flex gap-1">
                            {["1", "2", "3", "4", "5"].map((k) => (
                              <div key={k} className="flex-1">
                                <div className="bg-brand-blue/10 rounded-sm overflow-hidden" style={{ height: 40 }}>
                                  <div
                                    className="bg-brand-blue rounded-sm w-full"
                                    style={{
                                      height: analytics.experience_rating.total_ratings > 0
                                        ? `${(analytics.experience_rating.distribution[k] / analytics.experience_rating.total_ratings) * 100}%`
                                        : "0%",
                                      marginTop: "auto",
                                    }}
                                  />
                                </div>
                                <p className="text-[10px] text-center text-brand-blue/40 mt-0.5">{k}</p>
                              </div>
                            ))}
                          </div>
                          <p className="text-xs text-brand-blue/40">
                            {analytics.experience_rating.total_ratings} ratings ({(analytics.experience_rating.response_rate * 100).toFixed(0)}% response rate)
                          </p>
                        </CardContent>
                      </Card>
                    </div>
                  </>
                )}
              </>
            )}
          </>
        )}

        {/* Empty state when no survey selected */}
        {!selectedSurvey && !loading && (
          <Card className="bg-white border-0 shadow-sm rounded-2xl">
            <CardContent className="py-16 text-center space-y-3">
              <Calendar className="h-10 w-10 text-brand-blue/20 mx-auto" />
              <p className="text-sm text-brand-blue/40">
                {selectedProgram
                  ? "Select a survey to view its data"
                  : "Select a program type to get started"}
              </p>
            </CardContent>
          </Card>
        )}
      </main>

      {/* ── New Survey Dialog ── */}
      <NewSurveyDialog
        open={showNewProgram}
        onOpenChange={setShowNewProgram}
        onCreated={handleSurveyCreated}
        primaryActionLabel="Open Survey in Editor"
        onPrimaryAction={(cohort) => router.push(`/admin/editor?cohort=${cohort.id}`)}
      />

      {/* ── Delete Responses Confirmation Dialog ── */}
      <Dialog open={showDeleteConfirm} onOpenChange={setShowDeleteConfirm}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle className="text-red-600">Delete All Responses</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-brand-blue/60 py-2">
            This will permanently delete{" "}
            <strong>
              all responses for &ldquo;{selectedSurveyName || "this survey"}&rdquo;
            </strong>
            . This action cannot be undone.
          </p>
          <DialogFooter className="gap-2">
            <Button
              variant="outline"
              onClick={() => setShowDeleteConfirm(false)}
            >
              Cancel
            </Button>
            <Button
              onClick={handleDeleteAllResponses}
              disabled={deleting}
              className="bg-red-600 hover:bg-red-700 text-white gap-2"
            >
              {deleting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
              Delete All
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Extraction Review Dialog (H4) ── */}
      <Dialog open={reviewOpen} onOpenChange={setReviewOpen}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle className="text-brand-blue">Rate Extraction Usefulness</DialogTitle>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <div className="space-y-1">
              <Label className="text-xs">Reviewer (required)</Label>
              <Input
                value={reviewForm.reviewed_by}
                onChange={(e) => setReviewForm((f) => ({ ...f, reviewed_by: e.target.value }))}
                placeholder="e.g. allison"
                className="h-9"
              />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Is the extraction useful?</Label>
              <div className="flex gap-2">
                {[
                  { value: true, label: "Useful" },
                  { value: false, label: "Not useful" },
                  { value: null, label: "Unsure" },
                ].map((opt) => (
                  <Button
                    key={String(opt.value)}
                    size="sm"
                    variant={reviewForm.useful_flag === opt.value ? "default" : "outline"}
                    onClick={() => setReviewForm((f) => ({ ...f, useful_flag: opt.value }))}
                  >
                    {opt.label}
                  </Button>
                ))}
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label className="text-xs">Accuracy (1–5)</Label>
                <div className="flex gap-1">
                  {[1, 2, 3, 4, 5].map((n) => (
                    <Button
                      key={n}
                      size="sm"
                      variant={reviewForm.accuracy_rating === n ? "default" : "outline"}
                      onClick={() => setReviewForm((f) => ({ ...f, accuracy_rating: n }))}
                      className="w-9"
                    >
                      {n}
                    </Button>
                  ))}
                </div>
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Usefulness (1–5)</Label>
                <div className="flex gap-1">
                  {[1, 2, 3, 4, 5].map((n) => (
                    <Button
                      key={n}
                      size="sm"
                      variant={reviewForm.usefulness_rating === n ? "default" : "outline"}
                      onClick={() => setReviewForm((f) => ({ ...f, usefulness_rating: n }))}
                      className="w-9"
                    >
                      {n}
                    </Button>
                  ))}
                </div>
              </div>
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Accuracy notes</Label>
              <textarea
                className="w-full min-h-[60px] rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm"
                value={reviewForm.accuracy_notes}
                onChange={(e) => setReviewForm((f) => ({ ...f, accuracy_notes: e.target.value }))}
                placeholder="What was wrong (if anything)?"
              />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Usefulness notes</Label>
              <textarea
                className="w-full min-h-[60px] rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm"
                value={reviewForm.usefulness_notes}
                onChange={(e) => setReviewForm((f) => ({ ...f, usefulness_notes: e.target.value }))}
                placeholder="Would a program manager act on this?"
              />
            </div>
          </div>
          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => setReviewOpen(false)}>Cancel</Button>
            <Button
              onClick={saveReview}
              disabled={reviewSaving || !reviewForm.reviewed_by.trim()}
              className="bg-brand-blue hover:bg-brand-blue/90"
            >
              {reviewSaving ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : null}
              Save review
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Delete Survey Confirmation Dialog ── */}
      <Dialog open={showDeleteSurveyConfirm} onOpenChange={setShowDeleteSurveyConfirm}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle className="text-red-600">Delete Survey</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-brand-blue/60 py-2">
            This will permanently delete the survey{" "}
            <strong>&ldquo;{selectedSurveyName || "this survey"}&rdquo;</strong>{" "}
            and all its responses, versions, and analytics. This action cannot be undone.
          </p>
          <DialogFooter className="gap-2">
            <Button
              variant="outline"
              onClick={() => setShowDeleteSurveyConfirm(false)}
            >
              Cancel
            </Button>
            <Button
              onClick={handleDeleteSurvey}
              disabled={deletingSurvey}
              className="bg-red-600 hover:bg-red-700 text-white gap-2"
            >
              {deletingSurvey ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
              Delete Survey
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
