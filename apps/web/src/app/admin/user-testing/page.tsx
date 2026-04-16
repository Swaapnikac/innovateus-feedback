"use client";

/**
 * User Testing Analytics Dashboard
 *
 * Soft-launch companion view (Apr 22 – May 5) that maps directly to the six
 * hypotheses H1–H6 and the ten success criteria S1–S10. All numbers are
 * served from a single source of truth: `GET /v1/admin/user-testing-analytics`,
 * which delegates to `app.services.metrics_service.compute_user_testing_metrics`.
 *
 * Sections (match brief §7):
 *   A. Executive summary cards (with S-target badges)
 *   B. Funnel visualization
 *   C. Voice vs text comparison
 *   D. Follow-up effectiveness
 *   E. Survey flow / friction
 *   F. Voice UX
 *   G. Technical health
 *   H. Extraction quality
 *   I. Qualtrics sync
 *   J. Participant feedback
 *   K. Facilitator feedback (admin-entered)
 *   L. Filters (cohort + date range, preserved in the URL)
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  PieChart,
  Pie,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
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
import { Download, Loader2, RefreshCw } from "lucide-react";
import {
  api,
  type FacilitatorFeedbackPayload,
  type UserTestingAnalytics,
} from "@/lib/api";

const COLOR_BLUE = "#2563eb";
const COLOR_TEAL = "#0d9488";
const COLOR_AMBER = "#d97706";
const COLOR_RED = "#dc2626";
const COLOR_GRAY = "#6b7280";
const COLOR_GREEN = "#16a34a";

function pct(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return `${(v * 100).toFixed(1)}%`;
}

function num(v: number | null | undefined, digits = 0): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return digits ? v.toFixed(digits) : Math.round(v).toString();
}

function secs(v: number | null | undefined): string {
  if (!v) return "—";
  if (v < 60) return `${v.toFixed(0)}s`;
  const m = Math.floor(v / 60);
  const s = Math.round(v - m * 60);
  return `${m}m ${s}s`;
}

interface CardTarget {
  label: string;
  value: string;
  target?: string;
  meets?: boolean;
  hint?: string;
}

function TargetCard({ t }: { t: CardTarget }) {
  return (
    <Card className="border-brand-blue/10">
      <CardContent className="p-4 space-y-1">
        <div className="flex items-center justify-between gap-2">
          <p className="text-xs uppercase text-muted-foreground tracking-wide">{t.label}</p>
          {t.meets !== undefined && (
            <Badge
              variant="outline"
              className={
                t.meets
                  ? "border-green-500 text-green-700 bg-green-50"
                  : "border-amber-500 text-amber-700 bg-amber-50"
              }
            >
              {t.meets ? "On target" : "Below target"}
            </Badge>
          )}
        </div>
        <p className="text-2xl font-semibold text-brand-blue">{t.value}</p>
        {t.target && (
          <p className="text-xs text-muted-foreground">Target: {t.target}</p>
        )}
        {t.hint && <p className="text-xs text-muted-foreground">{t.hint}</p>}
      </CardContent>
    </Card>
  );
}

function HypothesisCard({
  id,
  label,
  summary,
  totals,
}: {
  id: string;
  label: string;
  summary: string;
  totals: { true: number; false: number; null: number };
}) {
  const total = totals.true + totals.false + totals.null;
  const pctSupport = total ? (totals.true / total) * 100 : 0;
  return (
    <Card className="border-brand-blue/10">
      <CardContent className="p-4 space-y-2">
        <div className="flex items-center justify-between">
          <p className="text-sm font-semibold">{id.toUpperCase()}</p>
          <Badge variant="outline" className="text-xs">
            {total} eligible
          </Badge>
        </div>
        <p className="text-xs text-muted-foreground">{label}</p>
        <p className="text-xs text-muted-foreground">{summary}</p>
        <div className="h-2 w-full rounded bg-muted overflow-hidden">
          <div
            className="h-full bg-green-500"
            style={{ width: `${pctSupport}%` }}
          />
        </div>
        <div className="flex items-center justify-between text-xs">
          <span className="text-green-700">Supports: {totals.true}</span>
          <span className="text-amber-700">Against: {totals.false}</span>
          <span className="text-muted-foreground">N/A: {totals.null}</span>
        </div>
      </CardContent>
    </Card>
  );
}

export default function UserTestingAnalyticsPage() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [analytics, setAnalytics] = useState<UserTestingAnalytics | null>(null);
  const [cohorts, setCohorts] = useState<
    Array<{ id: string; name: string; course_name: string }>
  >([]);
  const [error, setError] = useState<string | null>(null);

  const cohortId = searchParams.get("cohort_id") || "";
  const start = searchParams.get("start") || "";
  const end = searchParams.get("end") || "";

  const updateQuery = useCallback(
    (patch: Record<string, string>) => {
      const params = new URLSearchParams(searchParams.toString());
      for (const [k, v] of Object.entries(patch)) {
        if (v) params.set(k, v);
        else params.delete(k);
      }
      router.replace(`/admin/user-testing?${params.toString()}`);
    },
    [router, searchParams],
  );

  const load = useCallback(async () => {
    try {
      const [cohortsData, analyticsData] = await Promise.all([
        api.getCohorts(),
        api.getUserTestingAnalytics({
          cohort_id: cohortId || undefined,
          start: start || undefined,
          end: end || undefined,
        }),
      ]);
      setCohorts(cohortsData.map((c) => ({ id: c.id, name: c.name, course_name: c.course_name })));
      setAnalytics(analyticsData);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [cohortId, start, end]);

  useEffect(() => {
    if (typeof window !== "undefined") {
      const token = localStorage.getItem("admin_token");
      if (!token) {
        router.replace("/admin/login");
        return;
      }
    }
    setLoading(true);
    void load();
  }, [load, router]);

  const targets = analytics?.targets;
  const exec = analytics?.executive;

  const executiveCards: CardTarget[] = useMemo(() => {
    if (!analytics || !exec || !targets) return [];
    return [
      {
        label: "Completion rate (S1)",
        value: pct(exec.completion_rate),
        target: pct(targets["completion_rate"]),
        meets: exec.completion_rate >= targets["completion_rate"],
      },
      {
        label: "Voice adoption (S2)",
        value: pct(exec.voice_adoption_rate),
        target: pct(targets["voice_adoption_rate"]),
        meets: exec.voice_adoption_rate >= targets["voice_adoption_rate"],
      },
      {
        label: "Post-FU vagueness (S3)",
        value: pct(analytics.followup_effectiveness.post_followup_vagueness_rate),
        target: `≤ ${pct(targets["post_followup_vagueness_rate_max"])}`,
        meets:
          analytics.followup_effectiveness.post_followup_vagueness_rate <=
          targets["post_followup_vagueness_rate_max"],
      },
      {
        label: "Avg voice word count (S4)",
        value: num(analytics.voice_vs_text.avg_voice_word_count, 1),
        target: `≥ ${targets["avg_voice_word_count_min"]}`,
        meets:
          (analytics.voice_vs_text.avg_voice_word_count ?? 0) >=
          (targets["avg_voice_word_count_min"] || 0),
      },
      {
        label: "Extraction usefulness (S5)",
        value: pct(analytics.extraction_quality.extraction_usefulness_rate),
        target: pct(targets["extraction_usefulness_rate_min"]),
        meets:
          analytics.extraction_quality.extraction_usefulness_rate >=
          targets["extraction_usefulness_rate_min"],
        hint: `${analytics.extraction_quality.reviews_with_useful_flag} rated / ${analytics.extraction_quality.extractions_total} extractions`,
      },
      {
        label: "Avg time to complete (S6)",
        value: secs(exec.avg_time_to_complete_sec),
        target: `≤ ${secs(targets["avg_time_to_complete_max_sec"])}`,
        meets:
          !!exec.avg_time_to_complete_sec &&
          exec.avg_time_to_complete_sec <= targets["avg_time_to_complete_max_sec"],
      },
      {
        label: "Qualtrics sync (S8)",
        value: pct(exec.qualtrics_sync_success_rate),
        target: pct(targets["qualtrics_sync_success_rate_min"]),
        meets:
          exec.qualtrics_sync_success_rate >=
          targets["qualtrics_sync_success_rate_min"],
      },
      {
        label: "Voice conv. completion (S10)",
        value: pct(analytics.voice_ux.voice_conversation_completion_rate),
        target: pct(targets["voice_conversation_completion_rate_min"]),
        meets:
          analytics.voice_ux.voice_conversation_completion_rate >=
          targets["voice_conversation_completion_rate_min"],
        hint: `${analytics.voice_ux.voice_conversation_completed_count} of ${analytics.voice_ux.started_in_voice_count} voice starters`,
      },
      {
        label: "Follow-up engagement",
        value: pct(exec.follow_up_engagement_rate),
        hint: `${analytics.followup_effectiveness.followups_answered_total} / ${analytics.followup_effectiveness.followups_shown_total}`,
      },
      {
        label: "Critical errors (S7)",
        value: num(exec.critical_error_count),
        target: "0",
        meets: exec.critical_error_count === 0,
      },
    ];
  }, [analytics, exec, targets]);

  const voiceTextData = useMemo(() => {
    if (!analytics) return [];
    return [
      {
        label: "Voice",
        avg_word_count: analytics.voice_vs_text.avg_voice_word_count ?? 0,
        vague_rate: analytics.voice_vs_text.voice_vague_rate * 100,
        count: analytics.voice_vs_text.voice_open_answer_count,
      },
      {
        label: "Text",
        avg_word_count: analytics.voice_vs_text.avg_text_word_count ?? 0,
        vague_rate: analytics.voice_vs_text.text_vague_rate * 100,
        count: analytics.voice_vs_text.text_open_answer_count,
      },
    ];
  }, [analytics]);

  const followupData = useMemo(() => {
    if (!analytics) return [];
    const fe = analytics.followup_effectiveness;
    return [
      { stage: "Initially vague", count: fe.initial_vague_count },
      { stage: "Still vague after FU", count: fe.vague_after_followups_count },
      { stage: "Improved by FU", count: fe.specificity_improvement_count },
    ];
  }, [analytics]);

  const funnelData = useMemo(() => {
    if (!analytics) return [];
    const firstCount = analytics.funnel[0]?.count || 1;
    return analytics.funnel.map((f, i) => ({
      stage: f.stage.replace("_", " "),
      count: f.count,
      pct: (f.count / firstCount) * 100,
      drop: i > 0 ? Math.max(0, analytics.funnel[i - 1].count - f.count) : 0,
    }));
  }, [analytics]);

  if (loading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-white via-brand-blue/5 to-brand-teal/5 flex items-center justify-center">
        <div className="flex items-center gap-2 text-brand-blue">
          <Loader2 className="h-4 w-4 animate-spin" /> Loading user-testing analytics…
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-white via-brand-blue/5 to-brand-teal/5 p-8">
        <Card className="max-w-xl mx-auto border-red-300">
          <CardContent className="p-6 space-y-2">
            <p className="font-semibold text-red-700">Failed to load analytics</p>
            <p className="text-sm text-muted-foreground">{error}</p>
            <Button
              onClick={() => {
                setLoading(true);
                void load();
              }}
              variant="outline"
              size="sm"
            >
              <RefreshCw className="h-4 w-4 mr-1" /> Retry
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (!analytics) return null;

  return (
    <div className="min-h-screen bg-gradient-to-br from-white via-brand-blue/5 to-brand-teal/5">
      <div className="max-w-7xl mx-auto p-6 space-y-8">
        {/* Header + filters (L) */}
        <div className="space-y-3">
          <div className="flex items-start justify-between gap-4 flex-wrap">
            <div>
              <h1 className="text-2xl font-bold text-brand-blue">
                User Testing Analytics
              </h1>
              <p className="text-sm text-muted-foreground">
                Soft launch dashboard — aligned with hypotheses H1–H6 and
                success criteria S1–S10. Last refreshed{" "}
                {new Date(analytics.generated_at).toLocaleString()}.
              </p>
            </div>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  setRefreshing(true);
                  void load();
                }}
                disabled={refreshing}
              >
                <RefreshCw className={`h-4 w-4 mr-1 ${refreshing ? "animate-spin" : ""}`} />
                Refresh
              </Button>
              <a
                href={api.exportUrl("user-testing.csv", {
                  cohort_id: cohortId || undefined,
                  start: start || undefined,
                  end: end || undefined,
                })}
                target="_blank"
                rel="noreferrer"
              >
                <Button variant="outline" size="sm">
                  <Download className="h-4 w-4 mr-1" /> User-testing CSV
                </Button>
              </a>
              <Button
                variant="outline"
                size="sm"
                onClick={() => router.push("/admin/dashboard")}
              >
                Back to main dashboard
              </Button>
            </div>
          </div>

          <Card className="border-brand-blue/10">
            <CardContent className="p-4 flex flex-wrap items-end gap-4">
              <div className="space-y-1 min-w-[220px]">
                <Label className="text-xs">Cohort / Survey</Label>
                <Select
                  value={cohortId || "all"}
                  onValueChange={(v) => updateQuery({ cohort_id: v === "all" ? "" : v })}
                >
                  <SelectTrigger className="h-9">
                    <SelectValue placeholder="All cohorts" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All cohorts</SelectItem>
                    {cohorts.map((c) => (
                      <SelectItem key={c.id} value={c.id}>
                        {c.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Start</Label>
                <Input
                  type="date"
                  value={start}
                  onChange={(e) => updateQuery({ start: e.target.value })}
                  className="h-9"
                />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">End</Label>
                <Input
                  type="date"
                  value={end}
                  onChange={(e) => updateQuery({ end: e.target.value })}
                  className="h-9"
                />
              </div>
              <div className="text-xs text-muted-foreground ml-auto">
                {analytics.totals.total_submissions} submissions ·{" "}
                {analytics.totals.completed} completed · {analytics.totals.abandoned} abandoned · {analytics.totals.in_progress} in-progress
              </div>
            </CardContent>
          </Card>
        </div>

        {/* A. Executive summary */}
        <section className="space-y-3">
          <h2 className="text-lg font-semibold text-brand-blue">A. Executive summary</h2>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
            {executiveCards.map((c) => (
              <TargetCard key={c.label} t={c} />
            ))}
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-6 gap-3">
            {(["h1", "h2", "h3", "h4", "h5", "h6"] as const).map((h) => (
              <HypothesisCard
                key={h}
                id={h}
                label={
                  {
                    h1: "Voice produces more detailed feedback",
                    h2: "Follow-ups improve response quality",
                    h3: "Participants complete without confusion",
                    h4: "Extracted insights are useful",
                    h5: "Voice feels natural, not robotic",
                    h6: "Gov devices/networks can run the tool",
                  }[h]
                }
                summary={
                  {
                    h1: "Voice word count > text (per submission)",
                    h2: "≥1 follow-up improved specificity",
                    h3: "Submission marked completed",
                    h4: "Reviewer flagged extraction as useful",
                    h5: "Started in voice AND finished in voice",
                    h6: "No critical errors, no mic failures",
                  }[h]
                }
                totals={analytics.hypothesis_totals[h]}
              />
            ))}
          </div>
        </section>

        {/* B. Funnel */}
        <section className="space-y-3">
          <h2 className="text-lg font-semibold text-brand-blue">B. Submission funnel</h2>
          <Card>
            <CardContent className="p-4">
              <ResponsiveContainer width="100%" height={260}>
                <BarChart data={funnelData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="stage" />
                  <YAxis />
                  <Tooltip />
                  <Bar dataKey="count" fill={COLOR_BLUE} name="Count" />
                </BarChart>
              </ResponsiveContainer>
              <Table className="mt-4">
                <TableHeader>
                  <TableRow>
                    <TableHead>Stage</TableHead>
                    <TableHead className="text-right">Count</TableHead>
                    <TableHead className="text-right">% of opened</TableHead>
                    <TableHead className="text-right">Drop from prev</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {funnelData.map((f) => (
                    <TableRow key={f.stage}>
                      <TableCell className="capitalize">{f.stage}</TableCell>
                      <TableCell className="text-right">{f.count}</TableCell>
                      <TableCell className="text-right">{f.pct.toFixed(1)}%</TableCell>
                      <TableCell className="text-right">{f.drop}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </section>

        {/* C. Voice vs text */}
        <section className="space-y-3">
          <h2 className="text-lg font-semibold text-brand-blue">C. Voice vs text</h2>
          <div className="grid md:grid-cols-2 gap-4">
            <Card>
              <CardHeader className="pb-2"><CardTitle className="text-sm">Average word count</CardTitle></CardHeader>
              <CardContent className="p-4">
                <ResponsiveContainer width="100%" height={240}>
                  <BarChart data={voiceTextData}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="label" />
                    <YAxis />
                    <Tooltip />
                    <Bar dataKey="avg_word_count" fill={COLOR_TEAL} name="Avg words" />
                  </BarChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2"><CardTitle className="text-sm">Vagueness rate</CardTitle></CardHeader>
              <CardContent className="p-4">
                <ResponsiveContainer width="100%" height={240}>
                  <BarChart data={voiceTextData}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="label" />
                    <YAxis unit="%" />
                    <Tooltip formatter={(v: unknown) => (typeof v === "number" ? `${v.toFixed(1)}%` : String(v))} />
                    <Bar dataKey="vague_rate" fill={COLOR_AMBER} name="Vague %" />
                  </BarChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          </div>
          <Card>
            <CardContent className="p-4 text-sm">
              Mode-switch rate:{" "}
              <span className="font-semibold">
                {pct(analytics.voice_vs_text.mode_switch_rate)}
              </span>{" "}
              of submissions switched voice ↔ text at least once.
            </CardContent>
          </Card>
        </section>

        {/* D. Follow-up effectiveness */}
        <section className="space-y-3">
          <h2 className="text-lg font-semibold text-brand-blue">D. Follow-up effectiveness (H2)</h2>
          <div className="grid lg:grid-cols-3 gap-4">
            <Card className="lg:col-span-1">
              <CardHeader className="pb-2"><CardTitle className="text-sm">Vague → specific conversion</CardTitle></CardHeader>
              <CardContent className="p-4">
                <ResponsiveContainer width="100%" height={240}>
                  <BarChart data={followupData}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="stage" />
                    <YAxis />
                    <Tooltip />
                    <Bar dataKey="count" fill={COLOR_TEAL} />
                  </BarChart>
                </ResponsiveContainer>
                <div className="text-xs text-muted-foreground mt-2">
                  Specificity improvement rate:{" "}
                  {pct(analytics.followup_effectiveness.specificity_improvement_rate)}
                </div>
              </CardContent>
            </Card>
            <Card className="lg:col-span-2">
              <CardHeader className="pb-2"><CardTitle className="text-sm">Top follow-up prompts</CardTitle></CardHeader>
              <CardContent className="p-2">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Prompt</TableHead>
                      <TableHead className="text-right">Shown</TableHead>
                      <TableHead className="text-right">Answered</TableHead>
                      <TableHead className="text-right">Improved</TableHead>
                      <TableHead className="text-right">Rate</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {analytics.followup_effectiveness.top_followup_prompts.slice(0, 8).map((p, i) => (
                      <TableRow key={i}>
                        <TableCell className="max-w-[360px] truncate" title={p.prompt}>
                          {p.prompt}
                        </TableCell>
                        <TableCell className="text-right">{p.shown}</TableCell>
                        <TableCell className="text-right">{p.answered}</TableCell>
                        <TableCell className="text-right">{p.improved}</TableCell>
                        <TableCell className="text-right">{pct(p.improvement_rate)}</TableCell>
                      </TableRow>
                    ))}
                    {analytics.followup_effectiveness.top_followup_prompts.length === 0 && (
                      <TableRow><TableCell colSpan={5} className="text-muted-foreground text-center">No follow-up prompts seen yet.</TableCell></TableRow>
                    )}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          </div>
        </section>

        {/* E. Survey friction */}
        <section className="space-y-3">
          <h2 className="text-lg font-semibold text-brand-blue">E. Survey friction</h2>
          <Card>
            <CardContent className="p-4 space-y-4">
              <div className="grid md:grid-cols-2 gap-4">
                <div>
                  <p className="text-sm text-muted-foreground">Average completion time</p>
                  <p className="text-2xl font-semibold text-brand-blue">
                    {secs(analytics.survey_friction.avg_time_to_complete_sec)}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    Median: {secs(analytics.survey_friction.median_time_to_complete_sec)}
                  </p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Abandonment events</p>
                  <p className="text-2xl font-semibold text-amber-700">
                    {analytics.survey_friction.abandonment_by_step.reduce(
                      (acc, a) => acc + a.count,
                      0,
                    )}
                  </p>
                </div>
              </div>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Abandonment stage / question</TableHead>
                    <TableHead className="text-right">Count</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {analytics.survey_friction.abandonment_by_step.map((a) => (
                    <TableRow key={a.question_id}>
                      <TableCell className="font-mono text-xs">{a.question_id}</TableCell>
                      <TableCell className="text-right">{a.count}</TableCell>
                    </TableRow>
                  ))}
                  {analytics.survey_friction.abandonment_by_step.length === 0 && (
                    <TableRow>
                      <TableCell colSpan={2} className="text-center text-muted-foreground">
                        No abandonment events recorded.
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </section>

        {/* F. Voice UX */}
        <section className="space-y-3">
          <h2 className="text-lg font-semibold text-brand-blue">F. Voice UX (H5, H6)</h2>
          <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-3">
            <Card><CardContent className="p-4">
              <p className="text-xs uppercase text-muted-foreground">Voice conv. completion</p>
              <p className="text-2xl font-semibold">{pct(analytics.voice_ux.voice_conversation_completion_rate)}</p>
              <p className="text-xs text-muted-foreground">{analytics.voice_ux.voice_conversation_completed_count} / {analytics.voice_ux.started_in_voice_count}</p>
            </CardContent></Card>
            <Card><CardContent className="p-4">
              <p className="text-xs uppercase text-muted-foreground">Transcript edit rate</p>
              <p className="text-2xl font-semibold">{pct(analytics.voice_ux.transcript_edit_rate)}</p>
              <p className="text-xs text-muted-foreground">Voice answers where user edited the transcript</p>
            </CardContent></Card>
            <Card><CardContent className="p-4">
              <p className="text-xs uppercase text-muted-foreground">Mic permission failures</p>
              <p className="text-2xl font-semibold">{pct(analytics.voice_ux.mic_permission_failure_rate)}</p>
            </CardContent></Card>
            <Card><CardContent className="p-4">
              <p className="text-xs uppercase text-muted-foreground">Mode switch rate</p>
              <p className="text-2xl font-semibold">{pct(analytics.voice_vs_text.mode_switch_rate)}</p>
            </CardContent></Card>
          </div>
          <Card>
            <CardHeader className="pb-2"><CardTitle className="text-sm">Voice session duration distribution</CardTitle></CardHeader>
            <CardContent className="p-4">
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={analytics.voice_ux.voice_duration_distribution}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="bucket" />
                  <YAxis />
                  <Tooltip />
                  <Bar dataKey="count" fill={COLOR_BLUE} />
                </BarChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </section>

        {/* G. Technical health */}
        <section className="space-y-3">
          <h2 className="text-lg font-semibold text-brand-blue">G. Technical health (H6, S7)</h2>
          <div className="grid lg:grid-cols-3 gap-3">
            <Card>
              <CardHeader className="pb-2"><CardTitle className="text-sm">Browser breakdown</CardTitle></CardHeader>
              <CardContent className="p-4">
                <ResponsiveContainer width="100%" height={220}>
                  <PieChart>
                    <Tooltip />
                    <Legend />
                    <Pie
                      data={analytics.technical_health.browser_breakdown}
                      dataKey="count"
                      nameKey="label"
                      outerRadius={70}
                    >
                      {analytics.technical_health.browser_breakdown.map((_, i) => (
                        <Cell
                          key={i}
                          fill={[COLOR_BLUE, COLOR_TEAL, COLOR_AMBER, COLOR_RED, COLOR_GRAY, COLOR_GREEN][i % 6]}
                        />
                      ))}
                    </Pie>
                  </PieChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2"><CardTitle className="text-sm">Device type</CardTitle></CardHeader>
              <CardContent className="p-4">
                <ResponsiveContainer width="100%" height={220}>
                  <PieChart>
                    <Tooltip />
                    <Legend />
                    <Pie
                      data={analytics.technical_health.device_breakdown}
                      dataKey="count"
                      nameKey="label"
                      outerRadius={70}
                    >
                      {analytics.technical_health.device_breakdown.map((_, i) => (
                        <Cell
                          key={i}
                          fill={[COLOR_TEAL, COLOR_BLUE, COLOR_AMBER, COLOR_RED, COLOR_GRAY, COLOR_GREEN][i % 6]}
                        />
                      ))}
                    </Pie>
                  </PieChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2"><CardTitle className="text-sm">Reliability summary</CardTitle></CardHeader>
              <CardContent className="p-4 space-y-2 text-sm">
                <div className="flex justify-between"><span className="text-muted-foreground">Avg API latency</span><span>{num(analytics.technical_health.avg_api_latency_ms)} ms</span></div>
                <div className="flex justify-between"><span className="text-muted-foreground">Max API latency</span><span>{num(analytics.technical_health.max_api_latency_ms)} ms</span></div>
                <div className="flex justify-between"><span className="text-muted-foreground">Timeouts</span><span>{analytics.technical_health.total_timeouts}</span></div>
                <div className="flex justify-between"><span className="text-muted-foreground">API failures</span><span>{analytics.technical_health.total_api_failures}</span></div>
                <div className="flex justify-between"><span className="text-muted-foreground">Client errors</span><span>{analytics.technical_health.client_error_count}</span></div>
                <div className="flex justify-between"><span className="text-muted-foreground">Critical errors</span><span className={analytics.technical_health.critical_error_count > 0 ? "text-red-600 font-semibold" : ""}>{analytics.technical_health.critical_error_count}</span></div>
                <div className="flex justify-between"><span className="text-muted-foreground">Critical error rate</span><span>{pct(analytics.technical_health.critical_error_rate)}</span></div>
              </CardContent>
            </Card>
          </div>
          <Card>
            <CardHeader className="pb-2"><CardTitle className="text-sm">Critical error rate by browser</CardTitle></CardHeader>
            <CardContent className="p-4">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Browser</TableHead>
                    <TableHead className="text-right">Critical error rate</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {Object.entries(analytics.technical_health.browser_error_rate).map(([browser, rate]) => (
                    <TableRow key={browser}>
                      <TableCell>{browser}</TableCell>
                      <TableCell className="text-right">{pct(rate)}</TableCell>
                    </TableRow>
                  ))}
                  {Object.keys(analytics.technical_health.browser_error_rate).length === 0 && (
                    <TableRow><TableCell colSpan={2} className="text-muted-foreground text-center">No browser data yet.</TableCell></TableRow>
                  )}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </section>

        {/* H. Extraction quality */}
        <section className="space-y-3">
          <h2 className="text-lg font-semibold text-brand-blue">H. Extraction quality (H4)</h2>
          <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-3">
            <Card><CardContent className="p-4">
              <p className="text-xs uppercase text-muted-foreground">Extraction success</p>
              <p className="text-2xl font-semibold">{pct(analytics.extraction_quality.extraction_success_rate)}</p>
              <p className="text-xs text-muted-foreground">{analytics.extraction_quality.extractions_total} extractions</p>
            </CardContent></Card>
            <Card><CardContent className="p-4">
              <p className="text-xs uppercase text-muted-foreground">Review coverage</p>
              <p className="text-2xl font-semibold">{pct(analytics.extraction_quality.review_coverage_rate)}</p>
              <p className="text-xs text-muted-foreground">{analytics.extraction_quality.reviews_total} reviewed</p>
            </CardContent></Card>
            <Card><CardContent className="p-4">
              <p className="text-xs uppercase text-muted-foreground">Useful rate</p>
              <p className="text-2xl font-semibold">{pct(analytics.extraction_quality.extraction_usefulness_rate)}</p>
            </CardContent></Card>
            <Card><CardContent className="p-4">
              <p className="text-xs uppercase text-muted-foreground">Avg ratings</p>
              <p className="text-sm">Accuracy: <span className="font-semibold">{num(analytics.extraction_quality.avg_accuracy_rating, 2)}</span></p>
              <p className="text-sm">Usefulness: <span className="font-semibold">{num(analytics.extraction_quality.avg_usefulness_rating, 2)}</span></p>
            </CardContent></Card>
          </div>
        </section>

        {/* I. Qualtrics sync */}
        <section className="space-y-3">
          <h2 className="text-lg font-semibold text-brand-blue">I. Qualtrics sync (S8)</h2>
          <div className="grid md:grid-cols-4 gap-3">
            <Card><CardContent className="p-4">
              <p className="text-xs uppercase text-muted-foreground">Attempted</p>
              <p className="text-2xl font-semibold">{analytics.qualtrics_sync.attempted_count}</p>
            </CardContent></Card>
            <Card><CardContent className="p-4">
              <p className="text-xs uppercase text-muted-foreground">Succeeded</p>
              <p className="text-2xl font-semibold text-green-700">{analytics.qualtrics_sync.succeeded_count}</p>
            </CardContent></Card>
            <Card><CardContent className="p-4">
              <p className="text-xs uppercase text-muted-foreground">Failed</p>
              <p className={`text-2xl font-semibold ${analytics.qualtrics_sync.failed_count > 0 ? "text-red-700" : ""}`}>{analytics.qualtrics_sync.failed_count}</p>
            </CardContent></Card>
            <Card><CardContent className="p-4">
              <p className="text-xs uppercase text-muted-foreground">Avg latency</p>
              <p className="text-2xl font-semibold">{num(analytics.qualtrics_sync.avg_latency_ms)} ms</p>
            </CardContent></Card>
          </div>
          <Card>
            <CardHeader className="pb-2"><CardTitle className="text-sm">Recent sync failures</CardTitle></CardHeader>
            <CardContent className="p-2">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Submission</TableHead>
                    <TableHead>Last attempt</TableHead>
                    <TableHead className="text-right">Attempts</TableHead>
                    <TableHead>Error</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {analytics.qualtrics_sync.recent_failures.map((f) => (
                    <TableRow key={f.submission_id}>
                      <TableCell className="font-mono text-xs">{f.submission_id.slice(0, 8)}…</TableCell>
                      <TableCell className="text-xs">{f.last_attempt_at ? new Date(f.last_attempt_at).toLocaleString() : "—"}</TableCell>
                      <TableCell className="text-right">{f.attempts}</TableCell>
                      <TableCell className="text-xs text-red-700 max-w-[320px] truncate" title={f.error}>{f.error || "—"}</TableCell>
                    </TableRow>
                  ))}
                  {analytics.qualtrics_sync.recent_failures.length === 0 && (
                    <TableRow><TableCell colSpan={4} className="text-muted-foreground text-center">No sync failures.</TableCell></TableRow>
                  )}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </section>

        {/* J. Participant feedback */}
        <section className="space-y-3">
          <h2 className="text-lg font-semibold text-brand-blue">J. Participant feedback</h2>
          <div className="grid md:grid-cols-4 gap-3">
            <Card><CardContent className="p-4">
              <p className="text-xs uppercase text-muted-foreground">Overall experience</p>
              <p className="text-2xl font-semibold">{num(analytics.participant_feedback.avg_experience_rating, 2)}/5</p>
              <p className="text-xs text-muted-foreground">{analytics.participant_feedback.experience_rating_count} ratings</p>
            </CardContent></Card>
            <Card><CardContent className="p-4">
              <p className="text-xs uppercase text-muted-foreground">Voice experience</p>
              <p className="text-2xl font-semibold">{num(analytics.participant_feedback.avg_voice_experience_rating, 2)}/5</p>
              <p className="text-xs text-muted-foreground">{analytics.participant_feedback.voice_experience_rating_count} ratings</p>
            </CardContent></Card>
            <Card><CardContent className="p-4">
              <p className="text-xs uppercase text-muted-foreground">Would use again</p>
              <p className="text-2xl font-semibold">
                {analytics.participant_feedback.would_use_again_total === 0
                  ? "—"
                  : pct(analytics.participant_feedback.would_use_again_yes / analytics.participant_feedback.would_use_again_total)}
              </p>
              <p className="text-xs text-muted-foreground">{analytics.participant_feedback.would_use_again_yes} / {analytics.participant_feedback.would_use_again_total}</p>
            </CardContent></Card>
            <Card><CardContent className="p-4">
              <p className="text-xs uppercase text-muted-foreground">Confusion / issues</p>
              <p className="text-sm">Confused: <span className="font-semibold">{analytics.participant_feedback.confusion_flag_count}</span></p>
              <p className="text-sm">Reported issues: <span className="font-semibold">{analytics.participant_feedback.reported_issue_count}</span></p>
            </CardContent></Card>
          </div>
        </section>

        {/* K. Facilitator feedback */}
        <FacilitatorSection
          cohorts={cohorts}
          current={cohortId}
          facilitatorRows={analytics.facilitator_feedback}
          onSaved={() => {
            setRefreshing(true);
            void load();
          }}
        />
      </div>
    </div>
  );
}

function FacilitatorSection({
  cohorts,
  current,
  facilitatorRows,
  onSaved,
}: {
  cohorts: Array<{ id: string; name: string }>;
  current: string;
  facilitatorRows: UserTestingAnalytics["facilitator_feedback"];
  onSaved: () => void;
}) {
  const [selectedCohort, setSelectedCohort] = useState(current || cohorts[0]?.id || "");
  const [form, setForm] = useState<Partial<FacilitatorFeedbackPayload>>({});
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");

  const loadForm = useCallback(async (cid: string) => {
    if (!cid) return;
    try {
      const payload = await api.getFacilitatorFeedback(cid);
      setForm(payload);
    } catch {
      setForm({});
    }
  }, []);

  useEffect(() => {
    void loadForm(selectedCohort);
  }, [selectedCohort, loadForm]);

  const save = async () => {
    if (!selectedCohort) return;
    setSaving(true);
    setMessage("");
    try {
      await api.saveFacilitatorFeedback(selectedCohort, form);
      setMessage("Saved.");
      onSaved();
    } catch (e) {
      setMessage(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="space-y-3">
      <h2 className="text-lg font-semibold text-brand-blue">K. Facilitator feedback</h2>
      <div className="grid lg:grid-cols-2 gap-4">
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm">Capture facilitator feedback (S9)</CardTitle></CardHeader>
          <CardContent className="p-4 space-y-3">
            <div className="space-y-1">
              <Label className="text-xs">Cohort</Label>
              <Select value={selectedCohort} onValueChange={setSelectedCohort}>
                <SelectTrigger className="h-9"><SelectValue placeholder="Select cohort" /></SelectTrigger>
                <SelectContent>
                  {cohorts.map((c) => (
                    <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div className="space-y-1">
                <Label className="text-xs">Facilitator name</Label>
                <Input
                  className="h-9"
                  value={form.facilitator_name || ""}
                  onChange={(e) => setForm({ ...form, facilitator_name: e.target.value })}
                />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Facilitator email</Label>
                <Input
                  className="h-9"
                  value={form.facilitator_email || ""}
                  onChange={(e) => setForm({ ...form, facilitator_email: e.target.value })}
                />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Source channel</Label>
                <Input
                  className="h-9"
                  value={form.source_channel || ""}
                  onChange={(e) => setForm({ ...form, source_channel: e.target.value })}
                  placeholder="e.g. email, workshop_link, qr"
                />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Launch phase</Label>
                <Input
                  className="h-9"
                  value={form.launch_phase || ""}
                  onChange={(e) => setForm({ ...form, launch_phase: e.target.value })}
                  placeholder="soft_launch"
                />
              </div>
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Feedback text</Label>
              <Textarea
                rows={4}
                value={form.facilitator_feedback_text || ""}
                onChange={(e) => setForm({ ...form, facilitator_feedback_text: e.target.value })}
              />
            </div>
            <div className="flex gap-3">
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={!!form.facilitator_reported_issue_flag}
                  onChange={(e) => setForm({ ...form, facilitator_reported_issue_flag: e.target.checked })}
                />
                Facilitator reported an issue
              </label>
              <div className="space-y-1 flex-1">
                <Label className="text-xs">Issue type</Label>
                <Input
                  className="h-9"
                  value={form.facilitator_issue_type || ""}
                  onChange={(e) => setForm({ ...form, facilitator_issue_type: e.target.value })}
                />
              </div>
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Issue notes</Label>
              <Textarea
                rows={2}
                value={form.facilitator_issue_notes || ""}
                onChange={(e) => setForm({ ...form, facilitator_issue_notes: e.target.value })}
              />
            </div>
            <div className="flex items-center gap-2">
              <Button onClick={save} disabled={saving || !selectedCohort}>
                {saving && <Loader2 className="h-4 w-4 mr-1 animate-spin" />} Save
              </Button>
              {message && <p className="text-xs text-muted-foreground">{message}</p>}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm">All facilitator notes</CardTitle></CardHeader>
          <CardContent className="p-2">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Cohort</TableHead>
                  <TableHead>Facilitator</TableHead>
                  <TableHead>Phase</TableHead>
                  <TableHead>Issue?</TableHead>
                  <TableHead>Feedback</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {facilitatorRows.map((r) => (
                  <TableRow key={r.cohort_id}>
                    <TableCell>{r.cohort_name}</TableCell>
                    <TableCell>{r.facilitator_name || "—"}</TableCell>
                    <TableCell>{r.launch_phase || "—"}</TableCell>
                    <TableCell>
                      {r.reported_issue ? (
                        <span className="text-amber-700 font-semibold">{r.issue_type || "Yes"}</span>
                      ) : (
                        "No"
                      )}
                    </TableCell>
                    <TableCell className="max-w-[360px] whitespace-pre-wrap text-xs">{r.feedback_text}</TableCell>
                  </TableRow>
                ))}
                {facilitatorRows.length === 0 && (
                  <TableRow><TableCell colSpan={5} className="text-center text-muted-foreground">No facilitator notes yet.</TableCell></TableRow>
                )}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      </div>
    </section>
  );
}
