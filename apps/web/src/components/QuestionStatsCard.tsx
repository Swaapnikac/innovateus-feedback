"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from "recharts";

interface QuestionStats {
  question_id: string;
  question_type: string;
  question_text: string;
  total_responses: number;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  stats: Record<string, any>;
}

interface QuestionStatsCardProps {
  question: QuestionStats;
}

function typeLabel(t: string): string {
  switch (t) {
    case "rating": return "Rating";
    case "nps": return "NPS";
    case "slider": return "Slider";
    case "mcq": return "Choice";
    case "multi": return "Multi";
    case "dropdown": return "Dropdown";
    case "yesno": return "Yes/No";
    case "matrix": return "Matrix";
    case "ranking": return "Ranking";
    case "open": return "Open";
    case "short_text": return "Short Text";
    case "date": return "Date";
    default: return t;
  }
}

function StatTile({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="bg-brand-light-blue/40 rounded-lg p-3 text-center">
      <p className="text-lg font-bold text-brand-blue">{value}</p>
      <p className="text-[10px] text-brand-blue/40 uppercase tracking-wider mt-0.5">{label}</p>
    </div>
  );
}

export function QuestionStatsCard({ question }: QuestionStatsCardProps) {
  const { stats, question_type, total_responses, question_text, question_id } = question;

  return (
    <Card className="bg-white border-0 shadow-sm rounded-2xl">
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <p className="text-[10px] font-mono text-brand-blue/30 uppercase tracking-wider mb-1">
              {question_id}
            </p>
            <CardTitle className="text-sm text-brand-blue leading-snug line-clamp-2">
              {question_text}
            </CardTitle>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <Badge variant="outline" className="text-[10px] border-brand-blue/15 text-brand-blue/50">
              {typeLabel(question_type)}
            </Badge>
            <Badge variant="secondary" className="text-[10px]">
              {total_responses}
            </Badge>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {total_responses === 0 ? (
          <p className="text-xs text-brand-blue/30 italic py-4 text-center">No responses yet</p>
        ) : (
          <RenderStats type={question_type} stats={stats} />
        )}
      </CardContent>
    </Card>
  );
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function RenderStats({ type, stats }: { type: string; stats: Record<string, any> }) {
  if (type === "nps") {
    const dist = (stats.distribution || {}) as Record<string, number>;
    const data = Array.from({ length: 11 }, (_, i) => ({
      name: String(i),
      value: dist[String(i)] || 0,
    }));
    const npsScore = stats.nps_score ?? 0;
    const total = stats.promoters + stats.passives + stats.detractors;
    return (
      <div className="space-y-3">
        <div className="grid grid-cols-4 gap-2">
          <div className="bg-brand-teal/10 rounded-lg p-3 text-center col-span-1">
            <p className="text-2xl font-bold text-brand-teal">{npsScore}</p>
            <p className="text-[10px] text-brand-blue/40 uppercase tracking-wider mt-0.5">NPS Score</p>
          </div>
          <StatTile label="Promoters" value={`${total ? Math.round((stats.promoters / total) * 100) : 0}%`} />
          <StatTile label="Passives" value={`${total ? Math.round((stats.passives / total) * 100) : 0}%`} />
          <StatTile label="Detractors" value={`${total ? Math.round((stats.detractors / total) * 100) : 0}%`} />
        </div>
        <div className="h-32">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data}>
              <XAxis dataKey="name" tick={{ fontSize: 10 }} />
              <YAxis tick={{ fontSize: 10 }} allowDecimals={false} />
              <Tooltip />
              <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                {data.map((_, i) => (
                  <Cell key={i} fill={i <= 6 ? "#9D0C1B" : i <= 8 ? "#D09006" : "#097261"} fillOpacity={0.85} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    );
  }

  if (type === "rating") {
    const dist = (stats.distribution || {}) as Record<string, number>;
    const data = Object.keys(dist).sort((a, b) => Number(a) - Number(b)).map((k) => ({
      name: k,
      value: dist[k],
    }));
    return (
      <div className="space-y-3">
        <div className="grid grid-cols-2 gap-2">
          <StatTile label="Average" value={stats.avg ?? "—"} />
          <StatTile label="Median" value={stats.median ?? "—"} />
        </div>
        <div className="h-32">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data}>
              <XAxis dataKey="name" tick={{ fontSize: 10 }} />
              <YAxis tick={{ fontSize: 10 }} allowDecimals={false} />
              <Tooltip />
              <Bar dataKey="value" fill="#124D8F" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    );
  }

  if (type === "slider") {
    return (
      <div className="grid grid-cols-4 gap-2">
        <StatTile label="Average" value={stats.avg ?? "—"} />
        <StatTile label="Median" value={stats.median ?? "—"} />
        <StatTile label="Min" value={stats.min ?? "—"} />
        <StatTile label="Max" value={stats.max ?? "—"} />
      </div>
    );
  }

  if (type === "mcq" || type === "dropdown" || type === "yesno") {
    const dist = (stats.distribution || {}) as Record<string, number>;
    const data = Object.entries(dist)
      .sort((a, b) => b[1] - a[1])
      .map(([name, value]) => ({ name, value }));
    return (
      <div className="space-y-2">
        {data.map(({ name, value }) => {
          const total = data.reduce((s, d) => s + d.value, 0);
          const pct = total > 0 ? Math.round((value / total) * 100) : 0;
          const displayName = type === "yesno"
            ? name === "yes" ? "Yes" : name === "no" ? "No" : name
            : name;
          return (
            <div key={name} className="space-y-1">
              <div className="flex justify-between text-xs">
                <span className="text-brand-blue/70 truncate">{displayName}</span>
                <span className="font-semibold text-brand-blue shrink-0 ml-2">
                  {value} ({pct}%)
                </span>
              </div>
              <div className="h-2 bg-brand-blue/10 rounded-full overflow-hidden">
                <div
                  className="h-full bg-brand-blue rounded-full"
                  style={{ width: `${pct}%` }}
                />
              </div>
            </div>
          );
        })}
      </div>
    );
  }

  if (type === "multi") {
    const dist = (stats.distribution || {}) as Record<string, number>;
    const data = Object.entries(dist)
      .sort((a, b) => b[1] - a[1])
      .map(([name, value]) => ({ name, value }));
    const maxVal = Math.max(...data.map((d) => d.value), 1);
    return (
      <div className="space-y-2">
        {data.map(({ name, value }) => (
          <div key={name} className="space-y-1">
            <div className="flex justify-between text-xs">
              <span className="text-brand-blue/70 truncate">{name}</span>
              <span className="font-semibold text-brand-blue shrink-0 ml-2">{value}</span>
            </div>
            <div className="h-2 bg-brand-blue/10 rounded-full overflow-hidden">
              <div
                className="h-full bg-brand-teal rounded-full"
                style={{ width: `${(value / maxVal) * 100}%` }}
              />
            </div>
          </div>
        ))}
      </div>
    );
  }

  if (type === "matrix") {
    const rows: string[] = stats.rows || [];
    const cols: string[] = stats.columns || [];
    const rowDist = (stats.row_distributions || {}) as Record<string, Record<string, number>>;
    const displayRows = rows.length > 0 ? rows : Object.keys(rowDist);
    const displayCols = cols.length > 0 ? cols : Array.from(
      new Set(Object.values(rowDist).flatMap((r) => Object.keys(r)))
    );
    const maxCount = Math.max(
      ...Object.values(rowDist).flatMap((r) => Object.values(r)),
      1
    );
    return (
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-brand-blue/10">
              <th className="text-left py-1.5 px-2 font-normal text-brand-blue/40"></th>
              {displayCols.map((c) => (
                <th key={c} className="text-center py-1.5 px-2 font-normal text-brand-blue/60">
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {displayRows.map((r) => (
              <tr key={r} className="border-b border-brand-blue/5 last:border-0">
                <td className="py-1.5 px-2 text-brand-blue font-medium">{r}</td>
                {displayCols.map((c) => {
                  const count = rowDist[r]?.[c] ?? 0;
                  const intensity = count / maxCount;
                  return (
                    <td
                      key={c}
                      className="text-center py-1.5 px-2 rounded text-brand-blue font-mono"
                      style={{
                        backgroundColor: `rgba(18, 77, 143, ${intensity * 0.35})`,
                      }}
                    >
                      {count || "—"}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  if (type === "ranking") {
    const avgRanks = (stats.average_ranks || {}) as Record<string, number>;
    const data = Object.entries(avgRanks)
      .sort((a, b) => a[1] - b[1])
      .map(([name, rank]) => ({ name, rank }));
    return (
      <div className="space-y-2">
        {data.map(({ name, rank }, i) => (
          <div
            key={name}
            className="flex items-center gap-3 bg-brand-light-blue/40 rounded-lg px-3 py-2"
          >
            <span className="text-xs font-mono text-brand-blue/40 w-8">#{i + 1}</span>
            <span className="flex-1 text-sm text-brand-blue truncate">{name}</span>
            <span className="text-xs font-semibold text-brand-blue">avg {rank}</span>
          </div>
        ))}
      </div>
    );
  }

  if (type === "date") {
    return (
      <div className="grid grid-cols-3 gap-2">
        <StatTile label="Earliest" value={stats.earliest ?? "—"} />
        <StatTile label="Latest" value={stats.latest ?? "—"} />
        <StatTile label="Count" value={stats.count ?? 0} />
      </div>
    );
  }

  if (type === "open" || type === "short_text") {
    return (
      <div className="grid grid-cols-2 gap-2">
        <StatTile label="Responses" value={stats.count ?? 0} />
        <StatTile label="Avg Length" value={`${stats.avg_length ?? 0} ch`} />
      </div>
    );
  }

  return <p className="text-xs text-brand-blue/40 italic">No analysis available</p>;
}
