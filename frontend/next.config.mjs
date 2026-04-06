/** @type {import('next').NextConfig} */
const nextConfig = {
  experimental: {
    workerThreads: true,
    webpackBuildWorker: false,
  },
  images: {
    remotePatterns: [
      {
        protocol: 'https',
        hostname: 'avatars.githubusercontent.com',
      },
      {
        protocol: 'https',
        hostname: 'avatars.githubusercontent.com',
        pathname: '/**',
      },
    ],
  },
};

export default nextConfig;
