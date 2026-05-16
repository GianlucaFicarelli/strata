import { defineConfig, mergeConfig } from "vitest/config";
import viteConfig from "./vite.config.js";

export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      environment: "jsdom",
      globals: true,
      setupFiles: ["./src/__tests__/setup.js"],
      include: ["src/__tests__/**/*.{test,spec}.{js,jsx}"],
      execArgv: ["--no-experimental-webstorage"],
      coverage: {
        provider: "v8",
        include: ["src/**/*.{js,jsx}"],
        exclude: [
          "src/__tests__/**",
          // Entry point and pure rendering shells: no standalone logic to unit-test.
          // Covered at integration/e2e level.
          "src/main.jsx",
          "src/App.jsx",
          "src/shell/FilePreview.jsx",
          "src/shell/Sidebar.jsx",
        ],
        reporter: ["text", "html", "lcov"],
        reportsDirectory: ".coverage",
        thresholds: {
          lines: 75,
          functions: 65,
          branches: 70,
          statements: 70,
        },
      },
    },
  }),
);
