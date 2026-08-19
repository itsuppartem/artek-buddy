import { defineConfig } from "@playwright/test";

const port = Number(process.env.ARTEK_UI_PORT || 4178);
const baseURL = `http://127.0.0.1:${port}`;
const hostUrl = (process.env.ARTEK_UI_HOST_URL || "").replace(/\/$/, "");
const home = process.env.ARTEK_E2E_HOME || "";
const token = process.env.ARTEK_E2E_TOKEN || "";

if (process.env.ARTEK_UI_ISOLATED !== "1" || !hostUrl || !home || !token) {
  throw new Error("Memory shots refuse the live host. Run tests/run_memory_shots.py.");
}
try {
  const parsed = new URL(hostUrl);
  const local = parsed.hostname === "127.0.0.1" || parsed.hostname === "localhost";
  const portNo = parsed.port || (parsed.protocol === "https:" ? "443" : "80");
  if (!local || portNo === "8080") {
    throw new Error("live");
  }
} catch {
  throw new Error("Memory shots refuse the live host. Run tests/run_memory_shots.py.");
}

export default defineConfig({
  testDir: "./e2e",
  testMatch: "memory-shots.spec.ts",
  fullyParallel: false,
  retries: 0,
  workers: 1,
  reporter: [["list"]],
  timeout: 90_000,
  expect: { timeout: 20_000 },
  use: {
    baseURL,
    viewport: { width: 1440, height: 900 },
    ignoreHTTPSErrors: true,
    screenshot: "off",
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
      HOME: home,
      ARTEK_BUDDY_URL: hostUrl,
      ARTEK_BUDDY_NOTIFY: "0",
      AGENT_HTTP_TOKEN: token,
      ARTEK_BUDDY_UNPAIRED: "",
    },
  },
});
