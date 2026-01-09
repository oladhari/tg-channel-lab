import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Required for the Dockerfile runtime (node server.js from .next/standalone)
  output: "standalone",

  // Keep your dev-origin allowlist
  allowedDevOrigins: [
    "http://170.64.232.77:3000",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
  ],

  // Still supported in Next 16 (if you want to allow TS errors during build)
  typescript: {
    ignoreBuildErrors: true,
  },
};

export default nextConfig;
