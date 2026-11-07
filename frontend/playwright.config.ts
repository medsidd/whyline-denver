import { defineConfig } from "@playwright/test";

// Unit-style tests of pure functions; no browser or dev server needed.
export default defineConfig({
  testDir: "./tests",
  reporter: "list",
});
