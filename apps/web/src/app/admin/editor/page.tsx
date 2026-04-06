"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
  GripVertical,
  ChevronRight,
  X,
  Shuffle,
  History,
  RotateCcw,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { InnovateLogo } from "@/components/InnovateLogo";
import { api, type SurveyQuestion, type QuestionGroup, type SurveyVersionSummary } from "@/lib/api";

const QUESTION_TYPES = [
  { value: "rating", label: "Rating (scale)" },
  { value: "mcq", label: "Multiple Choice (single)" },
  { value: "multi", label: "Multi-Select (multiple)" },
  { value: "open", label: "Open-Ended (text/voice)" },
] as const;

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
}: QuestionEditorProps) {
  const [expanded, setExpanded] = useState(false);
  const needsOptions = question.type === "rating" || question.type === "mcq" || question.type === "multi";

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
        <GripVertical className="h-4 w-4 text-brand-blue/20 shrink-0" />
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
              <Label className="text-xs text-brand-blue/50">Options</Label>
              {((question.options || []) as (string | number)[]).map(
                (opt, i) => (
                  <div key={i} className="flex items-center gap-2">
                    <Input
                      value={String(opt)}
                      onChange={(e) => updateOption(i, e.target.value)}
                      className="h-8 text-sm flex-1"
                      placeholder={`Option ${i + 1}`}
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
                <Plus className="h-3 w-3" /> Add Option
              </Button>
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

export default function EditorPage() {
  const router = useRouter();
  const [cohorts, setCohorts] = useState<
    Array<{ id: string; name: string; course_name: string; max_submissions_per_ip?: number }>
  >([]);
  const [selectedCohort, setSelectedCohort] = useState("");
  const [title, setTitle] = useState("Post-Course Survey");
  const [maxSubmissionsPerIp, setMaxSubmissionsPerIp] = useState(1);
  const [questions, setQuestions] = useState<SurveyQuestion[]>([]);
  const [questionGroups, setQuestionGroups] = useState<QuestionGroup[]>([]);
  const [activeVersion, setActiveVersion] = useState<string | null>(null);
  const [versionHistory, setVersionHistory] = useState<SurveyVersionSummary[]>([]);
  const [showHistory, setShowHistory] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState("");

  const loadVersionHistory = useCallback(
    async (cohortId: string) => {
      try {
        const history = await api.getVersionHistory(cohortId);
        setVersionHistory(history.items);
        setActiveVersion(history.active_version);
      } catch {
        setVersionHistory([]);
      }
    },
    []
  );

  const loadSurvey = useCallback(
    async (cohortId: string) => {
      if (!cohortId) return;
      try {
        const data = await api.getEditorSurvey(cohortId);
        setTitle(data.survey.title);
        setQuestions(data.survey.questions);
        setQuestionGroups(data.survey.question_groups || []);
        setActiveVersion(data.active_version ?? null);
        loadVersionHistory(cohortId);
      } catch {
        router.push("/admin/editor/login");
      }
    },
    [router, loadVersionHistory]
  );

  useEffect(() => {
    api
      .getEditorCohorts()
      .then((data) => {
        setCohorts(data);
        if (data.length > 0) {
          setSelectedCohort(data[0].id);
          setMaxSubmissionsPerIp(data[0].max_submissions_per_ip ?? 1);
        }
      })
      .catch(() => router.push("/admin/editor/login"))
      .finally(() => setLoading(false));
  }, [router]);

  useEffect(() => {
    if (selectedCohort) {
      loadSurvey(selectedCohort);
      const cohort = cohorts.find((c) => c.id === selectedCohort);
      if (cohort) setMaxSubmissionsPerIp(cohort.max_submissions_per_ip ?? 1);
    }
  }, [selectedCohort, loadSurvey, cohorts]);

  const handleSave = async () => {
    if (!selectedCohort) return;
    setSaving(true);
    setSaveMessage("");
    try {
      const result = await api.saveEditorSurvey(selectedCohort, {
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
        loadVersionHistory(selectedCohort);
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
    if (!selectedCohort) return;
    if (!confirm(`Restore survey to ${versionLabel}? This will create a new version.`)) return;
    try {
      const result = await api.restoreVersion(selectedCohort, versionLabel);
      setActiveVersion(result.version_label);
      setSaveMessage(`Restored from ${versionLabel} as ${result.version_label}`);
      await loadSurvey(selectedCohort);
      setTimeout(() => setSaveMessage(""), 4000);
    } catch (err) {
      setSaveMessage(
        err instanceof Error ? err.message : "Failed to restore"
      );
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
    return (
      <div className="min-h-screen bg-brand-light-blue/40 flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-brand-blue" />
      </div>
    );
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

      <main className="max-w-3xl mx-auto px-6 py-8 space-y-6">
        <Card className="bg-white border-0 shadow-sm rounded-2xl">
          <CardContent className="pt-6">
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div className="space-y-1">
                <Label className="text-xs font-semibold text-brand-blue/40 uppercase tracking-wider">
                  Cohort
                </Label>
                <Select
                  value={selectedCohort}
                  onValueChange={setSelectedCohort}
                >
                  <SelectTrigger className="rounded-xl w-full">
                    <SelectValue placeholder="Select cohort" />
                  </SelectTrigger>
                  <SelectContent>
                    {cohorts.map((c) => (
                      <SelectItem key={c.id} value={c.id}>
                        {c.name} — {c.course_name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
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
                    onChange={(e) => setMaxSubmissionsPerIp(Number(e.target.value) || 0)}
                    className="rounded-xl w-20"
                  />
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="rounded-xl text-xs shrink-0"
                    onClick={async () => {
                      if (!selectedCohort) return;
                      try {
                        await api.updateCohortSettings(selectedCohort, { max_submissions_per_ip: maxSubmissionsPerIp });
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
                className="gap-1 text-xs rounded-full"
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
            {questionGroups.map((g, gi) => (
              <div
                key={g.id}
                className="flex items-center gap-3 bg-gray-50/80 rounded-lg px-3 py-2"
              >
                <Input
                  value={g.id}
                  onChange={(e) => {
                    const oldId = g.id;
                    const next = [...questionGroups];
                    next[gi] = { ...g, id: e.target.value };
                    setQuestionGroups(next);
                    setQuestions(
                      questions.map((q) =>
                        q.group === oldId ? { ...q, group: e.target.value } : q
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
                    const removedId = questionGroups[gi].id;
                    setQuestionGroups(
                      questionGroups.filter((_, i) => i !== gi)
                    );
                    setQuestions(
                      questions.map((q) =>
                        q.group === removedId ? { ...q, group: undefined } : q
                      )
                    );
                  }}
                  className="h-8 w-8 p-0 text-brand-red/60 hover:text-brand-red shrink-0"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              </div>
            ))}
          </CardContent>
        </Card>

        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-medium text-brand-blue">
            Questions ({questions.length})
          </CardTitle>
          <Button
            size="sm"
            onClick={addQuestion}
            className="gap-1.5 bg-brand-blue hover:bg-brand-blue/90 rounded-full text-xs px-4"
          >
            <Plus className="h-3.5 w-3.5" /> Add Question
          </Button>
        </div>

        <div className="space-y-3">
          {questions.map((q, i) => (
            <QuestionEditor
              key={q.id + i}
              question={q}
              index={i}
              total={questions.length}
              allQuestions={questions}
              availableGroups={questionGroups}
              onChange={(updated) => updateQuestion(i, updated)}
              onDelete={() => deleteQuestion(i)}
              onMoveUp={() => moveQuestion(i, i - 1)}
              onMoveDown={() => moveQuestion(i, i + 1)}
            />
          ))}
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
            disabled={saving || !selectedCohort}
            className="gap-2 bg-brand-teal hover:bg-brand-teal/90 rounded-full px-8 shadow-sm"
          >
            {saving ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Save className="h-4 w-4" />
            )}
            {saving ? "Saving..." : "Save Survey"}
          </Button>
          {activeVersion && (
            <Badge variant="outline" className="text-xs font-mono border-brand-blue/20 text-brand-blue/60">
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
                saveMessage.includes("Saved") || saveMessage.includes("Restored")
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
      </main>
    </div>
  );
}
