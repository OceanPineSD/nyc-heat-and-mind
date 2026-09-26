import { resolve } from "node:path";
import { defineConfig } from "vite";

export default defineConfig({
  worker: { format: "es" },
  build: {
    rollupOptions: {
      input: {
        map: resolve(__dirname, "index.html"),
        overlap: resolve(__dirname, "overlap/index.html"),
        methods: resolve(__dirname, "methods/index.html"),
      },
    },
  },
});
