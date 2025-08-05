/** @type {import('next').NextConfig} */
const nextConfig = {
  experimental: {
    serverActions: {
      allowedOrigins: ['localhost:3000', '127.0.0.1:3000']
    },
  },
  images: {
    domains: ['images.unsplash.com'],
  },
  webpack: (config, { isServer }) => {
    // Optimize for graph algorithms and large datasets
    config.experiments = {
      ...config.experiments,
      topLevelAwait: true,
    };
    
    if (!isServer) {
      config.resolve.fallback = {
        ...config.resolve.fallback,
        fs: false,
        net: false,
        tls: false,
      };
    }
    
    return config;
  },
};

module.exports = nextConfig;