/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  poweredByHeader: false,
  reactStrictMode: true,
  transpilePackages: ["@crs/auth", "@crs/api", "@crs/ui"],
  experimental: { serverActions: { allowedOrigins: [process.env.PORTAL_BASE_URL ? new URL(process.env.PORTAL_BASE_URL).host : "staff.credit.local"] } },
};

export default nextConfig;
