/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";

    return [
      {
        source: "/api/:path*",
        destination: `${apiBaseUrl}/api/:path*`
      },
      {
        source: "/health",
        destination: `${apiBaseUrl}/health`
      }
    ];
  }
};

export default nextConfig;
