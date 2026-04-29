"use client";

import { Suspense, useState, useEffect, useCallback, useMemo } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Card, CardContent, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Settings,
  Plus,
  Trash2,
  ChevronUp,
  ChevronDown,
  Save,
  Loader2,
  ArrowLeft,
  ChevronRight,
  X,
  Shuffle,
  History,
  RotateCcw,
  FileEdit,
  Copy,
  Eye,
  EyeOff,
  Sparkles,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { InnovateLogo } from "@/components/InnovateLogo";
import { NewSurveyDialog, type CreatedCohort } from "@/components/NewSurveyDialog";
import { SortableList, DragHandle, type DragHandleProps } from "@/components/SortableList";
import { SurveyPreview } from "@/components/SurveyPreview";
import { api, type SurveyQuestion, type QuestionGroup, type SurveyVersionSummary } from "@/lib/api";

const QUESTION_TYPES = [
  { value: "rating", label: "Rating (scale)" },
  { value: "mcq", label: "Multiple Choice (single)" },
  { value: "multi", label: "Multi-Select (multiple)" },
  { value: "open", label: "Open-Ended (text/voice)" },
  { value: "nps", label: "NPS (0–10 likelihood)" },
  { value: "slider", label: "Slider (range)" },
  { value: "matrix", label: "Matrix / Grid" },
  { value: "ranking", label: "Ranking (drag to order)" },
  { value: "yesno", label: "Yes / No" },
  { value: "dropdown", label: "Dropdown" },
  { value: "short_text", label: "Short Text" },
  { value: "date", label: "Date" },
] as const;

const TYPES_NEEDING_OPTIONS = new Set([
  "rating",
  "mcq",
  "multi",
  "matrix",
  "ranking",
  "dropdown",
]);

interface ProgramItem {
  id: string;
  name: string;
  course_name: string;
  program_type: string | null;
  max_submissions_per_ip?: number;
}

function emptyQuestion(): SurveyQuestion {
  return {
    id: `q${Date.now()}`,
    type: "open",
    text: "",
    required: false,
    voice_eligible: false,
  };
}

interface QuestionEditorProps {
  question: SurveyQuestion;
  index: number;
  total: number;
  allQuestions: SurveyQuestion[];
  availableGroups: QuestionGroup[];
  onChange: (updated: SurveyQuestion) => void;
  onDelete: () => void;
  onMoveUp: () => void;
  onMoveDown: () => void;
  dragHandle?: DragHandleProps;
}

function QuestionEditor({
  question,
  index,
  total,
  allQuestions,
  availableGroups,
  onChange,
  onDelete,
  onMoveUp,
  onMoveDown,
  dragHandle,
}: QuestionEditorProps) {
  const [expanded, setExpanded] = useState(false);
  const needsOptions = TYPES_NEEDING_OPTIONS.has(question.type);
  const isSlider = question.type === "slider";
  const isNps = question.type === "nps";
  const isMatrix = question.type === "matrix";
  const optionsLabel = question.type === "matrix" ? "Columns (scale)" : "Options";

  const updateField = <K extends keyof SurveyQuestion>(key: K, value: SurveyQuestion[K]) => {
    onChange({ ...question, [key]: value });
  };

  const addOption = () => {
    const current = (question.options || []) as (string | number)[];
    updateField("options", [...current, ""]);
  };

  const updateOption = (i: number, value: string) => {
    const current = [...(question.options || [])] as (string | number)[];
    current[i] = question.type === "rating" ? Number(value) || 0 : value;
    updateField("options", current);
  };

  const removeOption = (i: number) => {
    const current = [...(question.options || [])] as (string | number)[];
    current.splice(i, 1);
    updateField("options", current);
  };

  return (
    <Card className="bg-white border shadow-sm rounded-xl">
      <div
        className="flex items-center gap-3 px-4 py-3 cursor-pointer hover:bg-gray-50/50 transition-colors"
        onClick={() => setExpanded(!expanded)}
      >
        {dragHandle ? (
          <span onClick={(e) => e.stopPropagation()}>
            <DragHandle {...dragHandle} />
          </span>
        ) : null}
        <span className="text-xs font-mono text-brand-blue/30 shrink-0 w-6">
          {index + 1}.
        </span>
        <span className="text-sm font-medium text-brand-blue truncate flex-1">
          {question.text || "(untitled question)"}
        </span>
        {question.group && (
          <span className="text-xs bg-brand-teal/15 text-brand-teal px-2 py-0.5 rounded-full shrink-0">
            {availableGroups.find((g) => g.id === question.group)?.label || question.group}
          </span>
        )}
        <span className="text-xs bg-brand-light-blue/60 text-brand-blue/60 px-2 py-0.5 rounded-full shrink-0">
          {question.type}
        </span>
        <ChevronRight
          className={`h-4 w-4 text-brand-blue/30 transition-transform shrink-0 ${
            expanded ? "rotate-90" : ""
          }`}
        />
      </div>

      {expanded && (
        <CardContent className="pt-0 pb-4 space-y-4 border-t">
          <div className="grid grid-cols-3 gap-4 pt-4">
            <div className="space-y-1.5">
              <Label className="text-xs text-brand-blue/50">Question ID</Label>
              <Input
                value={question.id}
                onChange={(e) => updateField("id", e.target.value)}
                className="h-9 text-sm font-mono"
                placeholder="e.g. q1_recommend"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs text-brand-blue/50">Type</Label>
              <Select
                value={question.type}
                onValueChange={(v) =>
                  updateField("type", v as SurveyQuestion["type"])
                }
              >
                <SelectTrigger className="h-9 text-sm">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {QUESTION_TYPES.map((t) => (
                    <SelectItem key={t.value} value={t.value}>
                      {t.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs text-brand-blue/50">Group</Label>
              <Select
                value={question.group || "__none__"}
                onValueChange={(v) =>
                  updateField("group", v === "__none__" ? undefined : v)
                }
              >
                <SelectTrigger className="h-9 text-sm">
                  <SelectValue placeholder="No group" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none__">No group</SelectItem>
                  {availableGroups.map((g) => (
                    <SelectItem key={g.id} value={g.id}>
                      {g.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="space-y-1.5">
            <Label className="text-xs text-brand-blue/50">Question Text</Label>
            <Textarea
              value={question.text}
              onChange={(e) => updateField("text", e.target.value)}
              className="min-h-[60px] text-sm resize-y"
              placeholder="Enter the question text..."
            />
          </div>

          <div className="space-y-1.5">
            <Label className="text-xs text-brand-blue/50">
              Description (optional)
            </Label>
            <Input
              value={question.description || ""}
              onChange={(e) =>
                updateField("description", e.target.value || undefined)
              }
              className="h-9 text-sm"
              placeholder="Helper text shown below the question"
            />
          </div>

          {needsOptions && (
            <div className="space-y-2">
              <Label className="text-xs text-brand-blue/50">{optionsLabel}</Label>
              {((question.options || []) as (string | number)[]).map(
                (opt, i) => (
                  <div key={i} className="flex items-center gap-2">
                    <Input
                      value={String(opt)}
                      onChange={(e) => updateOption(i, e.target.value)}
                      className="h-8 text-sm flex-1"
                      placeholder={`${optionsLabel.slice(0, -1)} ${i + 1}`}
                    />
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={() => removeOption(i)}
                      className="h-8 w-8 p-0 text-brand-red/60 hover:text-brand-red"
                    >
                      <X className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                )
              )}
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={addOption}
                className="gap-1 text-xs"
              >
                <Plus className="h-3 w-3" /> Add {optionsLabel === "Options" ? "Option" : "Column"}
              </Button>
            </div>
          )}

          {isMatrix && (
            <div className="space-y-2">
              <Label className="text-xs text-brand-blue/50">Rows (items to rate)</Label>
              {(question.rows || []).map((row, i) => (
                <div key={i} className="flex items-center gap-2">
                  <Input
                    value={row}
                    onChange={(e) => {
                      const next = [...(question.rows || [])];
                      next[i] = e.target.value;
                      updateField("rows", next);
                    }}
                    className="h-8 text-sm flex-1"
                    placeholder={`Row ${i + 1}`}
                  />
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => {
                      const next = [...(question.rows || [])];
                      next.splice(i, 1);
                      updateField("rows", next);
                    }}
                    className="h-8 w-8 p-0 text-brand-red/60 hover:text-brand-red"
                  >
                    <X className="h-3.5 w-3.5" />
                  </Button>
                </div>
              ))}
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => updateField("rows", [...(question.rows || []), ""])}
                className="gap-1 text-xs"
              >
                <Plus className="h-3 w-3" /> Add Row
              </Button>
            </div>
          )}

          {isSlider && (
            <div className="grid grid-cols-3 gap-3">
              <div className="space-y-1">
                <Label className="text-xs text-brand-blue/50">Min</Label>
                <Input
                  type="number"
                  value={question.scale_min ?? 0}
                  onChange={(e) => updateField("scale_min", Number(e.target.value))}
                  className="h-8 text-sm"
                />
              </div>
              <div className="space-y-1">
                <Label className="text-xs text-brand-blue/50">Max</Label>
                <Input
                  type="number"
                  value={question.scale_max ?? 100}
                  onChange={(e) => updateField("scale_max", Number(e.target.value))}
                  className="h-8 text-sm"
                />
              </div>
              <div className="space-y-1">
                <Label className="text-xs text-brand-blue/50">Step</Label>
                <Input
                  type="number"
                  value={question.scale_step ?? 1}
                  onChange={(e) => updateField("scale_step", Number(e.target.value))}
                  className="h-8 text-sm"
                />
              </div>
            </div>
          )}

          {(isSlider || isNps) && (
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label className="text-xs text-brand-blue/50">Low Label</Label>
                <Input
                  value={question.labels?.low ?? ""}
                  onChange={(e) =>
                    updateField("labels", { ...(question.labels || {}), low: e.target.value })
                  }
                  className="h-8 text-sm"
                  placeholder={isNps ? "Not at all likely" : "Low"}
                />
              </div>
              <div className="space-y-1">
                <Label className="text-xs text-brand-blue/50">High Label</Label>
                <Input
                  value={question.labels?.high ?? ""}
                  onChange={(e) =>
                    updateField("labels", { ...(question.labels || {}), high: e.target.value })
                  }
                  className="h-8 text-sm"
                  placeholder={isNps ? "Extremely likely" : "High"}
                />
              </div>
            </div>
          )}

          <div className="flex flex-wrap items-center gap-6 pt-1">
            <label className="flex items-center gap-2 cursor-pointer">
              <Switch
                checked={question.required}
                onCheckedChange={(v) => updateField("required", v)}
              />
              <span className="text-sm text-brand-blue/70">Required</span>
            </label>

            {question.type === "open" && (
              <label className="flex items-center gap-2 cursor-pointer">
                <Switch
                  checked={question.voice_eligible}
                  onCheckedChange={(v) => updateField("voice_eligible", v)}
                />
                <span className="text-sm text-brand-blue/70">
                  Voice Eligible
                </span>
              </label>
            )}
          </div>

          <details className="pt-1">
            <summary className="text-xs text-brand-blue/40 cursor-pointer hover:text-brand-blue/60">
              Conditional Logic (advanced)
            </summary>
            <div className="grid grid-cols-3 gap-2 pt-2">
              <div className="space-y-1">
                <Label className="text-xs text-brand-blue/40">
                  Depends on Question
                </Label>
                <Select
                  value={question.condition?.question_id || "__none__"}
                  onValueChange={(v) =>
                    updateField(
                      "condition",
                      v === "__none__"
                        ? undefined
                        : {
                            question_id: v,
                            operator:
                              question.condition?.operator || "not_equals",
                            value: question.condition?.value || "",
                          }
                    )
                  }
                >
                  <SelectTrigger className="h-8 text-xs">
                    <SelectValue placeholder="None" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="__none__">None</SelectItem>
                    {allQuestions
                      .filter((q) => q.id !== question.id)
                      .map((q) => (
                        <SelectItem key={q.id} value={q.id}>
                          {q.id}
                        </SelectItem>
                      ))}
                  </SelectContent>
                </Select>
              </div>
              {question.condition && (
                <>
                  <div className="space-y-1">
                    <Label className="text-xs text-brand-blue/40">
                      Operator
                    </Label>
                    <Select
                      value={question.condition.operator}
                      onValueChange={(v) =>
                        updateField("condition", {
                          ...question.condition!,
                          operator: v,
                        })
                      }
                    >
                      <SelectTrigger className="h-8 text-xs">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="equals">equals</SelectItem>
                        <SelectItem value="not_equals">not equals</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-1">
                    <Label className="text-xs text-brand-blue/40">Value</Label>
                    <Input
                      value={question.condition.value}
                      onChange={(e) =>
                        updateField("condition", {
                          ...question.condition!,
                          value: e.target.value,
                        })
                      }
                      className="h-8 text-xs"
                      placeholder="Match value"
                    />
                  </div>
                </>
              )}
            </div>
          </details>

          <div className="flex items-center gap-2 pt-2 border-t">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={onMoveUp}
              disabled={index === 0}
              className="h-8 w-8 p-0"
            >
              <ChevronUp className="h-4 w-4" />
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={onMoveDown}
              disabled={index === total - 1}
              className="h-8 w-8 p-0"
            >
              <ChevronDown className="h-4 w-4" />
            </Button>
            <div className="flex-1" />
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={onDelete}
              className="gap-1 text-brand-red/70 hover:text-brand-red hover:bg-brand-red/5 text-xs"
            >
              <Trash2 className="h-3.5 w-3.5" /> Delete
            </Button>
          </div>
        </CardContent>
      )}
    </Card>
  );
}

function EditorLoading() {
  return (
    <div className="min-h-screen bg-brand-light-blue/40 flex items-center justify-center">
      <Loader2 className="h-8 w-8 animate-spin text-brand-blue" />
    </div>
  );
}

function EditorPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();

  // ── Programs and selection state ──
  const [programs, setPrograms] = useState<ProgramItem[]>([]);
  const [selectedProgramType, setSelectedProgramType] = useState<string>("");
  const [selectedProgram, setSelectedProgram] = useState<string>("");
  const [loading, setLoading] = useState(true);

  // ── Survey content state ──
  const [title, setTitle] = useState("Post-Course Survey");
  const [maxSubmissionsPerIp, setMaxSubmissionsPerIp] = useState(1);
  const [questions, setQuestions] = useState<SurveyQuestion[]>([]);
  const [questionGroups, setQuestionGroups] = useState<QuestionGroup[]>([]);
  const [activeVersion, setActiveVersion] = useState<string | null>(null);
  const [versionHistory, setVersionHistory] = useState<SurveyVersionSummary[]>([]);
  const [showHistory, setShowHistory] = useState(false);
  const [saving, setSaving] = useState(false);
  const [duplicating, setDuplicating] = useState(false);
  const [saveMessage, setSaveMessage] = useState("");
  const [showNewSurvey, setShowNewSurvey] = useState(false);
  const [showPreview, setShowPreview] = useState(false);
  const [showGenerator, setShowGenerator] = useState(false);
  const [aiGoal, setAiGoal] = useState("");
  const [aiQuestionCount, setAiQuestionCount] = useState(8);
  const [aiGenerating, setAiGenerating] = useState(false);

  // ── Derived: surveys filtered by program type ──
  const filteredPrograms = useMemo(() => {
    if (!selectedProgramType) return [];
    if (selectedProgramType === "all") return programs;
    return programs.filter(
      (p) => p.program_type === selectedProgramType || !p.program_type
    );
  }, [programs, selectedProgramType]);

  // ── Fetch program list ──
  const fetchPrograms = useCallback(async () => {
    try {
      const data = await api.getEditorCohorts();
      setPrograms(data);
      return data;
    } catch {
      router.push("/iu-ops-9k2p/editor/login");
      return [];
    }
  }, [router]);

  // ── Load survey config for a program ──
  const loadVersionHistory = useCallback(async (programId: string) => {
    try {
      const history = await api.getVersionHistory(programId);
      setVersionHistory(history.items);
      setActiveVersion(history.active_version);
    } catch {
      setVersionHistory([]);
    }
  }, []);

  const loadSurvey = useCallback(
    async (programId: string) => {
      if (!programId) return;
      try {
        const data = await api.getEditorSurvey(programId);
        setTitle(data.survey.title);
        setQuestions(data.survey.questions);
        setQuestionGroups(data.survey.question_groups || []);
        setActiveVersion(data.active_version ?? null);
        loadVersionHistory(programId);
      } catch {
        router.push("/iu-ops-9k2p/editor/login");
      }
    },
    [router, loadVersionHistory]
  );

  // ── Initial load: programs + optional preselection from ?cohort= ──
  useEffect(() => {
    const cohortFromUrl = searchParams.get("cohort");
    fetchPrograms().then((data) => {
      if (cohortFromUrl) {
        const match = data.find((p) => p.id === cohortFromUrl);
        if (match) {
          setSelectedProgramType(match.program_type || "all");
          setSelectedProgram(match.id);
          setMaxSubmissionsPerIp(match.max_submissions_per_ip ?? 1);
        }
      }
      setLoading(false);
    });
  }, [fetchPrograms, searchParams]);

  // ── Cross-tab sync: refresh programs when window regains focus ──
  useEffect(() => {
    const onFocus = () => {
      fetchPrograms();
    };
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [fetchPrograms]);

  // ── Load survey when selection changes ──
  useEffect(() => {
    if (selectedProgram) {
      loadSurvey(selectedProgram);
      const program = programs.find((p) => p.id === selectedProgram);
      if (program) setMaxSubmissionsPerIp(program.max_submissions_per_ip ?? 1);
    } else {
      setTitle("Post-Course Survey");
      setQuestions([]);
      setQuestionGroups([]);
      setActiveVersion(null);
      setVersionHistory([]);
      setShowPreview(false);
    }
  }, [selectedProgram, programs, loadSurvey]);

  // ── Selection handlers ──
  const handleProgramTypeChange = (value: string) => {
    setSelectedProgramType(value);
    setSelectedProgram("");
    setShowPreview(false);
  };

  const handleProgramChange = (value: string) => {
    setSelectedProgram(value);
  };

  const handleSurveyCreated = async (cohort: CreatedCohort) => {
    // Refresh list so the new survey is included
    const data = await fetchPrograms();
    if (cohort.program_type) setSelectedProgramType(cohort.program_type);
    setSelectedProgram(cohort.id);
    const created = data.find((p) => p.id === cohort.id);
    if (created) setMaxSubmissionsPerIp(created.max_submissions_per_ip ?? 1);
  };

  const handleSave = async () => {
    if (!selectedProgram) return;
    setSaving(true);
    setSaveMessage("");
    try {
      const result = await api.saveEditorSurvey(selectedProgram, {
        version: "1.0",
        title,
        questions,
        question_groups: questionGroups,
      });
      if (result.status === "no_changes") {
        setSaveMessage("No changes detected");
      } else {
        setSaveMessage(`Saved as ${result.version_label}`);
        setActiveVersion(result.version_label ?? activeVersion);
        loadVersionHistory(selectedProgram);
      }
      setTimeout(() => setSaveMessage(""), 4000);
    } catch (err) {
      setSaveMessage(
        err instanceof Error ? err.message : "Failed to save survey"
      );
    } finally {
      setSaving(false);
    }
  };

  const handleRestore = async (versionLabel: string) => {
    if (!selectedProgram) return;
    if (!confirm(`Restore survey to ${versionLabel}? This will create a new version.`)) return;
    try {
      const result = await api.restoreVersion(selectedProgram, versionLabel);
      setActiveVersion(result.version_label);
      setSaveMessage(`Restored from ${versionLabel} as ${result.version_label}`);
      await loadSurvey(selectedProgram);
      setTimeout(() => setSaveMessage(""), 4000);
    } catch (err) {
      setSaveMessage(
        err instanceof Error ? err.message : "Failed to restore"
      );
    }
  };

  const handleDuplicateSurvey = async () => {
    if (!selectedProgram) return;
    setDuplicating(true);
    setSaveMessage("");
    try {
      const copy = await api.duplicateCohort(selectedProgram);
      const data = await fetchPrograms();
      setSelectedProgramType(copy.program_type || "all");
      setSelectedProgram(copy.id);
      const created = data.find((p) => p.id === copy.id);
      setMaxSubmissionsPerIp(
        created?.max_submissions_per_ip ?? copy.max_submissions_per_ip ?? 1
      );
      setSaveMessage(`Duplicated as ${copy.name}`);
      setTimeout(() => setSaveMessage(""), 4000);
    } catch (err) {
      setSaveMessage(
        err instanceof Error ? err.message : "Failed to duplicate survey"
      );
    } finally {
      setDuplicating(false);
    }
  };

  const handleGenerateSurvey = async () => {
    if (!aiGoal.trim()) {
      setSaveMessage("Describe what the survey should learn");
      return;
    }
    if (questions.length > 0) {
      const confirmed = confirm("Replace the current draft questions with an AI-generated survey? You can still review before saving.");
      if (!confirmed) return;
    }
    setAiGenerating(true);
    setSaveMessage("");
    try {
      const result = await api.generateSurvey({
        goal_description: aiGoal,
        program_type: selectedProgramType === "all" ? undefined : selectedProgramType,
        question_count: aiQuestionCount,
      });
      setTitle(result.survey.title || title);
      setQuestions(result.survey.questions || []);
      setQuestionGroups(result.survey.question_groups || []);
      setShowGenerator(false);
      setShowPreview(true);
      setSaveMessage("Generated draft survey");
      setTimeout(() => setSaveMessage(""), 4000);
    } catch (err) {
      setSaveMessage(err instanceof Error ? err.message : "Failed to generate survey");
    } finally {
      setAiGenerating(false);
    }
  };

  const updateQuestion = (index: number, updated: SurveyQuestion) => {
    const next = [...questions];
    next[index] = updated;
    setQuestions(next);
  };

  const deleteQuestion = (index: number) => {
    setQuestions(questions.filter((_, i) => i !== index));
  };

  const moveQuestion = (from: number, to: number) => {
    if (to < 0 || to >= questions.length) return;
    const next = [...questions];
    const [item] = next.splice(from, 1);
    next.splice(to, 0, item);
    setQuestions(next);
  };

  const addQuestion = () => {
    setQuestions([...questions, emptyQuestion()]);
  };

  if (loading) {
    return <EditorLoading />;
  }

  return (
    <div className="min-h-screen bg-brand-light-blue/40 pb-16">
      <header className="bg-white border-b border-[#E4EFFC] px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <InnovateLogo size="sm" />
          <div className="h-6 w-px bg-[#124D8F]/10" />
          <div className="flex items-center gap-2 text-xs font-semibold text-brand-dark-yellow uppercase tracking-widest">
            <Settings className="h-3.5 w-3.5" />
            Survey Editor
          </div>
        </div>
        <div className="flex items-center gap-2">
          {selectedProgram && (
            <Button
              variant="outline"
              size="sm"
              onClick={handleDuplicateSurvey}
              disabled={duplicating}
              className="border-brand-blue/15 text-brand-blue/60 hover:bg-brand-blue/5 gap-2"
            >
              {duplicating ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Copy className="h-4 w-4" />
              )}
              Duplicate
            </Button>
          )}
          {selectedProgram && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => setShowGenerator(!showGenerator)}
              className="border-brand-teal/20 text-brand-teal hover:bg-brand-teal/5 gap-2"
            >
              <Sparkles className="h-4 w-4" />
              AI Generate
            </Button>
          )}
          <Button
            size="sm"
            onClick={() => setShowNewSurvey(true)}
            className="bg-brand-blue hover:bg-brand-blue/90 gap-2"
          >
            <Plus className="h-4 w-4" />
            New Survey
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => router.push("/iu-ops-9k2p/dashboard")}
            className="border-brand-blue/15 text-brand-blue/60 hover:bg-brand-blue/5 gap-2"
          >
            <ArrowLeft className="h-4 w-4" />
            Back to Dashboard
          </Button>
        </div>
      </header>

      <main
        className={`mx-auto px-6 py-8 space-y-6 ${
          showPreview ? "max-w-7xl" : "max-w-4xl"
        }`}
      >
        {/* ── Program + Survey selectors (mirrors Dashboard) ── */}
        <Card className="bg-white border-0 shadow-sm rounded-2xl">
          <CardContent className="pt-6">
            <div className="flex flex-wrap gap-4 items-end">
              <div className="space-y-1">
                <Label className="text-xs font-semibold text-brand-blue/40 uppercase tracking-wider">
                  Program
                </Label>
                <Select value={selectedProgramType} onValueChange={handleProgramTypeChange}>
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

              <div className="space-y-1">
                <Label className="text-xs font-semibold text-brand-blue/40 uppercase tracking-wider">
                  Survey
                </Label>
                <Select
                  value={selectedProgram}
                  onValueChange={handleProgramChange}
                  disabled={!selectedProgramType}
                >
                  <SelectTrigger className="w-72 rounded-xl">
                    <SelectValue
                      placeholder={
                        selectedProgramType
                          ? "Select survey..."
                          : "Select a program first"
                      }
                    />
                  </SelectTrigger>
                  <SelectContent>
                    {filteredPrograms.map((p) => (
                      <SelectItem key={p.id} value={p.id}>
                        {p.name}
                      </SelectItem>
                    ))}
                    {filteredPrograms.length === 0 && selectedProgramType && (
                      <p className="px-3 py-2 text-xs text-brand-blue/40">
                        No surveys for this program type
                      </p>
                    )}
                  </SelectContent>
                </Select>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* ── Editing surface (only when a survey is selected) ── */}
        {selectedProgram ? (
          <>
            <div
              className={
                showPreview
                  ? "grid gap-6 xl:grid-cols-[minmax(0,1fr)_420px] items-start"
                  : ""
              }
            >
              <div className="space-y-6">
            <Card className="bg-white border-0 shadow-sm rounded-2xl">
              <CardContent className="pt-6">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div className="space-y-1">
                    <Label className="text-xs font-semibold text-brand-blue/40 uppercase tracking-wider">
                      Survey Title
                    </Label>
                    <Input
                      value={title}
                      onChange={(e) => setTitle(e.target.value)}
                      className="rounded-xl"
                    />
                  </div>
                  <div className="space-y-1">
                    <Label className="text-xs font-semibold text-brand-blue/40 uppercase tracking-wider">
                      Max Submissions / IP
                    </Label>
                    <div className="flex items-center gap-2">
                      <Input
                        type="number"
                        min={0}
                        value={maxSubmissionsPerIp}
                        onChange={(e) =>
                          setMaxSubmissionsPerIp(Number(e.target.value) || 0)
                        }
                        className="rounded-xl w-20"
                      />
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        className="rounded-xl text-xs shrink-0"
                        onClick={async () => {
                          if (!selectedProgram) return;
                          try {
                            await api.updateCohortSettings(selectedProgram, {
                              max_submissions_per_ip: maxSubmissionsPerIp,
                            });
                            setSaveMessage("Limit updated");
                            setTimeout(() => setSaveMessage(""), 3000);
                          } catch {
                            setSaveMessage("Failed to update limit");
                          }
                        }}
                      >
                        Apply
                      </Button>
                    </div>
                    <p className="text-[10px] text-brand-blue/30">0 = unlimited</p>
                  </div>
                </div>
              </CardContent>
            </Card>

            {showGenerator && (
              <Card className="bg-white border-0 shadow-sm rounded-2xl">
                <CardContent className="pt-6 space-y-4">
                  <div className="flex items-center gap-2">
                    <Sparkles className="h-4 w-4 text-brand-teal" />
                    <Label className="text-xs font-semibold text-brand-blue/40 uppercase tracking-wider">
                      AI Survey Generator
                    </Label>
                  </div>
                  <Textarea
                    value={aiGoal}
                    onChange={(e) => setAiGoal(e.target.value)}
                    className="min-h-[110px] rounded-xl text-sm resize-y"
                    placeholder="Example: Collect feedback from workshop participants about what they applied, what barriers they faced, and what support they need next."
                  />
                  <div className="flex flex-wrap items-end gap-3">
                    <div className="space-y-1">
                      <Label className="text-xs text-brand-blue/45">Questions</Label>
                      <Input
                        type="number"
                        min={3}
                        max={14}
                        value={aiQuestionCount}
                        onChange={(e) => setAiQuestionCount(Number(e.target.value) || 8)}
                        className="h-9 w-24 rounded-xl"
                      />
                    </div>
                    <Button
                      type="button"
                      onClick={handleGenerateSurvey}
                      disabled={aiGenerating}
                      className="gap-2 bg-brand-teal hover:bg-brand-teal/90"
                    >
                      {aiGenerating ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <Sparkles className="h-4 w-4" />
                      )}
                      Generate Draft
                    </Button>
                    <p className="text-xs text-brand-blue/40">
                      Review and edit the draft, then save when ready.
                    </p>
                  </div>
                </CardContent>
              </Card>
            )}

            <Card className="bg-white border-0 shadow-sm rounded-2xl">
              <CardContent className="pt-6 space-y-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Shuffle className="h-4 w-4 text-brand-blue/50" />
                    <Label className="text-xs font-semibold text-brand-blue/40 uppercase tracking-wider">
                      Question Groups
                    </Label>
                  </div>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() =>
                      setQuestionGroups([
                        ...questionGroups,
                        { id: `group_${Date.now()}`, label: "", randomize: false },
                      ])
                    }
                    className="gap-1 text-xs"
                  >
                    <Plus className="h-3 w-3" /> Add Group
                  </Button>
                </div>
                {questionGroups.length === 0 && (
                  <p className="text-xs text-brand-blue/30">
                    No groups defined. Questions will be served in their authored
                    order. Add groups to enable within-group randomization.
                  </p>
                )}
                {questionGroups.length > 0 && (
                  <SortableList
                    items={questionGroups.map((group, index) => ({
                      id: `${group.id || "group"}-${index}`,
                      group,
                    }))}
                    onReorder={(next) =>
                      setQuestionGroups(next.map((item) => item.group))
                    }
                    renderItem={(item, gi, dragHandle) => {
                      const g = item.group;
                      return (
                        <div className="flex items-center gap-3 bg-gray-50/80 rounded-lg px-3 py-2">
                          <span className="shrink-0">
                            <DragHandle {...dragHandle} />
                          </span>
                          <Input
                            value={g.id}
                            onChange={(e) => {
                              const oldId = g.id;
                              const next = [...questionGroups];
                              next[gi] = { ...g, id: e.target.value };
                              setQuestionGroups(next);
                              setQuestions(
                                questions.map((q) =>
                                  q.group === oldId
                                    ? { ...q, group: e.target.value }
                                    : q
                                )
                              );
                            }}
                            className="h-8 text-xs font-mono w-28"
                            placeholder="group_id"
                          />
                          <Input
                            value={g.label}
                            onChange={(e) => {
                              const next = [...questionGroups];
                              next[gi] = { ...g, label: e.target.value };
                              setQuestionGroups(next);
                            }}
                            className="h-8 text-sm flex-1"
                            placeholder="Group label"
                          />
                          <label className="flex items-center gap-1.5 cursor-pointer shrink-0">
                            <Switch
                              checked={g.randomize}
                              onCheckedChange={(v) => {
                                const next = [...questionGroups];
                                next[gi] = { ...g, randomize: v };
                                setQuestionGroups(next);
                              }}
                            />
                            <span className="text-xs text-brand-blue/60">Randomize</span>
                          </label>
                          <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            onClick={() => {
                              const removedId = g.id;
                              setQuestionGroups(
                                questionGroups.filter((_, i) => i !== gi)
                              );
                              setQuestions(
                                questions.map((q) =>
                                  q.group === removedId
                                    ? { ...q, group: undefined }
                                    : q
                                )
                              );
                            }}
                            className="h-8 w-8 p-0 text-brand-red/60 hover:text-brand-red shrink-0"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </Button>
                        </div>
                      );
                    }}
                  />
                )}
              </CardContent>
            </Card>

            <div className="flex items-center justify-between">
              <CardTitle className="text-sm font-medium text-brand-blue">
                Questions ({questions.length})
              </CardTitle>
              <div className="flex items-center gap-2">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => setShowPreview(!showPreview)}
                  className="gap-1.5 border-brand-blue/15 text-brand-blue/60 hover:bg-brand-blue/5 text-xs px-3"
                >
                  {showPreview ? (
                    <EyeOff className="h-3.5 w-3.5" />
                  ) : (
                    <Eye className="h-3.5 w-3.5" />
                  )}
                  {showPreview ? "Hide Preview" : "Preview"}
                </Button>
                <Button
                  size="sm"
                  onClick={addQuestion}
                  className="gap-1.5 bg-brand-blue hover:bg-brand-blue/90 text-xs px-4"
                >
                  <Plus className="h-3.5 w-3.5" /> Add Question
                </Button>
              </div>
            </div>

            <div className="space-y-3">
              {questions.length > 0 && (
                <SortableList
                  items={questions.map((question, index) => ({
                    id: `${question.id || "question"}-${index}`,
                    question,
                  }))}
                  onReorder={(next) =>
                    setQuestions(next.map((item) => item.question))
                  }
                  renderItem={(item, i, dragHandle) => (
                    <QuestionEditor
                      question={item.question}
                      index={i}
                      total={questions.length}
                      allQuestions={questions}
                      availableGroups={questionGroups}
                      onChange={(updated) => updateQuestion(i, updated)}
                      onDelete={() => deleteQuestion(i)}
                      onMoveUp={() => moveQuestion(i, i - 1)}
                      onMoveDown={() => moveQuestion(i, i + 1)}
                      dragHandle={dragHandle}
                    />
                  )}
                />
              )}
            </div>

            {questions.length === 0 && (
              <Card className="bg-white border-dashed border-2 border-brand-blue/10 rounded-2xl">
                <CardContent className="py-12 text-center">
                  <p className="text-sm text-brand-blue/40">
                    No questions yet. Click &quot;Add Question&quot; to get started.
                  </p>
                </CardContent>
              </Card>
            )}

            <div className="flex items-center gap-4 pt-4">
              <Button
                onClick={handleSave}
                disabled={saving || !selectedProgram}
                className="gap-2 bg-brand-teal hover:bg-brand-teal/90 px-8 shadow-sm"
              >
                {saving ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Save className="h-4 w-4" />
                )}
                {saving ? "Saving..." : "Save Survey"}
              </Button>
              {activeVersion && (
                <Badge
                  variant="outline"
                  className="text-xs font-mono border-brand-blue/20 text-brand-blue/60"
                >
                  {activeVersion}
                </Badge>
              )}
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => setShowHistory(!showHistory)}
                className="gap-1.5 text-xs text-brand-blue/50 hover:text-brand-blue"
              >
                <History className="h-3.5 w-3.5" />
                History
              </Button>
              {saveMessage && (
                <span
                  className={`text-sm ${
                    saveMessage.includes("Saved") ||
                    saveMessage.includes("Restored") ||
                    saveMessage.includes("Duplicated") ||
                    saveMessage.includes("updated")
                      ? "text-brand-teal"
                      : saveMessage.includes("No changes")
                        ? "text-brand-blue/50"
                        : "text-brand-red"
                  }`}
                >
                  {saveMessage}
                </span>
              )}
            </div>

            {showHistory && (
              <Card className="bg-white border-0 shadow-sm rounded-2xl">
                <CardContent className="pt-6 space-y-3">
                  <div className="flex items-center gap-2 mb-2">
                    <History className="h-4 w-4 text-brand-blue/50" />
                    <Label className="text-xs font-semibold text-brand-blue/40 uppercase tracking-wider">
                      Version History
                    </Label>
                  </div>
                  {versionHistory.length === 0 && (
                    <p className="text-xs text-brand-blue/30">No versions saved yet.</p>
                  )}
                  {versionHistory.map((v) => (
                    <div
                      key={v.version_label}
                      className={`flex items-center gap-3 rounded-lg px-3 py-2.5 ${
                        v.version_label === activeVersion
                          ? "bg-brand-teal/5 border border-brand-teal/20"
                          : "bg-gray-50/80"
                      }`}
                    >
                      <Badge
                        variant={v.version_label === activeVersion ? "default" : "outline"}
                        className={`text-xs font-mono shrink-0 ${
                          v.version_label === activeVersion
                            ? "bg-brand-teal text-white"
                            : "border-brand-blue/20 text-brand-blue/50"
                        }`}
                      >
                        {v.version_label}
                      </Badge>
                      <div className="flex-1 min-w-0">
                        <p className="text-xs text-brand-blue/70 truncate">
                          {v.change_summary || "No description"}
                        </p>
                        <p className="text-[10px] text-brand-blue/30">
                          {new Date(v.created_at).toLocaleString()} by {v.created_by}
                        </p>
                      </div>
                      {v.version_label !== activeVersion && (
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          onClick={() => handleRestore(v.version_label)}
                          className="gap-1 text-xs text-brand-blue/40 hover:text-brand-blue shrink-0"
                        >
                          <RotateCcw className="h-3 w-3" />
                          Restore
                        </Button>
                      )}
                      {v.version_label === activeVersion && (
                        <span className="text-[10px] font-medium text-brand-teal uppercase tracking-wider shrink-0">
                          Current
                        </span>
                      )}
                    </div>
                  ))}
                </CardContent>
              </Card>
            )}
              </div>

              {showPreview && (
                <aside className="xl:sticky xl:top-6">
                  <SurveyPreview
                    title={title}
                    questions={questions}
                    questionGroups={questionGroups}
                  />
                </aside>
              )}
            </div>
          </>
        ) : (
          <Card className="bg-white border-0 shadow-sm rounded-2xl">
            <CardContent className="py-16 text-center space-y-3">
              <FileEdit className="h-10 w-10 text-brand-blue/20 mx-auto" />
              <p className="text-sm text-brand-blue/40">
                {selectedProgramType
                  ? "Select a survey to start editing"
                  : "Select a program type to get started"}
              </p>
              <p className="text-xs text-brand-blue/30">
                Or click &ldquo;New Survey&rdquo; to create a new one.
              </p>
            </CardContent>
          </Card>
        )}
      </main>

      <NewSurveyDialog
        open={showNewSurvey}
        onOpenChange={setShowNewSurvey}
        onCreated={handleSurveyCreated}
        primaryActionLabel="Start Editing"
      />
    </div>
  );
}

export default function EditorPage() {
  return (
    <Suspense fallback={<EditorLoading />}>
      <EditorPageContent />
    </Suspense>
  );
}
