import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/chat/voice", // 前端直接访问的路径
        destination: "http://localhost:8000/chat/voice", // 后端实际路径
      },
    ];
  },
};

export default nextConfig;