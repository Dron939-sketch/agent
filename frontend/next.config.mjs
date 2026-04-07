/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  experimental: {
    optimizePackageImports: ["lucide-react", "framer-motion"]
  },
  async rewrites() {
    const api = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    return [
      { source: "/api/backend/:path*", destination: `${api}/api/:path*` },
      { source: "/health", destination: `${api}/health` }
    ];
  }
};

export default nextConfig;
