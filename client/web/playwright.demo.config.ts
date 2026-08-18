import { defineConfig } from "@playwright/test";

const port = Number(process.env.ARTEK_UI_PORT || 4177);
const baseURL = `http://127.0.0.1:${port}`;
const hostUrl = (process.env.ARTEK_UI_HOST_URL || "").replace(/\/$/, "");
const home = process.env.ARTEK_E2E_HOME || "";
const token = process.env.ARTEK_E2E_TOKEN || "";

if (process.env.ARTEK_UI_ISOLATED !== "1" || !hostUrl || !home || !token) {
  throw new Error("Demo recording refuses the live host. Run `make demo`.");
}

export default defineConfig({
  testDir: "./e2e",
  testMatch: "demo.spec.ts",
  fullyParallel: false,
  retries: 0,
  workers: 1,
  reporter: [["list"]],
  timeout: 240_000,
  expect: { timeout: 30_000 },
  use: {
    baseURL,
    viewport: { width: 1440, height: 900 },
    ignoreHTTPSErrors: true,
    screenshot: "off",
    trace: "off",
    video: { mode: "on", size: { width: 1440, height: 900 } },
    launchOptions: {
      executablePath: process.env.PLAYWRIGHT_CHROMIUM || "/usr/bin/chromium",
      args: ["--no-sandbox", "--disable-dev-shm-usage"],
      slowMo: 240,
    },
  },
  projects: [{ name: "chromium" }],
  webServer: {
    command: `python3 ../artek_buddy.py --serve --port ${port}`,
    url: `${baseURL}/`,
    reuseExistingServer: false,
    timeout: 30_000,
    env: {
      ...process.env,
      HOME: home,
      ARTEK_BUDDY_URL: hostUrl,
      ARTEK_BUDDY_NOTIFY: "0",
      AGENT_HTTP_TOKEN: "",
      ARTEK_BUDDY_UNPAIRED: "1",
    },
  },
});
