import { expect, test, type Page } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { openComputerPane, openShell, sendMessage } from "./helpers";

const shotDir = process.env.ARTEK_SHOT_DIR || "/tmp/artek-memory-shots";

async function shot(page: Page, name: string, clip?: { x: number; y: number; width: number; height: number }) {
  fs.mkdirSync(shotDir, { recursive: true });
  await page.screenshot({
    path: path.join(shotDir, name),
    fullPage: false,
    clip,
    type: "png",
  });
}

function clampClip(
  page: Page,
  box: { x: number; y: number; width: number; height: number },
  pad = 12,
) {
  const viewport = page.viewportSize() || { width: 1440, height: 900 };
  const x = Math.max(0, Math.floor(box.x - pad));
  const y = Math.max(0, Math.floor(box.y - pad));
  const width = Math.min(viewport.width - x, Math.ceil(box.width + pad * 2));
  const height = Math.min(viewport.height - y, Math.ceil(box.height + pad * 2));
  return { x, y, width: Math.max(1, width), height: Math.max(1, height) };
}

test("memory panel and Remembered shots", async ({ page }) => {
  test.setTimeout(120_000);
  await openShell(page);
  const research = page.getByTestId("bot-row").filter({ hasText: "Research" });
  await expect(research).toBeVisible({ timeout: 15_000 });
  await research.click();
  await expect(page.getByLabel("Message")).toBeVisible();

  await openComputerPane(page);
  await expect(page.getByTestId("memory-doc").first()).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText("Lives in Belgrade")).toBeVisible();
  await expect(page.getByText(/owner · shared/).first()).toBeVisible();
  await expect(page.getByText(/work · shared/).first()).toBeVisible();
  await expect(page.getByText(/charter · this bot/).first()).toBeVisible();

  const heading = page.getByText("Memory", { exact: true });
  await heading.scrollIntoViewIfNeeded();
  await page.waitForTimeout(350);
  await shot(page, "01-memory-panel.png");

  const docs = page.getByTestId("memory-doc");
  const count = await docs.count();
  expect(count).toBeGreaterThanOrEqual(4);
  const firstBox = await docs.first().boundingBox();
  const lastBox = await docs.nth(count - 1).boundingBox();
  const headingBox = await heading.boundingBox();
  if (firstBox && lastBox && headingBox) {
    await shot(
      page,
      "02-memory-shelves.png",
      clampClip(page, {
        x: headingBox.x,
        y: headingBox.y,
        width: Math.max(firstBox.width, headingBox.width + 80),
        height: lastBox.y + lastBox.height - headingBox.y,
      }, 16),
    );
  } else {
    await shot(page, "02-memory-shelves.png");
  }

  await shot(page, "03-shared-book.png");

  // Remembered is SSE-only and emitted after run.completed. The shell then
  // GET /v1/threads/:id and the meta line vanishes. Delay that refresh so
  // Remembered stays while MemoryPanel remounts and lists the tea card.
  await page.route("**/v1/threads/*", async (route) => {
    const url = route.request().url();
    const method = route.request().method();
    const refresh = method === "GET" && !url.includes("/events") && !url.includes("/messages");
    if (refresh) {
      await new Promise((resolve) => setTimeout(resolve, 20_000));
    }
    await route.continue();
  });

  const remembered = page.getByText(/Remembered:/);
  const appeared = remembered.first().waitFor({ state: "visible", timeout: 20_000 });
  await sendMessage(page, "I prefer tea.");
  await appeared;

  // MemoryPanel only polls /v1/memory every 10s and does not refetch on
  // run.completed. Toggle the computer pane so it remounts and lists again
  // without touching the delayed thread GET.
  const computerBtn = page.getByTitle("Agent computer");
  await computerBtn.click();
  await expect(heading).toBeHidden({ timeout: 5_000 });
  await computerBtn.click();
  await expect(heading).toBeVisible({ timeout: 8_000 });

  const teaCard = page.getByTestId("memory-doc").filter({ hasText: /tea/i });
  await expect(teaCard).toBeVisible({ timeout: 15_000 });
  await expect(remembered.first()).toBeVisible();
  await remembered.first().scrollIntoViewIfNeeded();
  await page.waitForTimeout(250);
  await shot(page, "04-remembered-thread.png");
  await shot(page, "04-remembered-with-tea.png");

  await heading.scrollIntoViewIfNeeded();
  await page.waitForTimeout(300);
  await shot(page, "05-memory-after-remember.png");
});
