/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  poweredByHeader: false,
  reactStrictMode: true,
  transpilePackages: ["@crs/auth", "@crs/api", "@crs/ui"],
  experimental: { serverActions: { allowedOrigins: ["staff.credit.local"] } },
};

export default nextConfig;
