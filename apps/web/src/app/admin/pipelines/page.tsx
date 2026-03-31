"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { InnovateLogo } from "@/components/InnovateLogo";
import {
  ArrowLeft,
  Database,
  CheckCircle2,
  XCircle,
  Loader2,
  ExternalLink,
  RefreshCw,
  ArrowRight,
} from "lucide-react";
import { api } from "@/lib/api";

interface PipelineStatus {
  id: string;
  name: string;
  description: string;
  configured: boolean;
  details: Record<string, string | null>;
  loading: boolean;
  color: string;
  icon: string;
}

export default function PipelinesPage() {
  const router = useRouter();
  const [pipelines, setPipelines] = useState<PipelineStatus[]>([
    {
      id: "backend",
      name: "InnovateUS Database",
      description:
        "Your primary data store. All survey responses, AI extractions, and metadata are saved here automatically.",
      configured: true,
      details: { status: "Always active" },
      loading: false,
      color: "brand-teal",
      icon: "database",
    },
    {
      id: "jotform",
      name: "JotForm",
      description:
        "Push completed responses to a JotForm form via the submissions API. Requires an API key and form ID.",
      configured: false,
      details: {},
      loading: true,
      color: "brand-dark-yellow",
      icon: "jotform",
    },
  ]);

  const [syncing, setSyncing] = useState<Record<string, boolean>>({});

  useEffect(() => {
    api
      .getJotformStatus()
      .then((data) => {
        setPipelines((prev) =>
          prev.map((p) =>
            p.id === "jotform"
              ? {
                  ...p,
                  configured: data.configured,
                  details: {
                    form_id: data.form_id,
                    api_url: data.api_url,
                  },
                  loading: false,
                }
              : p
          )
        );
      })
      .catch(() => {
        setPipelines((prev) =>
          prev.map((p) =>
            p.id === "jotform"
              ? { ...p, loading: false, details: { error: "Failed to check" } }
              : p
          )
        );
      });
  }, []);

  const activeCount = pipelines.filter((p) => p.configured).length;

  return (
    <div className="min-h-screen bg-brand-light-blue/40">
      <header className="bg-white border-b border-[#E4EFFC] px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <InnovateLogo size="sm" />
          <div className="h-6 w-px bg-[#124D8F]/10" />
          <span className="text-xs font-semibold text-[#124D8F]/40 uppercase tracking-widest">
            Pipelines
          </span>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => router.push("/admin/dashboard")}
          className="rounded-full border-brand-blue/15 text-brand-blue/60 hover:bg-brand-blue/5 gap-2"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Dashboard
        </Button>
      </header>

      <main className="max-w-4xl mx-auto px-6 py-8 space-y-8">
        {/* Summary */}
        <div className="space-y-2">
          <h1 className="text-2xl font-serif text-brand-blue">
            Data Pipelines
          </h1>
          <p className="text-brand-blue/60 text-sm">
            When a user completes your survey, data flows to every active
            pipeline below. Enable multiple destinations to keep your data in
            sync across platforms.
          </p>
        </div>

        {/* Flow Diagram */}
        <Card className="bg-white border-0 shadow-sm rounded-2xl">
          <CardContent className="pt-6 pb-6">
            <div className="flex items-center justify-center gap-3 flex-wrap">
              <div className="flex items-center gap-2 bg-brand-light-blue rounded-full px-4 py-2">
                <span className="w-2 h-2 rounded-full bg-brand-blue animate-pulse" />
                <span className="text-sm font-medium text-brand-blue">
                  User Submits Survey
                </span>
              </div>
              <ArrowRight className="h-4 w-4 text-brand-blue/30 shrink-0" />
              <div className="flex items-center gap-2 bg-brand-blue/5 rounded-full px-4 py-2">
                <RefreshCw className="h-3.5 w-3.5 text-brand-blue/50" />
                <span className="text-sm text-brand-blue/60">
                  Background Sync
                </span>
              </div>
              <ArrowRight className="h-4 w-4 text-brand-blue/30 shrink-0" />
              <div className="flex items-center gap-2 bg-brand-teal/10 rounded-full px-4 py-2">
                <span className="text-sm font-medium text-brand-teal">
                  {activeCount} Active{" "}
                  {activeCount === 1 ? "Pipeline" : "Pipelines"}
                </span>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Pipeline Cards */}
        <div className="space-y-4">
          {pipelines.map((pipeline) => (
            <Card
              key={pipeline.id}
              className={`bg-white border-0 shadow-sm rounded-2xl transition-all ${
                pipeline.configured
                  ? "ring-1 ring-brand-teal/20"
                  : "opacity-80"
              }`}
            >
              <CardHeader className="pb-2">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div
                      className={`w-10 h-10 rounded-xl flex items-center justify-center ${
                        pipeline.id === "backend"
                          ? "bg-brand-teal/10"
                          : "bg-brand-yellow/15"
                      }`}
                    >
                      {pipeline.id === "backend" ? (
                        <Database
                          className="h-5 w-5 text-brand-teal"
                        />
                      ) : (
                        <span className="text-base font-bold text-brand-dark-yellow">
                          JF
                        </span>
                      )}
                    </div>
                    <div>
                      <CardTitle className="text-base text-brand-blue">
                        {pipeline.name}
                      </CardTitle>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    {pipeline.loading ? (
                      <Loader2 className="h-4 w-4 animate-spin text-brand-blue/40" />
                    ) : pipeline.configured ? (
                      <Badge className="bg-brand-teal/10 text-brand-teal border-0 gap-1.5">
                        <CheckCircle2 className="h-3 w-3" />
                        Active
                      </Badge>
                    ) : (
                      <Badge
                        variant="outline"
                        className="border-brand-blue/10 text-brand-blue/40 gap-1.5"
                      >
                        <XCircle className="h-3 w-3" />
                        Not Configured
                      </Badge>
                    )}
                  </div>
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                <p className="text-sm text-brand-blue/50 leading-relaxed">
                  {pipeline.description}
                </p>

                {!pipeline.loading && pipeline.id !== "backend" && (
                  <div className="bg-brand-light-blue/40 rounded-xl p-4 space-y-2">
                    {pipeline.configured ? (
                      <>
                        <p className="text-xs font-semibold text-brand-blue/40 uppercase tracking-wider">
                          Connection Details
                        </p>
                        <div className="grid grid-cols-2 gap-2">
                          {Object.entries(pipeline.details)
                            .filter(([, v]) => v)
                            .map(([key, value]) => (
                              <div key={key}>
                                <p className="text-[11px] text-brand-blue/30 uppercase">
                                  {key.replace(/_/g, " ")}
                                </p>
                                <p className="text-sm font-mono text-brand-blue/70">
                                  {value}
                                </p>
                              </div>
                            ))}
                        </div>
                      </>
                    ) : (
                      <div className="space-y-2">
                        <p className="text-xs font-semibold text-brand-blue/40 uppercase tracking-wider">
                          How to Enable
                        </p>
                        <ol className="text-sm text-brand-blue/60 space-y-1 list-decimal list-inside">
                          <li>
                            Get your API key from{" "}
                            <a
                              href="https://www.jotform.com/myaccount/api"
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-brand-blue underline inline-flex items-center gap-1"
                            >
                              jotform.com/myaccount/api
                              <ExternalLink className="h-3 w-3" />
                            </a>
                          </li>
                          <li>
                            Add{" "}
                            <code className="text-xs bg-brand-blue/5 px-1.5 py-0.5 rounded">
                              JOTFORM_API_KEY
                            </code>{" "}
                            and{" "}
                            <code className="text-xs bg-brand-blue/5 px-1.5 py-0.5 rounded">
                              JOTFORM_FORM_ID
                            </code>{" "}
                            to your{" "}
                            <code className="text-xs bg-brand-blue/5 px-1.5 py-0.5 rounded">
                              .env
                            </code>
                          </li>
                          <li>Restart the API server</li>
                        </ol>
                      </div>
                    )}
                  </div>
                )}

                {pipeline.id === "backend" && (
                  <div className="bg-brand-teal/5 rounded-xl p-4">
                    <p className="text-xs font-semibold text-brand-teal/60 uppercase tracking-wider mb-1">
                      Always Active
                    </p>
                    <p className="text-sm text-brand-blue/50">
                      This is your primary database. Every submission is stored
                      here regardless of other pipeline settings. Exports (CSV,
                      PDF, PPTX) pull from this source.
                    </p>
                  </div>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      </main>
    </div>
  );
}
