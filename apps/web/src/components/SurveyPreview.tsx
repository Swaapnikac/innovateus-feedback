"use client";

import { useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Eye, ChevronLeft, ChevronRight } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { ProgressBar } from "@/components/ProgressBar";
import { QuestionCard } from "@/components/QuestionCard";
import { ChoiceQuestion } from "@/components/ChoiceQuestion";
import { MultiSelectQuestion } from "@/components/MultiSelectQuestion";
import { NpsQuestion } from "@/components/NpsQuestion";
import { SliderQuestion } from "@/components/SliderQuestion";
import { MatrixQuestion } from "@/components/MatrixQuestion";
import { RankingQuestion } from "@/components/RankingQuestion";
import { YesNoQuestion } from "@/components/YesNoQuestion";
import { DropdownQuestion, ShortTextQuestion, DateQuestion } from "@/components/SimpleQuestions";
import { Textarea } from "@/components/ui/textarea";
import type { SurveyQuestion, QuestionGroup } from "@/lib/api";
import { MAX_ANSWER_CHARS } from "@/lib/limits";

interface SurveyPreviewProps {
  title: string;
  questions: SurveyQuestion[];
  questionGroups: QuestionGroup[];
}

export function SurveyPreview({ title, questions, questionGroups }: SurveyPreviewProps) {
  const [step, setStep] = useState(0);
  const [previewAnswers, setPreviewAnswers] = useState<Record<string, { value: string; multiValues: string[] }>>({});

  // Visible questions respect conditional logic
  const visible = questions.filter((q) => {
    if (!q.condition) return true;
    const dep = previewAnswers[q.condition.question_id];
    if (!dep) return false;
    if (q.condition.operator === "not_equals") return dep.value !== q.condition.value;
    return dep.value === q.condition.value;
  });

  if (visible.length === 0) {
    return (
      <Card className="bg-white border-0 shadow-sm rounded-2xl">
        <CardContent className="py-12 text-center">
          <Eye className="h-8 w-8 text-brand-blue/20 mx-auto mb-2" />
          <p className="text-sm text-brand-blue/40">No questions to preview yet.</p>
        </CardContent>
      </Card>
    );
  }

  const boundedStep = Math.min(step, visible.length - 1);
  const current = visible[boundedStep];
  const ans = previewAnswers[current.id] || { value: "", multiValues: [] };
  const setValue = (v: string) =>
    setPreviewAnswers((prev) => ({ ...prev, [current.id]: { ...ans, value: v } }));
  const setMulti = (v: string[]) =>
    setPreviewAnswers((prev) => ({ ...prev, [current.id]: { ...ans, multiValues: v } }));

  const groupLabel = current.group
    ? questionGroups.find((g) => g.id === current.group)?.label
    : null;

  return (
    <div className="bg-brand-light-blue/40 rounded-2xl p-4 border border-brand-blue/10">
      <div className="flex items-center gap-2 mb-3">
        <Eye className="h-4 w-4 text-brand-blue/50" />
        <span className="text-xs font-semibold text-brand-blue/40 uppercase tracking-wider">
          Live Preview
        </span>
        <Badge variant="outline" className="text-[10px] border-brand-blue/15 text-brand-blue/40 ml-auto">
          {title || "Untitled"}
        </Badge>
      </div>

      <div className="space-y-4">
        <ProgressBar current={boundedStep + 1} total={visible.length} />

        {groupLabel && (
          <p className="text-[10px] font-semibold text-brand-dark-yellow uppercase tracking-widest text-center">
            {groupLabel}
          </p>
        )}

        <QuestionCard
          text={current.text || "(untitled question)"}
          description={current.description}
          required={current.required}
        >
          {(current.type === "rating" || current.type === "mcq") && (
            <ChoiceQuestion
              type={current.type}
              options={current.options || []}
              value={ans.value}
              onChange={setValue}
            />
          )}
          {current.type === "multi" && (
            <MultiSelectQuestion
              options={(current.options || []).map(String)}
              value={ans.multiValues}
              onChange={setMulti}
            />
          )}
          {current.type === "nps" && (
            <NpsQuestion value={ans.value} onChange={setValue} labels={current.labels} />
          )}
          {current.type === "slider" && (
            <SliderQuestion
              value={ans.value}
              onChange={setValue}
              min={current.scale_min}
              max={current.scale_max}
              step={current.scale_step}
              labels={current.labels}
            />
          )}
          {current.type === "matrix" && (
            <MatrixQuestion
              rows={current.rows || []}
              columns={current.options || []}
              value={ans.value}
              onChange={setValue}
            />
          )}
          {current.type === "ranking" && (
            <RankingQuestion options={current.options || []} value={ans.value} onChange={setValue} />
          )}
          {current.type === "yesno" && <YesNoQuestion value={ans.value} onChange={setValue} />}
          {current.type === "dropdown" && (
            <DropdownQuestion options={current.options || []} value={ans.value} onChange={setValue} />
          )}
          {current.type === "short_text" && <ShortTextQuestion value={ans.value} onChange={setValue} />}
          {current.type === "date" && <DateQuestion value={ans.value} onChange={setValue} />}
          {current.type === "open" && (
            <div className="space-y-2">
              <Textarea
                value={ans.value}
                onChange={(e) => setValue(e.target.value.slice(0, MAX_ANSWER_CHARS))}
                placeholder="Participant can type or speak here..."
                className="min-h-[100px] resize-y text-base"
                maxLength={MAX_ANSWER_CHARS}
              />
              {current.voice_eligible && (
                <p className="text-[11px] text-brand-blue/40 italic">
                  Voice input is enabled for this question in the live survey.
                </p>
              )}
            </div>
          )}
        </QuestionCard>

        <div className="flex justify-between">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setStep(Math.max(0, boundedStep - 1))}
            disabled={boundedStep === 0}
            className="gap-1.5 border-brand-blue/15 text-brand-blue/60 text-xs"
          >
            <ChevronLeft className="h-3.5 w-3.5" />
            Back
          </Button>
          <span className="text-xs text-brand-blue/40 self-center">
            {boundedStep + 1} / {visible.length}
          </span>
          <Button
            size="sm"
            onClick={() => setStep(Math.min(visible.length - 1, boundedStep + 1))}
            disabled={boundedStep >= visible.length - 1}
            className="gap-1.5 bg-brand-blue hover:bg-brand-blue/90 text-xs"
          >
            Next
            <ChevronRight className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>
    </div>
  );
}
