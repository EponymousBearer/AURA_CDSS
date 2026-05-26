/** @type {import('next').NextConfig} */
const nextConfig = {
  // NOTE: do NOT set output: 'standalone' on Vercel — Vercel optimizes the build
  // itself, and 'standalone' can produce output Vercel doesn't serve (404).
  // Re-add only for self-hosted/Docker frontend deployments.
  images: {
    unoptimized: true,
  },
  eslint: {
    ignoreDuringBuilds: true,
  },
  typescript: {
    ignoreBuildErrors: true,
  },
}

module.exports = nextConfig
