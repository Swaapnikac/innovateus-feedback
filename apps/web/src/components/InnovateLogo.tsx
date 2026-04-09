"use client";

import Image from "next/image";

interface InnovateLogoProps {
  className?: string;
  size?: "sm" | "md" | "lg";
  variant?: "color" | "white";
}

export function InnovateLogo({ className = "", size = "md", variant = "color" }: InnovateLogoProps) {
  const heights = { sm: 36, md: 44, lg: 56 };
  const widths = { sm: 180, md: 220, lg: 280 };
  const h = heights[size];
  const w = widths[size];

  if (variant === "white") {
    return (
      <span className={`font-sans font-medium tracking-tight ${size === "sm" ? "text-lg" : size === "md" ? "text-2xl" : "text-3xl"} text-white ${className}`}>
        innovate<span className="text-brand-yellow">(</span>us<span className="text-brand-yellow">)</span>
      </span>
    );
  }

  return (
    <Image
      src="/images/logo.png"
      alt="InnovateUS"
      width={w}
      height={h}
      className={className}
      priority
    />
  );
}
