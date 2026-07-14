import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: {
    chunkSizeWarningLimit: 700,
    rollupOptions: {
      output: {
        manualChunks(id) {
          const path = id.replaceAll("\\", "/");
          if (!path.includes("/node_modules/")) return undefined;
          if (
            path.includes("/node_modules/react/") ||
            path.includes("/node_modules/react-dom/") ||
            path.includes("/node_modules/scheduler/")
          ) {
            return "vendor-react";
          }
          if (path.includes("/node_modules/antd/") || path.includes("/node_modules/@ant-design/icons")) {
            return "vendor-antd";
          }
          if (
            path.includes("/node_modules/@ant-design/") ||
            path.includes("/node_modules/@rc-component/") ||
            /\/node_modules\/rc-[^/]+\//.test(path)
          ) {
            return "vendor-rc";
          }
          return "vendor";
        },
      },
    },
  },
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8765",
      "/outputs": "http://127.0.0.1:8765",
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: "./vitest.setup.ts",
  },
});
