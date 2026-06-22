import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// Read-only dashboard SPA (Phase 6 · B2). Dev talks to the FastAPI read API on :8000 via
// CORS (see VITE_API_BASE in src/api.ts); prod is served same-origin by FastAPI from dist/.
export default defineConfig({
  plugins: [react()],
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: "./src/test/setup.ts",
    css: true,
  },
});
