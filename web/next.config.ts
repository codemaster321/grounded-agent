import type { NextConfig } from "next";

// The browser only talks to this server; /api is forwarded to FastAPI, so the
// session cookie stays first-party and no CORS setup is needed.
const nextConfig: NextConfig = {
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${process.env.API_URL ?? "http://127.0.0.1:8000"}/api/:path*` }];
  },
};

export default nextConfig;
