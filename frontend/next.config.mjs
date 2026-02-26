/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    const apiBase = process.env.API_BASE_URL;
    if (!apiBase) {
      return [];
    }
    return [
      {
        source: "/api/:path*",
        destination: `${apiBase}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
