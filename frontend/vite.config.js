import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// https://vite.dev/config/
export default defineConfig(({ command }) => ({
  plugins: [react()],

  // При сборке файлы подключает Django из /static/..., в разработке с корня.
  base: command === "build" ? "/static/webpages/booking/" : "/",

  server: {
    proxy: {
      "/api": "http://127.0.0.1:8000",
      "/media": "http://127.0.0.1:8000",
    },
  },

  build: {
    // Готовая форма кладётся прямо в статику приложения webpages.
    outDir: "../webpages/static/webpages/booking",
    emptyOutDir: true,
    cssCodeSplit: false,
    rollupOptions: {
      input: "src/main.jsx",
      output: {
        // Фиксированные имена, чтобы Django знал, что подключать.
        entryFileNames: "booking.js",
        assetFileNames: "booking[extname]",
      },
    },
  },
}));
