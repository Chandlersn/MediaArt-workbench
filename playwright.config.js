import { defineConfig } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'
import { randomUUID } from 'node:crypto'

const port = Number(process.env.WORKBENCH_E2E_PORT || 18080)
if (!Number.isInteger(port) || port < 1024 || port > 65535 || port === 8080) {
  throw new Error('Browser tests require a dedicated port (1024–65535, excluding 8080).')
}
const localPython = process.platform === 'win32' ? '.venv/Scripts/python.exe' : '.venv/bin/python'
const python = process.env.WORKBENCH_TEST_PYTHON ||
  (fs.existsSync(localPython) ? path.resolve(localPython) : 'python')
const baseURL = `http://127.0.0.1:${port}`
process.env.WORKBENCH_E2E_SHUTDOWN_TOKEN ||= randomUUID()

export default defineConfig({
  testDir: './tests/e2e',
  testMatch: '**/*.spec.js',
  globalTeardown: './tests/e2e/teardown.js',
  timeout: 90_000,
  expect: { timeout: 10_000 },
  workers: 1,
  retries: 0,
  outputDir: 'test-results/browser',
  reporter: [['list'], ['html', { outputFolder: 'test-results/report', open: 'never' }]],
  use: {
    baseURL,
    browserName: 'chromium',
    channel: process.env.WORKBENCH_TEST_BROWSER || (process.platform === 'win32' ? 'msedge' : undefined),
    headless: true,
    viewport: { width: 1440, height: 1000 },
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    actionTimeout: 15_000,
  },
  webServer: {
    command: `"${python}" -u tests/e2e/serve.py`,
    url: `${baseURL}/api/status`,
    reuseExistingServer: false,
    timeout: 30_000,
    env: {
      WORKBENCH_E2E_PORT: String(port), PYTHONIOENCODING: 'utf-8', PYTHONDONTWRITEBYTECODE: '1',
      WORKBENCH_E2E_SHUTDOWN_TOKEN: process.env.WORKBENCH_E2E_SHUTDOWN_TOKEN,
    },
  },
})
