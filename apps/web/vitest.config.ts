import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    // Playwright specs live in e2e/ and run with `pnpm e2e`.
    include: ["src/**/*.test.ts", "src/**/*.test.tsx"],
  },
});
