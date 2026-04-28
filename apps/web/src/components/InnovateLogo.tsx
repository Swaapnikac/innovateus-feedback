"use client";

import Image from "next/image";

interface InnovateLogoProps {
  className?: string;
  size?: "sm" | "md" | "lg";
  variant?: "color" | "white";
}

const INNOVATEUS_HOMEPAGE = "https://innovate-us.org/";

export function InnovateLogo({ className = "", size = "md", variant = "color" }: InnovateLogoProps) {
  const heights = { sm: 36, md: 44, lg: 56 };
  const widths = { sm: 180, md: 220, lg: 280 };
  const h = heights[size];
  const w = widths[size];

  const inner =
    variant === "white" ? (
      <span
        className={`font-sans font-medium tracking-tight ${
          size === "sm" ? "text-lg" : size === "md" ? "text-2xl" : "text-3xl"
        } text-white ${className}`}
      >
        innovate<span className="text-brand-yellow">(</span>us<span className="text-brand-yellow">)</span>
      </span>
    ) : (
      <Image
        src="/images/logo.png"
        alt="InnovateUS"
        width={w}
        height={h}
        className={className}
        priority
      />
    );

  return (
    <a
      href={INNOVATEUS_HOMEPAGE}
      target="_blank"
      rel="noopener noreferrer"
      aria-label="InnovateUS homepage (opens in a new tab)"
      className="inline-block rounded-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-blue"
    >
      {inner}
    </a>
  );
}
