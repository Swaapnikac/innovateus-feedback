"use client";

import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Plus, Loader2, CheckCircle2, Copy, ExternalLink } from "lucide-react";
import { QRCodeSVG } from "qrcode.react";
import { api } from "@/lib/api";

export interface CreatedCohort {
  id: string;
  // Optional human-friendly slug like ``generative-ai`` — when present we
  // build the share link from this so participants see a clean URL instead
  // of the raw UUID.
  slug: string | null;
  name: string;
  course_name: string;
  program_type: string | null;
  max_submissions_per_ip: number;
  created_at: string;
}

interface NewSurveyDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated: (cohort: CreatedCohort) => void;
  primaryActionLabel?: string;
  onPrimaryAction?: (cohort: CreatedCohort) => void;
}

export function NewSurveyDialog({
  open,
  onOpenChange,
  onCreated,
  primaryActionLabel = "Open Survey in Editor",
  onPrimaryAction,
}: NewSurveyDialogProps) {
  const [programType, setProgramType] = useState("");
  const [surveyName, setSurveyName] = useState("");
  // Optional pretty slug for the survey URL. Auto-suggested from the
  // survey name unless the admin types something custom (we track that
  // with ``slugTouched`` so we don't overwrite manual edits).
  const [slug, setSlug] = useState("");
  const [slugTouched, setSlugTouched] = useState(false);
  const [creating, setCreating] = useState(false);
  const [validationError, setValidationError] = useState("");
  const [created, setCreated] = useState<CreatedCohort | null>(null);
  const [linkCopied, setLinkCopied] = useState(false);

  // Mirror the backend's slugify helper so the preview matches what the
  // server will accept. Lowercase, hyphens, no leading/trailing dashes.
  const suggestSlug = (value: string): string => {
    return value
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .slice(0, 60);
  };

  const reset = () => {
    setProgramType("");
    setSurveyName("");
    setSlug("");
    setSlugTouched(false);
    setCreating(false);
    setValidationError("");
    setCreated(null);
    setLinkCopied(false);
  };

  const handleClose = (next: boolean) => {
    if (!next) reset();
    onOpenChange(next);
  };

  // Use the cohort's slug when present so the QR/share link is the
  // friendly form (``/c/generative-ai``); fall back to UUID otherwise.
  const getSurveyLink = (cohort: CreatedCohort) => {
    const segment = cohort.slug || cohort.id;
    return `${typeof window !== "undefined" ? window.location.origin : ""}/c/${segment}`;
  };

  const copyLink = (cohort: CreatedCohort) => {
    navigator.clipboard.writeText(getSurveyLink(cohort));
    setLinkCopied(true);
    setTimeout(() => setLinkCopied(false), 2000);
  };

  const handleCreate = async () => {
    if (!programType || !surveyName.trim()) {
      setValidationError(
        !programType && !surveyName.trim()
          ? "Please select a program type and enter a survey name."
          : !programType
            ? "Please select a program type."
            : "Please enter a survey name."
      );
      return;
    }
    const trimmedSlug = slug.trim().toLowerCase();
    // Empty is fine (cohort just resolves by UUID); otherwise enforce the
    // same regex the backend uses so we surface validation client-side.
    if (trimmedSlug && !/^[a-z0-9](?:[a-z0-9-]{0,58}[a-z0-9])?$/.test(trimmedSlug)) {
      setValidationError(
        "Slug must be 2-60 chars: lowercase letters, digits, and hyphens (no leading/trailing dash)."
      );
      return;
    }
    setValidationError("");
    setCreating(true);
    try {
      const result = await api.createCohort(
        surveyName.trim(),
        programType,
        trimmedSlug || undefined
      );
      const cohort = result as CreatedCohort;
      setCreated(cohort);
      onCreated(cohort);
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to create survey");
    } finally {
      setCreating(false);
    }
  };

  const handlePrimaryAction = () => {
    if (!created) return;
    if (onPrimaryAction) {
      onPrimaryAction(created);
    }
    handleClose(false);
  };

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-md">
        {created ? (
          <>
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <CheckCircle2 className="h-5 w-5 text-brand-teal" />
                Survey Created
              </DialogTitle>
            </DialogHeader>
            <div className="space-y-5 py-2">
              <div className="flex justify-center">
                <div className="bg-white rounded-2xl p-4 border border-brand-blue/10 shadow-sm">
                  <QRCodeSVG
                    value={getSurveyLink(created)}
                    size={180}
                    level="M"
                    bgColor="#ffffff"
                    fgColor="#124D8F"
                  />
                </div>
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs font-semibold text-brand-blue/40 uppercase tracking-wider">
                  Survey Link
                </Label>
                <div className="flex items-center gap-2">
                  <Input
                    readOnly
                    value={getSurveyLink(created)}
                    className="rounded-xl text-xs font-mono"
                  />
                  <Button
                    size="sm"
                    variant="outline"
                    className="rounded-xl shrink-0 gap-1.5"
                    onClick={() => copyLink(created)}
                  >
                    <Copy className="h-3.5 w-3.5" />
                    {linkCopied ? "Copied!" : "Copy"}
                  </Button>
                </div>
              </div>
              <p className="text-[11px] text-brand-blue/30 text-center">
                Share the link or QR code with participants. Each survey has a unique link.
              </p>
            </div>
            <DialogFooter className="flex-col sm:flex-row gap-2">
              <Button
                variant="outline"
                onClick={() => handleClose(false)}
                className="border-brand-blue/15 text-brand-blue/60"
              >
                Done
              </Button>
              <Button
                onClick={handlePrimaryAction}
                className="bg-brand-blue hover:bg-brand-blue/90 gap-2"
              >
                <ExternalLink className="h-4 w-4" />
                {primaryActionLabel}
              </Button>
            </DialogFooter>
          </>
        ) : (
          <>
            <DialogHeader>
              <DialogTitle>Create New Survey</DialogTitle>
            </DialogHeader>
            <div className="space-y-4 py-2">
              <div className="space-y-1.5">
                <Label className="text-xs font-semibold text-brand-blue/40 uppercase tracking-wider">
                  Program Type <span className="text-brand-red">*</span>
                </Label>
                <Select
                  value={programType}
                  onValueChange={(v) => {
                    setProgramType(v);
                    setValidationError("");
                  }}
                >
                  <SelectTrigger className="rounded-xl">
                    <SelectValue placeholder="Select program type..." />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="course">Course</SelectItem>
                    <SelectItem value="workshop">Workshop</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs font-semibold text-brand-blue/40 uppercase tracking-wider">
                  Survey Name <span className="text-brand-red">*</span>
                </Label>
                <Input
                  placeholder="e.g. Using Generative AI at Work — Fall 2026"
                  value={surveyName}
                  onChange={(e) => {
                    const next = e.target.value;
                    setSurveyName(next);
                    if (!slugTouched) {
                      setSlug(suggestSlug(next));
                    }
                    setValidationError("");
                  }}
                  className="rounded-xl"
                />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs font-semibold text-brand-blue/40 uppercase tracking-wider">
                  Survey URL slug{" "}
                  <span className="text-brand-blue/30 font-normal normal-case">(optional)</span>
                </Label>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-brand-blue/50 font-mono">/c/</span>
                  <Input
                    placeholder="e.g. generative-ai"
                    value={slug}
                    onChange={(e) => {
                      setSlugTouched(true);
                      setSlug(e.target.value);
                      setValidationError("");
                    }}
                    onBlur={() => {
                      // Normalise on blur so the field always shows a
                      // server-acceptable form (no spaces, lowercase).
                      if (slug) setSlug(suggestSlug(slug));
                    }}
                    className="rounded-xl font-mono"
                  />
                </div>
                <p className="text-[11px] text-brand-blue/40">
                  Leave blank to use a random ID. Lowercase letters, digits, and hyphens only.
                </p>
              </div>
              {validationError && (
                <p className="text-sm text-brand-red">{validationError}</p>
              )}
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => handleClose(false)}>
                Cancel
              </Button>
              <Button
                onClick={handleCreate}
                disabled={creating}
                className="bg-brand-blue hover:bg-brand-blue/90 gap-2"
              >
                {creating ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Plus className="h-4 w-4" />
                )}
                Create New Survey
              </Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
