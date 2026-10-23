import { defineConfig, devices } from '@playwright/test';

/**
 * FinAlly E2E configuration.
 *
 * - With BASE_URL set (Docker: http://app:8000), tests run against that server as-is.
 * - Without it, Playwright starts the backend itself on port 8003 (E2E_PORT) via scripts/start-server.mjs:
 *   fresh throwaway DB, LLM_MOCK=true, SIM_SEED=42, STATIC_DIR=<repo>/frontend/out.
 *   Build the frontend first (`npm run build:frontend`).
 *
 * FinAlly is single-user, so every test shares one portfolio. Tests therefore run serially
 * (one worker) and use relative assertions; files run in alphabetical order, which only
 * matters for 01-fresh-start (it needs the untouched DB).
 */
const externalBaseURL = process.env.BASE_URL;
const baseURL = externalBaseURL ?? `http://localhost:${process.env.E2E_PORT ?? '8003'}`;

export default defineConfig({
  testDir: './tests',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  forbidOnly: !!process.env.CI,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL,
    viewport: { width: 1600, height: 1000 },
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'], viewport: { width: 1600, height: 1000 } } }],
  webServer: externalBaseURL
    ? undefined
    : {
        command: 'node scripts/start-server.mjs',
        url: `${baseURL}/api/health`,
        reuseExistingServer: false,
        timeout: 120_000,
        stdout: 'ignore', // uvicorn access log; errors and tracebacks go to stderr
        stderr: 'pipe',
      },
});
