/**
 * Next.js config — DocuMind frontend.
 *
 * Proxies /api/* to the API gateway so the browser stays same-origin.
 * Keeps vanilla CSS (no CSS Modules / CSS-in-JS globally; per-component
 * CSS modules remain opt-in).
 */

/** @type {import('next').NextConfig} */
const nextConfig = {
  distDir: process.env.NEXT_DIST_DIR || '.next',
  reactStrictMode: true,
  poweredByHeader: false,
  experimental: {
    typedRoutes: false,
  },
  async rewrites() {
    const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8080';
    return [
      {
        // Keep frontend-owned App Router APIs local. Everything else
        // still proxies to the gateway.
        source: '/api/:path((?!v1/tts(?:/|$)|v1/sidecar(?:/|$)).*)',
        destination: `${apiBase}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
