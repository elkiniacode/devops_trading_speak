import type { NextConfig } from "next";

// Static export: FastAPI serves frontend/out on the same origin as /api.
const nextConfig: NextConfig = {
  output: "export",
  // /charla/sala/ -> out/charla/sala/index.html, which StaticFiles(html=True) serves as-is.
  trailingSlash: true,
  images: { unoptimized: true },
  reactStrictMode: true,
  // Don't let `next dev` write AGENTS.md into the repo.
  agentRules: false,
  devIndicators: false,
};

export default nextConfig;
