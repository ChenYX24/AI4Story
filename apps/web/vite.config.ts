import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import tailwindcss from "@tailwindcss/vite";
import path from "node:path";

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [vue(), tailwindcss()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "src") },
  },
  server: {
    port: 5173,
    host: "127.0.0.1",
    // 开发时把后端 API / 静态资源走代理
    proxy: {
      "/api": "http://127.0.0.1:8000",
      "/outputs": "http://127.0.0.1:8000",
      "/assets/scenes": "http://127.0.0.1:8000",
      "/view": "http://127.0.0.1:8000",
      "/healthz": "http://127.0.0.1:8000",
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
    // 用 bundle/ 避免和后端 /assets/scenes 路由冲突
    assetsDir: "bundle",
  },
});
