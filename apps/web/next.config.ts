import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";

const withNextIntl = createNextIntlPlugin("./src/lib/i18n.ts");

// Defense-in-depth headers applied to every response. None of these are
// substitutes for proper auth or input validation — they just close the
// usual browser-side blast radius if something else goes wrong.
const SECURITY_HEADERS = [
  // Force HTTPS for two years on this host and all subdomains.
  {
    key: "Strict-Transport-Security",
    value: "max-age=63072000; includeSubDomains; preload",
  },
  // Stop the browser from second-guessing declared MIME types.
  { key: "X-Content-Type-Options", value: "nosniff" },
  // Block this app from being framed by other sites (clickjacking).
  { key: "X-Frame-Options", value: "DENY" },
  // Don't leak full URLs to third-party origins via the Referer header.
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  // Microphone is needed for the voice survey on the same origin only;
  // everything else is denied.
  {
    key: "Permissions-Policy",
    value: "camera=(), geolocation=(), microphone=(self), payment=()",
  },
];

const nextConfig: NextConfig = {
  images: {
    unoptimized: true,
  },
  // Strip console.* calls (except .error) at build time in production.
  // Keeps `console.error` so genuine bug reports still surface in
  // browser devtools, but removes log noise that could leak internal
  // state or user content during a soft launch.
  compiler: {
    removeConsole:
      process.env.NODE_ENV === "production" ? { exclude: ["error"] } : false,
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: SECURITY_HEADERS,
      },
    ];
  },
};

export default withNextIntl(nextConfig);
