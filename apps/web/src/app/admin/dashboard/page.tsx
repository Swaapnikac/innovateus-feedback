"use client";

import { useState, useEffect, useCallback } from "react";
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
  Link2,
  Trash2,
  GitBranch,
} from "lucide-react";
import { api, type ExtractionResult } from "@/lib/api";
import { InnovateLogo } from "@/components/InnovateLogo";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from "recharts";

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

export default function DashboardPage() {
  const router = useRouter();
  const [metrics, setMetrics] = useState<MetricsData | null>(null);
  const [responses, setResponses] = useState<ResponsesData | null>(null);
  const [cohorts, setCohorts] = useState<
    Array<{ id: string; name: string; course_name: string }>
  >([]);
  const [selectedCohort, setSelectedCohort] = useState<string>("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [versionFilter, setVersionFilter] = useState<string>("");
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [showNewProgram, setShowNewProgram] = useState(false);
  const [newProgramName, setNewProgramName] = useState("");
  const [newCourseName, setNewCourseName] = useState("");
  const [creating, setCreating] = useState(false);
  const [createdCohortId, setCreatedCohortId] = useState<string | null>(null);
  const [linkCopied, setLinkCopied] = useState(false);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [analytics, setAnalytics] = useState<any>(null);

  const loadData = useCallback(async () => {
    try {
      const cohortId = selectedCohort && selectedCohort !== "all" ? selectedCohort : undefined;
      const params = {
        cohort_id: cohortId,
        start: startDate || undefined,
        end: endDate || undefined,
        survey_version: versionFilter || undefined,
      };

      const [metricsData, responsesData, analyticsData] = await Promise.all([
        api.getMetrics(params),
        api.getResponses({ ...params, page, page_size: 10 }),
        api.getAnalytics({ cohort_id: cohortId, start: startDate || undefined, end: endDate || undefined }).catch(() => ({
          funnel: { page_views_landing: 0, page_views_consent: 0, survey_starts: 0, survey_in_progress: 0, survey_completed: 0, dropout_rate: 0 },
          per_question_dropout: [],
          voice_vs_text: { total_open_answers: 0, voice_count: 0, text_count: 0, voice_percentage: 0, per_question: [] },
          followup_effectiveness: { total_vague_detected: 0, followups_shown: 0, followups_answered: 0, followups_skipped: 0, answer_rate: 0 },
          voice_vs_text_quality: { voice_vague_rate: 0, text_vague_rate: 0, voice_avg_length: 0, text_avg_length: 0 },
          review_edits: { total_reviews: 0, reviews_with_edits: 0, edit_rate: 0, edits_per_question: [] },
          experience_rating: { total_ratings: 0, avg_rating: null, distribution: { "1": 0, "2": 0, "3": 0, "4": 0, "5": 0 }, response_rate: 0 },
          time_metrics: { avg_total_sec: null, median_total_sec: null, total_question_answers: 0 },
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
  }, [selectedCohort, startDate, endDate, versionFilter, page, router]);

  useEffect(() => {
    api.getCohorts().then(setCohorts).catch(() => {});
    loadData();
  }, [loadData]);

  const handleExport = async (type: "raw.csv" | "structured.csv" | "summary.pdf" | "summary.pptx") => {
    const exportCohortId = selectedCohort && selectedCohort !== "all" ? selectedCohort : undefined;
    const url = api.exportUrl(type, {
      cohort_id: exportCohortId,
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

  const handleCreateProgram = async () => {
    if (!newProgramName.trim() || !newCourseName.trim()) return;
    setCreating(true);
    try {
      const created = await api.createCohort(newProgramName.trim(), newCourseName.trim());
      setCohorts((prev) => [created, ...prev]);
      setSelectedCohort(created.id);
      setCreatedCohortId(created.id);
      setNewProgramName("");
      setNewCourseName("");
      loadData();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to create program");
    } finally {
      setCreating(false);
    }
  };

  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const handleDeleteAllResponses = async () => {
    setDeleting(true);
    try {
      const cohortId = selectedCohort && selectedCohort !== "all" ? selectedCohort : undefined;
      await api.deleteAllResponses(cohortId);
      setShowDeleteConfirm(false);
      loadData();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to delete responses");
    } finally {
      setDeleting(false);
    }
  };

  const closeNewProgramDialog = () => {
    setShowNewProgram(false);
    setCreatedCohortId(null);
    setLinkCopied(false);
  };

  // Use analytics data (aggregated across ALL submissions, not just current page)
  const topThemes: [string, number][] = (analytics?.top_themes ?? []).map((t: { theme: string; count: number }) => [t.theme, t.count]);
  const topBarriers: [string, number][] = (analytics?.top_barriers ?? []).map((b: { barrier: string; count: number }) => [b.barrier, b.count]);
  const successStories: string[] = analytics?.success_stories ?? [];

  if (loading) {
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
            New Program
          </Button>
          <Button variant="outline" size="sm" onClick={() => router.push("/admin/pipelines")} className="border-brand-teal/20 text-brand-teal hover:bg-brand-teal/5 gap-2">
            <GitBranch className="h-4 w-4" />
            Pipelines
          </Button>
          <Button variant="outline" size="sm" onClick={() => router.push("/admin/editor/login")} className="border-brand-dark-yellow/20 text-brand-dark-yellow hover:bg-brand-yellow/10 gap-2">
            <Settings className="h-4 w-4" />
            Survey Editor
          </Button>
          <Button variant="outline" size="sm" onClick={handleLogout} className="border-brand-blue/15 text-brand-blue/60 hover:bg-brand-blue/5 gap-2">
            <LogOut className="h-4 w-4" />
            Sign Out
          </Button>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 py-8 space-y-8">
        {/* Filters */}
        <Card className="bg-white border-0 shadow-sm rounded-2xl">
          <CardContent className="pt-6">
            <div className="flex flex-wrap gap-4 items-end">
              <div className="space-y-1">
                <Label className="text-xs font-semibold text-brand-blue/40 uppercase tracking-wider">Cohort</Label>
                <Select value={selectedCohort} onValueChange={setSelectedCohort}>
                  <SelectTrigger className="w-48 rounded-xl">
                    <SelectValue placeholder="All Cohorts" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Cohorts</SelectItem>
                    {cohorts.map((c) => (
                      <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              {selectedCohort && selectedCohort !== "all" && (
                <div className="space-y-1">
                  <Label className="text-xs font-semibold text-brand-blue/40 uppercase tracking-wider">Survey Link</Label>
                  <Button
                    variant="outline"
                    size="sm"
                    className="rounded-xl gap-2 text-xs h-10 w-full"
                    onClick={() => copyLink(selectedCohort)}
                  >
                    <Link2 className="h-3.5 w-3.5" />
                    {linkCopied ? "Copied!" : "Copy Survey Link"}
                  </Button>
                </div>
              )}
              <div className="space-y-1">
                <Label className="text-xs">Start Date</Label>
                <Input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} className="w-40" />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">End Date</Label>
                <Input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} className="w-40" />
              </div>
              <div className="space-y-1">
                <Label className="text-xs font-semibold text-brand-blue/40 uppercase tracking-wider">Version</Label>
                <Input
                  value={versionFilter}
                  onChange={(e) => setVersionFilter(e.target.value)}
                  className="w-28 rounded-xl"
                  placeholder="e.g. v2"
                />
              </div>
              <Button onClick={() => { setPage(1); loadData(); }} className="bg-brand-blue hover:bg-brand-blue/90 rounded-full px-6">
                Apply Filters
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* Metrics */}
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
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {responses.items.map((item) => {
                    const recommend = item.answers.find(
                      (a) => a.question_id === "q1_recommend"
                    );
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
              {/* Per-Question Dropout */}
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

              {/* Voice vs Text */}
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
              {/* Follow-up Effectiveness */}
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

              {/* Voice vs Text Quality */}
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

              {/* Review Edits */}
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

              {/* Experience Rating */}
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
      </main>

      <Dialog open={showNewProgram} onOpenChange={closeNewProgramDialog}>
        <DialogContent className="sm:max-w-md">
          {createdCohortId ? (
            <>
              <DialogHeader>
                <DialogTitle>Program Created</DialogTitle>
              </DialogHeader>
              <div className="space-y-4 py-2">
                <p className="text-sm text-brand-blue/60">
                  Share this link with participants to collect feedback:
                </p>
                <div className="flex items-center gap-2">
                  <Input
                    readOnly
                    value={getSurveyLink(createdCohortId)}
                    className="rounded-xl text-xs font-mono"
                  />
                  <Button
                    size="sm"
                    variant="outline"
                    className="rounded-xl shrink-0 gap-1.5"
                    onClick={() => copyLink(createdCohortId)}
                  >
                    <Copy className="h-3.5 w-3.5" />
                    {linkCopied ? "Copied!" : "Copy"}
                  </Button>
                </div>
                <p className="text-[11px] text-brand-blue/30">
                  You can customize the survey questions in the Survey Editor.
                </p>
              </div>
              <DialogFooter>
                <Button
                  onClick={closeNewProgramDialog}
                  className="bg-brand-blue hover:bg-brand-blue/90"
                >
                  Done
                </Button>
              </DialogFooter>
            </>
          ) : (
            <>
              <DialogHeader>
                <DialogTitle>Create New Program</DialogTitle>
              </DialogHeader>
              <div className="space-y-4 py-2">
                <div className="space-y-1">
                  <Label className="text-xs font-semibold text-brand-blue/40 uppercase tracking-wider">
                    Program Name
                  </Label>
                  <Input
                    placeholder="e.g. Spring 2026 Cohort"
                    value={newProgramName}
                    onChange={(e) => setNewProgramName(e.target.value)}
                    className="rounded-xl"
                  />
                </div>
                <div className="space-y-1">
                  <Label className="text-xs font-semibold text-brand-blue/40 uppercase tracking-wider">
                    Course Name
                  </Label>
                  <Input
                    placeholder="e.g. Introduction to Generative AI"
                    value={newCourseName}
                    onChange={(e) => setNewCourseName(e.target.value)}
                    className="rounded-xl"
                  />
                </div>
              </div>
              <DialogFooter>
                <Button
                  variant="outline"
                  onClick={closeNewProgramDialog}
                  className=""
                >
                  Cancel
                </Button>
                <Button
                  onClick={handleCreateProgram}
                  disabled={creating || !newProgramName.trim() || !newCourseName.trim()}
                  className="bg-brand-blue hover:bg-brand-blue/90 gap-2"
                >
                  {creating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
                  Create
                </Button>
              </DialogFooter>
            </>
          )}
        </DialogContent>
      </Dialog>

      <Dialog open={showDeleteConfirm} onOpenChange={setShowDeleteConfirm}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle className="text-red-600">Delete All Responses</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-brand-blue/60 py-2">
            This will permanently delete{" "}
            <strong>
              {selectedCohort && selectedCohort !== "all"
                ? `all responses for "${cohorts.find((c) => c.id === selectedCohort)?.name || "this program"}"`
                : "all responses across every program"}
            </strong>
            . This action cannot be undone.
          </p>
          <DialogFooter className="gap-2">
            <Button
              variant="outline"
              onClick={() => setShowDeleteConfirm(false)}
              className=""
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
    </div>
  );
}
