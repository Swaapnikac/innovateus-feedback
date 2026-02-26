"use client";

import { Shield } from "lucide-react";

export function PrivacyFooter() {
  return (
    <div className="fixed bottom-0 left-0 right-0 bg-white/80 backdrop-blur-sm border-t border-brand-blue/5 py-2.5 px-4 z-50">
      <div className="max-w-2xl mx-auto flex items-center justify-center gap-2 text-xs text-brand-blue/50">
        <Shield className="h-3 w-3 shrink-0" />
        <span>Audio is not stored. Only transcript text is saved. Your responses are anonymous.</span>
      </div>
    </div>
  );
}
