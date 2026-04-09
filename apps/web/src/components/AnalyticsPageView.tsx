"use client";

import { useEffect } from "react";
import { initSession, trackPageView } from "@/lib/analytics";

interface AnalyticsPageViewProps {
  page: string;
  cohortId?: string;
}

export function AnalyticsPageView({ page, cohortId }: AnalyticsPageViewProps) {
  useEffect(() => {
    initSession();
    trackPageView(page, cohortId);
  }, [page, cohortId]);

  return null;
}
