/**
 * Next.js config — DocuMind frontend.
 *
 * Proxies /api/* to the API gateway so the browser stays same-origin.
 * Keeps vanilla CSS (no CSS Modules / CSS-in-JS globally; per-component
 * CSS modules remain opt-in).
 */

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  experimental: {
    typedRoutes: false,
  },
  async rewrites() {
    const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8080';
    return [
      {
        source: '/api/:path*',
        destination: `${apiBase}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
