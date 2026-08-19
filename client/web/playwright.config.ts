import { defineConfig } from "@playwright/test";

const port = Number(process.env.ARTEK_UI_PORT || 4177);
const baseURL = `http://127.0.0.1:${port}`;
const isolated = requireIsolatedHost();

function requireIsolatedHost(): { hostUrl: string; home: string; token: string } {
  const hostUrl = (process.env.ARTEK_UI_HOST_URL || "").replace(/\/$/, "");
  const home = process.env.ARTEK_E2E_HOME || "";
  const token = process.env.ARTEK_E2E_TOKEN || "";
  const marked = process.env.ARTEK_UI_ISOLATED === "1";
  let live = true;
  try {
    const parsed = new URL(hostUrl);
    const local = parsed.hostname === "127.0.0.1" || parsed.hostname === "localhost";
    const portNo = parsed.port || (parsed.protocol === "https:" ? "443" : "80");
    live = !local || portNo === "8080";
  } catch {
    live = true;
  }
  if (!marked || !hostUrl || !home || !token || live) {
    throw new Error(
      "Playwright UI tests refuse the live host. Run `make test-ui` (throwaway Postgres + scripted runtime).",
    );
  }
  return { hostUrl, home, token };
}

export default defineConfig({
  testDir: "./e2e",
  testIgnore: ["demo.spec.ts", "memory-shots.spec.ts"],
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: 1,
  reporter: [["list"], ["html", { open: "never", outputFolder: "playwright-report" }]],
  timeout: 60_000,
  expect: { timeout: 15_000 },
  use: {
    baseURL,
    viewport: { width: 1440, height: 900 },
    ignoreHTTPSErrors: true,
    screenshot: "on",
    trace: "off",
    video: "off",
    launchOptions: {
      executablePath: process.env.PLAYWRIGHT_CHROMIUM || "/usr/bin/chromium",
      args: ["--no-sandbox", "--disable-dev-shm-usage"],
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
      HOME: isolated.home,
      ARTEK_BUDDY_URL: isolated.hostUrl,
      ARTEK_BUDDY_NOTIFY: "0",
      AGENT_HTTP_TOKEN: isolated.token,
      ARTEK_BUDDY_UNPAIRED: "",
      ARTEK_SAVE_NO_DIALOG: "1",
    },
  },
});
