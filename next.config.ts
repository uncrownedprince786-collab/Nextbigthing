import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // The workspace folder name contains a space and a parent directory that holds another
  // repository, so pin the bundler root to this project instead of guessing upward.
  turbopack: {
    root: __dirname,
  },

  // The replacement interface was built under /preview and promoted to the public routes on
  // 2026-10-20 (UI-CUTOVER-RUNBOOK-2026-10-18 §6). These are step 4 of that procedure: permanent
  // redirects so every link shared while the journey lived under /preview still resolves, rather
  // than 404ing on a path that was real last week.
  //
  // 308 rather than 302, because the move is permanent; `permanent: true` is Next's spelling of
  // it. Ordering matters: the most specific path comes first, so `/preview/asset/X/decision` is
  // not swallowed by the `/preview/asset/:symbol` rule beneath it.
  async redirects() {
    return [
      { source: "/preview/asset/:symbol/decision", destination: "/asset/:symbol/decision", permanent: true },
      { source: "/preview/asset/:symbol/research", destination: "/asset/:symbol", permanent: true },
      { source: "/preview/asset/:symbol", destination: "/asset/:symbol", permanent: true },
      { source: "/preview/predictions", destination: "/predictions", permanent: true },
      { source: "/preview/status", destination: "/status", permanent: true },
      { source: "/preview/markets/:slug", destination: "/markets/:slug", permanent: true },
      { source: "/preview/markets", destination: "/markets", permanent: true },
      { source: "/preview", destination: "/", permanent: true },
    ];
  },
};

export default nextConfig;
