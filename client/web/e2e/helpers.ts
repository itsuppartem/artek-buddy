import { expect, type APIRequestContext, type Page } from "@playwright/test";
import { readdirSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

export async function openShell(page: Page): Promise<void> {
  await page.addInitScript(() => {
    Object.defineProperty(window, "__artekAnchorDownloads", { value: 0, writable: true });
    const proto = HTMLAnchorElement.prototype;
    const original = proto.click;
    proto.click = function (this: HTMLAnchorElement) {
      if (this.hasAttribute("download")) {
        (window as unknown as { __artekAnchorDownloads: number }).__artekAnchorDownloads += 1;
      }
      return original.call(this);
    };
  });
  await page.goto("/");
  await expect(page.getByPlaceholder("Search")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByLabel("Message")).toBeVisible();
}

export async function createBot(
  page: Page,
  name?: string,
  computerMode: "team" | "dedicated" = "team",
): Promise<{ id: string; name: string }> {
  const botName = name ?? `e2e-reg-${Date.now().toString(36)}`;
  await page.getByRole("button", { name: "New bot" }).click();
  await expect(page.getByPlaceholder("Name this bot")).toBeVisible();
  await page.getByPlaceholder("Name this bot").fill(botName);
  await page.getByPlaceholder("Describe what this bot does").fill("Regression bot");
  if (computerMode === "dedicated") {
    await page.getByRole("button", { name: "Private" }).click();
    await expect(page.getByTestId("computer-mode-hint")).toContainText("own Linux container");
  }
  await page.getByRole("button", { name: "Create", exact: true }).click();
  await expect(page.getByTestId("bot-row").filter({ hasText: botName })).toBeVisible({
    timeout: 15_000,
  });
  await expect(page).toHaveURL(/\/app\/bot_[a-f0-9]+/);
  const match = page.url().match(/\/app\/(bot_[a-f0-9]+)/);
  if (!match) throw new Error("bot id missing from URL");
  return { id: match[1], name: botName };
}

export async function deleteBots(request: APIRequestContext, ids: string[]): Promise<void> {
  for (const id of ids) {
    await request.delete(`/v1/bots/${id}?delete_memories=true`).catch(() => undefined);
  }
}

export async function sendMessage(page: Page, text: string): Promise<void> {
  const composer = page.getByLabel("Message");
  await composer.fill(text);
  await page.getByRole("button", { name: "Send" }).click();
  await expect(
    page.locator('[data-testid="thread-message"][data-role="user"]').filter({ hasText: text }),
  ).toBeVisible({ timeout: 15_000 });
}

export function botBubbles(page: Page) {
  return page.locator('[data-testid="thread-message"][data-role="bot"]');
}

export function userBubbles(page: Page) {
  return page.locator('[data-testid="thread-message"][data-role="user"]');
}

export async function downloadFileCard(page: Page, name = "notes.txt"): Promise<string> {
  const posts: string[] = [];
  await page.route("**/local/save-artifact", async (route) => {
    posts.push(route.request().url());
    await route.continue();
  });
  const card = page.getByTestId("file-card");
  await card.getByRole("button", { name: "Download" }).click();
  const saved = card.getByTestId("file-saved");
  await expect(saved).toContainText("Saved to");
  const stem = name.replace(/\.[^.]+$/, "");
  await expect(saved).toContainText(stem);
  expect(posts.length).toBeGreaterThan(0);
  expect(await page.evaluate(() => (window as unknown as { __artekAnchorDownloads?: number }).__artekAnchorDownloads || 0)).toBe(0);
  const home = process.env.ARTEK_E2E_HOME || homedir();
  const folder = join(home, "Downloads");
  const suffix = name.slice(stem.length);
  const match = readdirSync(folder).filter((item) => item.startsWith(stem) && item.endsWith(suffix));
  expect(match.length).toBeGreaterThan(0);
  return join(folder, match[match.length - 1]);
}

export async function waitUntilIdle(page: Page): Promise<void> {
  await expect(page.getByTestId("typing-indicator")).toHaveCount(0, { timeout: 20_000 });
  await expect(page.getByLabel("Stop")).toHaveCount(0, { timeout: 20_000 });
}

export async function openBotMenu(page: Page, name?: string): Promise<void> {
  const row = name
    ? page.locator(`[data-testid="bot-row"][data-bot-name="${name}"]`)
    : page.getByTestId("bot-row").first();
  await row.click({ button: "right" });
}

export async function chooseMenu(page: Page, name: string): Promise<void> {
  await page.getByRole("menuitem", { name, exact: true }).click();
}

export async function openComputerPane(page: Page): Promise<void> {
  const memory = page.getByText("Memory", { exact: true });
  if (await memory.isVisible()) return;
  await page.getByTitle("Agent computer").click();
  await expect(memory).toBeVisible({ timeout: 8_000 });
}

export async function blockLocalNotify(page: Page): Promise<string[]> {
  const hits: string[] = [];
  await page.route("**/local/notify", async (route) => {
    hits.push(route.request().url());
    await route.fulfill({ status: 204, body: "" });
  });
  return hits;
}
