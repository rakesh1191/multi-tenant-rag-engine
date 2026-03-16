/** @type {import('next').NextConfig} */
const nextConfig = {
  // Standalone output bundles only required files for minimal Docker image
  output: 'standalone',
};

export default nextConfig;
