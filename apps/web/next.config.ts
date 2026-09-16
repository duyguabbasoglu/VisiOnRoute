import path from "node:path";
import type { NextConfig } from "next";

// Hobby profile (docs/operations/hobby-deployment.md): the web host proxies
// /api/* to the API host. The browser then calls its own origin
// (NEXT_PUBLIC_API_URL=""), so the SameSite=Lax refresh cookie stays
// first-party even though web and API live on different providers.
const apiProxyTarget = process.env.API_PROXY_TARGET?.replace(/\/+$/, "");

const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  output: "standalone",
  // Pin tracing to this app so stray lockfiles in parent directories are ignored.
  outputFileTracingRoot: path.join(__dirname),
  async rewrites() {
    if (!apiProxyTarget) return [];
    return [{ source: "/api/:path*", destination: `${apiProxyTarget}/api/:path*` }];
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
        ],
      },
    ];
  },
};

export default nextConfig;
