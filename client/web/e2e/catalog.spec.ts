import { expect, test } from "@playwright/test";
import { readClientLogTail } from "./client-log";
import {
  chooseMenu,
  createBot,
  deleteBots,
  openBotMenu,
  openComputerPane,
  openShell,
  sendMessage,
  userBubbles,
  waitUntilIdle,
} from "./helpers";

test.describe("every shell function", () => {
  const created: string[] = [];

  test.afterEach(async ({ request }, testInfo) => {
    await deleteBots(request, created.splice(0));
    testInfo.attach("client.log.tail", {
      body: readClientLogTail(20),
      contentType: "text/plain",
    });
  });

  test("running desktop without a screen url shows Retry", async ({ page }) => {
    await page.route("**/v1/computer/**/screen", (route) =>
      route.fulfill({
        status: 502,
        contentType: "application/json",
        body: JSON.stringify({ detail: "screen unreachable" }),
      }),
    );
    await openShell(page);
    const bot = await createBot(page, `e2e-screen-${Date.now().toString(36)}`);
    created.push(bot.id);
    await openComputerPane(page);
    await expect(page.getByTestId("computer-connecting")).toBeVisible({ timeout: 20_000 });
    await expect(page.getByRole("button", { name: "Retry" }).first()).toBeVisible();
    await page.unroute("**/v1/computer/**/screen");
    await page.getByRole("button", { name: "Retry" }).first().click();
    await expect(page.getByTestId("computer-preview")).toBeVisible({ timeout: 20_000 });
  });

  test("archives the last chat and restores it from Archived", async ({ page }) => {
    await openShell(page);
    const bot = await createBot(page, `e2e-arch-${Date.now().toString(36)}`);
    created.push(bot.id);
    await sendMessage(page, "keep this after archive");
    await waitUntilIdle(page);

    await openBotMenu(page, bot.name);
    await chooseMenu(page, "Archive");

    await expect(page.getByTestId("bot-row")).toHaveCount(0);
    await expect(page.getByTestId("open-archived")).toBeVisible();
    await expect(page.getByTestId("empty-inbox")).toBeVisible();
    await expect(page.getByTestId("thread-message")).toHaveCount(0);

    await page.getByTestId("open-archived").click();
    await expect(page.getByTestId("archived-bot-row")).toContainText(bot.name);
    await page.getByTestId("restore-chat").click();

    await expect(page.getByTestId("bot-row").filter({ hasText: bot.name })).toBeVisible();
    await expect(userBubbles(page).filter({ hasText: "keep this after archive" })).toBeVisible();
    await expect(page.getByTestId("open-archived")).toHaveCount(0);
  });

  test("pins, marks unread, duplicates, and edits a bot", async ({ page }) => {
    await openShell(page);
    const bot = await createBot(page, `e2e-menu-${Date.now().toString(36)}`);
    created.push(bot.id);

    await openBotMenu(page, bot.name);
    await chooseMenu(page, "Pin");
    await expect(page.getByTitle("Pinned")).toBeVisible();

    await openBotMenu(page, bot.name);
    await chooseMenu(page, "Mark as Unread");
    await expect(page.getByTestId("unread-dot")).toBeVisible();

    await openBotMenu(page, bot.name);
    await chooseMenu(page, "Mark as Read");
    await expect(page.getByTestId("unread-dot")).toHaveCount(0);

    await openBotMenu(page, bot.name);
    await chooseMenu(page, "Duplicate");
    const copyName = `${bot.name} (Copy)`;
    const copy = page.locator(`[data-testid="bot-row"][data-bot-name="${copyName}"]`);
    await expect(copy).toBeVisible();
    const copyId = await copy.getAttribute("data-bot-id");
    if (copyId) created.push(copyId);

    await openBotMenu(page, bot.name);
    await chooseMenu(page, "Edit Profile");
    await expect(page.getByText("Bot Settings")).toBeVisible();
    await page.getByRole("button", { name: "Edit Profile" }).click();
    const renamed = `${bot.name}-renamed`;
    await page.getByTestId("bot-name-input").fill(renamed);
    await page.getByRole("button", { name: "Save" }).click();
    await expect(page.locator(`[data-testid="bot-row"][data-bot-name="${renamed}"]`)).toBeVisible();
  });

  test("Private bot shows its own computer label", async ({ page }) => {
    await openShell(page);
    const bot = await createBot(page, `e2e-priv-${Date.now().toString(36)}`, "dedicated");
    created.push(bot.id);
    await openComputerPane(page);
    await expect(page.getByTestId("computer-label")).toHaveText(new RegExp(`${bot.name}.s computer`));
  });

  test("search keeps only the matching chat", async ({ page }) => {
    await openShell(page);
    const first = await createBot(page, `e2e-alpha-${Date.now().toString(36)}`);
    const second = await createBot(page, `e2e-beta-${Date.now().toString(36)}`);
    created.push(first.id, second.id);

    await page.getByPlaceholder("Search").fill("alpha");
    await expect(page.getByTestId("bot-row").filter({ hasText: first.name })).toBeVisible();
    await expect(page.getByTestId("bot-row").filter({ hasText: second.name })).toHaveCount(0);
  });

  test("creates memory and a routine from the computer pane", async ({ page }) => {
    await openShell(page);
    const bot = await createBot(page, `e2e-pane-${Date.now().toString(36)}`);
    created.push(bot.id);
    await openComputerPane(page);

    await page.getByTestId("new-memory").click();
    await page.getByPlaceholder("Facts to remember").fill("Remember the archive restore path.");
    await page.getByRole("button", { name: "Save" }).click();
    await expect(page.getByTestId("memory-doc")).toContainText("archive restore");

    await page.getByTestId("new-routine").click();
    await page.getByPlaceholder("Name", { exact: true }).fill("Morning ping");
    await page.getByPlaceholder("Prompt to send").fill("Say good morning");
    await page.getByRole("button", { name: "Save" }).click();
    await expect(page.getByTestId("routine-row")).toContainText("Morning ping");
    await page.getByTestId("routine-row").getByRole("button", { name: "on" }).click();
    await expect(page.getByTestId("routine-row").getByRole("button", { name: "off" })).toBeVisible();
  });

  test("reply composer attaches to a user message", async ({ page }) => {
    await openShell(page);
    const bot = await createBot(page, `e2e-reply-${Date.now().toString(36)}`);
    created.push(bot.id);
    await sendMessage(page, "reply to this line");
    await waitUntilIdle(page);

    await userBubbles(page).filter({ hasText: "reply to this line" }).click({ button: "right" });
    await page.getByRole("menuitem", { name: "Reply" }).click();
    await expect(page.getByText(/Replying to/)).toBeVisible();
    await page.getByLabel("Cancel reply").click();
    await expect(page.getByText(/Replying to/)).toHaveCount(0);
  });

  test("settings can stop and reset the computer", async ({ page }) => {
    await openShell(page);
    const bot = await createBot(page, `e2e-reset-${Date.now().toString(36)}`);
    created.push(bot.id);
    await openComputerPane(page);
    await expect(page.getByTitle("Settings")).toBeVisible();
    await page.getByTitle("Settings").click();
    await expect(page.getByText("Bot Settings")).toBeVisible();
    await expect(page.getByText(/Reset destroys the box/)).toBeVisible();
    await page.getByTestId("computer-stop").click();
    await expect(page.getByTestId("computer-power-state")).toHaveText("Offline");

    await page.getByTestId("computer-reset").click();
    await expect(page.getByText(/Browser logins and downloads will be gone/)).toBeVisible();
    await page.getByTestId("computer-reset-confirm").click();
    await expect(page.getByTestId("computer-power-state")).toHaveText("Offline");
    await expect(page.getByTestId("computer-reset")).toBeVisible();

    await page.getByLabel("Close settings").click();
    await page.getByTitle("Agent computer").click();
    await expect(page.getByText("Offline • Click to start")).toBeVisible();
  });

  test("settings delete removes the last chat", async ({ page }) => {
    await openShell(page);
    const bot = await createBot(page, `e2e-setdel-${Date.now().toString(36)}`);
    created.push(bot.id);
    await openBotMenu(page, bot.name);
    await chooseMenu(page, "Edit Profile");
    await expect(page.getByText("Bot Settings")).toBeVisible();
    await page.getByRole("button", { name: "Delete chat…" }).click();
    await page.getByRole("button", { name: "Delete", exact: true }).click();
    await expect(page.getByTestId("bot-row")).toHaveCount(0);
    await expect(page.getByTestId("empty-bots")).toBeVisible();
  });
});
