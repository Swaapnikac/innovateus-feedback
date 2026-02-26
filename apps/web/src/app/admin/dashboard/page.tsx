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
} from "lucide-react";
import { api, type ExtractionResult } from "@/lib/api";
import { InnovateLogo } from "@/components/InnovateLogo";

interface ResponseItem {
  id: string;
  cohort_id: string;
  created_at: string;
  completed_at: string | null;
  status: string;
  language: string;
  time_to_complete_sec: number | null;
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
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);

  const loadData = useCallback(async () => {
    try {
      const params = {
        cohort_id: selectedCohort || undefined,
        start: startDate || undefined,
        end: endDate || undefined,
      };

      const [metricsData, responsesData] = await Promise.all([
        api.getMetrics(params),
        api.getResponses({ ...params, page, page_size: 10 }),
      ]);

      setMetrics(metricsData);
      setResponses(responsesData);
    } catch {
      router.push("/admin/login");
    } finally {
      setLoading(false);
    }
  }, [selectedCohort, startDate, endDate, page, router]);

  useEffect(() => {
    api.getCohorts().then(setCohorts).catch(() => {});
    loadData();
  }, [loadData]);

  const handleExport = (type: "raw.csv" | "structured.csv" | "summary.pdf" | "summary.pptx") => {
    const url = api.exportUrl(type, {
      cohort_id: selectedCohort || undefined,
      start: startDate || undefined,
      end: endDate || undefined,
    });
    window.open(url, "_blank");
  };

  const handleLogout = () => {
    localStorage.removeItem("admin_token");
    router.push("/admin/login");
  };

  const allThemes: Record<string, number> = {};
  const allBarriers: Record<string, number> = {};
  const successStories: string[] = [];

  responses?.items.forEach((item) => {
    if (item.extraction) {
      item.extraction.top_themes?.forEach((t) => {
        allThemes[t] = (allThemes[t] || 0) + 1;
      });
      item.extraction.barriers?.forEach((b) => {
        allBarriers[b] = (allBarriers[b] || 0) + 1;
      });
      if (item.extraction.success_story_candidate) {
        successStories.push(item.extraction.success_story_candidate);
      }
    }
  });

  const topThemes = Object.entries(allThemes).sort((a, b) => b[1] - a[1]).slice(0, 6);
  const topBarriers = Object.entries(allBarriers).sort((a, b) => b[1] - a[1]).slice(0, 6);

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
        <Button variant="outline" size="sm" onClick={handleLogout} className="rounded-full border-brand-blue/15 text-brand-blue/60 hover:bg-brand-blue/5 gap-2">
          <LogOut className="h-4 w-4" />
          Sign Out
        </Button>
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
              <div className="space-y-1">
                <Label className="text-xs">Start Date</Label>
                <Input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} className="w-40" />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">End Date</Label>
                <Input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} className="w-40" />
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
              <Button variant="outline" size="sm" onClick={() => handleExport("raw.csv")} className="gap-2 rounded-full border-brand-blue/15 text-brand-blue/70">
                <FileSpreadsheet className="h-4 w-4" /> Raw CSV
              </Button>
              <Button variant="outline" size="sm" onClick={() => handleExport("structured.csv")} className="gap-2 rounded-full border-brand-blue/15 text-brand-blue/70">
                <FileSpreadsheet className="h-4 w-4" /> Structured CSV
              </Button>
              <Button variant="outline" size="sm" onClick={() => handleExport("summary.pdf")} className="gap-2 rounded-full border-brand-blue/15 text-brand-blue/70">
                <FileText className="h-4 w-4" /> Summary PDF
              </Button>
              <Button variant="outline" size="sm" onClick={() => handleExport("summary.pptx")} className="gap-2 rounded-full border-brand-blue/15 text-brand-blue/70">
                <Presentation className="h-4 w-4" /> Summary PPTX
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* Responses Table */}
        {responses && (
          <Card className="bg-white border-0 shadow-sm rounded-2xl">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-medium text-brand-blue">
                Responses ({responses.total} total)
              </CardTitle>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Date</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Language</TableHead>
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
                        <TableCell className="text-xs uppercase">{item.language}</TableCell>
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
      </main>
    </div>
  );
}
