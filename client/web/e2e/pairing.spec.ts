import { expect, test } from "@playwright/test";
import { spawn, type ChildProcess } from "node:child_process";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const port = 4178;

test.describe("pairing screen", () => {
  let child: ChildProcess | undefined;

  test.beforeAll(async () => {
    const home = mkdtempSync(join(tmpdir(), "artek-e2e-pair-"));
    child = spawn("python3", ["-u", join(root, "artek_buddy.py"), "--serve", `--port=${port}`], {
      cwd: root,
      env: {
        ...process.env,
        HOME: home,
        PYTHONUNBUFFERED: "1",
        ARTEK_BUDDY_UNPAIRED: "1",
        AGENT_HTTP_TOKEN: "",
        ARTEK_BUDDY_URL: process.env.ARTEK_UI_HOST_URL || "http://127.0.0.1:18080",
      },
      stdio: ["ignore", "pipe", "pipe"],
    });
    await waitForHttp(`http://127.0.0.1:${port}/`);
  });

  test.afterAll(() => {
    child?.kill("SIGTERM");
  });

  test("shows the pair form and rejects a fake code", async ({ browser }) => {
    const page = await browser.newPage();
    await page.goto(`http://127.0.0.1:${port}/`, { waitUntil: "networkidle" });
    await expect(page.getByTestId("pairing")).toBeVisible();
    await expect(page.getByText("Pair this computer")).toBeVisible();
    await page.screenshot({ path: "test-results/pairing-empty.png" });

    await page.getByPlaceholder("XXXX-XXXX").fill("AAAA-BBBB");
    await page.getByRole("button", { name: "Pair" }).click();
    await expect(page.getByTestId("pairing-error")).toBeVisible({ timeout: 20_000 });
    await expect(page.getByTestId("pairing-error")).toContainText(/invalid or expired|pairing/i);
    await page.screenshot({ path: "test-results/pairing-bad-code.png" });
    await page.close();
  });
});

async function waitForHttp(url: string): Promise<void> {
  const deadline = Date.now() + 20_000;
  let last = "";
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url);
      if (response.ok) return;
      last = `status ${response.status}`;
    } catch (err) {
      last = err instanceof Error ? err.message : String(err);
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error(`pairing proxy did not start (${last})`);
}
