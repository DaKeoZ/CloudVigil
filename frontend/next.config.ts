import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Transpiler Tremor et Recharts pour le SSR Next.js 14
  transpilePackages: ["@tremor/react"],
};

export default nextConfig;
