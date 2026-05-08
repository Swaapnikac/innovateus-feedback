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
  // Reverse-proxy the FastAPI backend through this Next.js server so the
  // browser only ever talks to one origin. With API and frontend on
  // different parent domains, the API's Set-Cookie was bound to the API
  // host and never made it back to the frontend — which broke the
  // /iu-ops-9k2p middleware and forced cross-site cookie rules that
  // strict browsers (Safari, Brave) refuse outright. Routing /api/v1/*
  // through here makes every cookie first-party.
  //
  // ``API_PROXY_TARGET`` is intentionally NOT prefixed with NEXT_PUBLIC_
  // so it is only available in the Node runtime (rewrites resolve here)
  // and never bundled into the client JS. The browser never sees the
  // upstream URL.
  async rewrites() {
    const target = process.env.API_PROXY_TARGET;
    if (!target) {
      // No proxy configured (typical in local dev where the survey hits
      // the API directly via NEXT_PUBLIC_API_URL=http://localhost:8009).
      return [];
    }
    const cleaned = target.replace(/\/+$/, "");
    return [
      { source: "/api/v1/:path*", destination: `${cleaned}/v1/:path*` },
    ];
  },
};

export default withNextIntl(nextConfig);
