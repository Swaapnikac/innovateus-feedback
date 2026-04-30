"use client";

import { useEffect, useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogDescription,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Loader2, AlertTriangle } from "lucide-react";
import { api } from "@/lib/api";

// Mirrors the backend ``SLUG_RE`` and ``is_valid_slug`` so the live preview
// matches exactly what the server will accept. Updating one without the
// other will desync the UX.
const SLUG_RE = /^[a-z0-9](?:[a-z0-9-]{0,58}[a-z0-9])?$/;

const slugify = (value: string): string =>
  value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 60);

interface EditSurveyLinkDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  cohortId: string;
  /** Current cohort name; used to seed the slug on first-time assignment. */
  cohortName: string;
  /** ``null`` when the cohort has no slug yet (first-time assign mode). */
  currentSlug: string | null;
  /** Existing IP cap; the endpoint requires this in the same request body. */
  maxSubmissionsPerIp: number;
  onUpdated: (newSlug: string) => void;
}

/**
 * Dialog that handles **both** assigning a slug to a cohort that has none and
 * renaming the slug of one that does. The dialog adapts its title and warning
 * banner based on which mode it is in:
 *
 * - First-time assignment: no warning is shown (no old links exist to break).
 * - Rename: amber warning explaining that old QR codes / links keep working
 *   forever as redirects (backed by ``previous_slugs`` on the server).
 */
export function EditSurveyLinkDialog({
  open,
  onOpenChange,
  cohortId,
  cohortName,
  currentSlug,
  maxSubmissionsPerIp,
  onUpdated,
}: EditSurveyLinkDialogProps) {
  const isRename = !!currentSlug;
  const [slug, setSlug] = useState<string>(currentSlug ?? "");
  const [slugTouched, setSlugTouched] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // When the dialog re-opens for a different cohort, reset state so it shows
  // the right starting slug instead of stale data from a previous edit.
  useEffect(() => {
    if (open) {
      setSlug(currentSlug ?? slugify(cohortName));
      setSlugTouched(false);
      setError(null);
    }
  }, [open, currentSlug, cohortName]);

  const normalized = slug.trim().toLowerCase();
  const validFormat = SLUG_RE.test(normalized);
  const isDifferent = normalized !== (currentSlug ?? "");
  const canSave = validFormat && isDifferent && !saving;

  async function handleSave() {
    if (!canSave) return;
    setSaving(true);
    setError(null);
    try {
      const result = await api.updateCohortSettings(cohortId, {
        max_submissions_per_ip: maxSubmissionsPerIp,
        slug: normalized,
      });
      const finalSlug = result.slug ?? normalized;
      onUpdated(finalSlug);
      onOpenChange(false);
    } catch (e) {
      const message = e instanceof Error ? e.message : "Failed to update.";
      // The backend surfaces clean messages for 400 (format) and 409
      // (collision); pass them through verbatim so the admin sees them.
      setError(message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => (saving ? null : onOpenChange(next))}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{isRename ? "Edit Survey URL" : "Add Custom URL"}</DialogTitle>
          <DialogDescription>
            {isRename
              ? "Change the public URL of this survey. Old links keep working."
              : "Pick a friendly URL for this survey instead of the long ID."}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3 py-2">
          {isRename && (
            <div className="text-sm text-muted-foreground">
              Current URL: <code className="rounded bg-muted px-1 py-0.5">/c/{currentSlug}</code>
            </div>
          )}

          <div className="space-y-1.5">
            <Label htmlFor="slug-input">New URL slug</Label>
            <div className="flex items-center gap-1 text-sm">
              <span className="text-muted-foreground">/c/</span>
              <Input
                id="slug-input"
                autoFocus
                value={slug}
                onChange={(e) => {
                  setSlug(e.target.value);
                  setSlugTouched(true);
                  setError(null);
                }}
                onBlur={() => {
                  if (slug) setSlug(slugify(slug));
                }}
                placeholder="responsible-ai-2026"
                className="font-mono"
                aria-invalid={!validFormat && slug.length > 0}
                aria-describedby="slug-help"
                disabled={saving}
              />
            </div>
            <p id="slug-help" className="text-xs text-muted-foreground">
              Lowercase letters, numbers, and hyphens. 2 to 60 characters. No spaces.
            </p>
            {slug && !validFormat && (
              <p className="text-xs text-red-600">
                That format is not valid. Try something like <code>my-course-2026</code>.
              </p>
            )}
          </div>

          <div className="rounded-md border bg-muted/50 px-3 py-2 text-xs">
            <span className="text-muted-foreground">Preview:</span>{" "}
            <code className="font-mono">
              {typeof window !== "undefined" ? window.location.origin : ""}/c/
              {normalized || "..."}
            </code>
          </div>

          {isRename && slugTouched && isDifferent && validFormat && (
            <div
              role="status"
              className="flex gap-2 rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900"
            >
              <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0" aria-hidden="true" />
              <div>
                <strong>Heads up:</strong> Renaming changes the URL. Existing QR codes and shared
                links to <code className="font-mono">/c/{currentSlug}</code> will keep working as
                redirects, but please update any printed material when convenient.
              </div>
            </div>
          )}

          {error && (
            <div role="alert" className="rounded-md border border-red-300 bg-red-50 p-3 text-sm text-red-800">
              {error}
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={saving}>
            Cancel
          </Button>
          <Button onClick={handleSave} disabled={!canSave}>
            {saving ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" />
                Saving...
              </>
            ) : isRename ? (
              "Save URL"
            ) : (
              "Add URL"
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
