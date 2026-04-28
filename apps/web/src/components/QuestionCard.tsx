"use client";

import { Card, CardContent, CardHeader } from "@/components/ui/card";
import type { ReactNode } from "react";

interface QuestionCardProps {
  text: string;
  description?: string;
  required?: boolean;
  headingId?: string;
  descriptionId?: string;
  children: ReactNode;
}

export function QuestionCard({
  text,
  description,
  required,
  headingId,
  descriptionId,
  children,
}: QuestionCardProps) {
  return (
    <Card className="w-full max-w-3xl mx-auto bg-white border-0 shadow-sm rounded-2xl">
      <CardHeader className="pb-4">
        <h2
          id={headingId}
          className="text-lg font-serif-text text-brand-blue leading-relaxed"
        >
          {text}
          {required && (
            <span className="text-brand-red ml-1" aria-label="required">
              *
            </span>
          )}
        </h2>
        {description && (
          <p
            id={descriptionId}
            className="text-sm text-brand-blue/50 mt-1"
          >
            {description}
          </p>
        )}
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  );
}
