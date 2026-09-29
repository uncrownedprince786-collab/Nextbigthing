import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // The workspace folder name contains a space and a parent directory that holds another
  // repository, so pin the bundler root to this project instead of guessing upward.
  turbopack: {
    root: __dirname,
  },
};

export default nextConfig;
