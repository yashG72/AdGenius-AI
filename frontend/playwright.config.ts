import { defineConfig, devices } from "@playwright/test"

/**
 * End-to-end smoke test against a running stack:
 *   backend API on :8000, Celery worker, Redis, Qdrant, PostgreSQL, and this app on :3000
 *   (npm run build && npm start).  Run with: npm run test:e2e
 */
export default defineConfig({
  testDir: "./e2e",
  timeout: 120_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000",
    viewport: { width: 1440, height: 900 },
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } }],
})
