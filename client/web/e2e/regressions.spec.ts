import { expect, test } from "@playwright/test";
import { readClientLogTail } from "./client-log";
import {
  blockLocalNotify,
  botBubbles,
  createBot,
  deleteBots,
  openShell,
  sendMessage,
  userBubbles,
  waitUntilIdle,
} from "./helpers";

const DRAFT_LEAK = "grade's current weather from a public API";
const DRAFT_ANSWER = "Belgrade is 22°C and clear.";
const CLOSE_STATUS = "Closing Chromium";
const SLOW_ANSWER = "slow done";
const MARKDOWN_RAW = "**Belgrade** weather is 22C";
const MARKDOWN_PLAIN = "Belgrade weather is 22C";

test.describe("live-window regressions", () => {
  const created: string[] = [];

  test.afterEach(async ({ request }, testInfo) => {
    await deleteBots(request, created.splice(0));
    testInfo.attach("client.log.tail", {
      body: readClientLogTail(30),
      contentType: "text/plain",
    });
  });

  test("deleting the last bot clears the thread", async ({ page }) => {
    await openShell(page);
    const bot = await createBot(page);
    created.push(bot.id);
    await sendMessage(page, "hello then delete");
    await waitUntilIdle(page);
    await expect(userBubbles(page).filter({ hasText: "hello then delete" })).toBeVisible();

    await page.getByTestId("bot-row").click({ button: "right" });
    await page.getByRole("menuitem", { name: "Delete" }).click();

    await expect(page.getByTestId("bot-row")).toHaveCount(0);
    await expect(page.getByTestId("empty-bots")).toBeVisible();
    await expect(page.getByTestId("thread-message")).toHaveCount(0);
    await expect(page.getByLabel("Message")).toBeDisabled();
  });

  test("does not create a broken default bot", async ({ page }) => {
    await openShell(page);
    await expect(page.getByTestId("bot-row")).toHaveCount(0);
    await expect(page.getByTestId("empty-bots")).toBeVisible();
    await expect(page.getByLabel("Message")).toBeDisabled();
    await page.getByTestId("empty-bots").getByRole("button", { name: "Create bot" }).click();
    await expect(page.getByPlaceholder("Name this bot")).toBeVisible();
  });

  test("does not flash empty-bots while the bot list is loading", async ({ page }) => {
    await page.route("**/v1/bots", async (route) => {
      if (route.request().method() !== "GET") {
        await route.continue();
        return;
      }
      await new Promise((resolve) => setTimeout(resolve, 800));
      await route.continue();
    });
    await page.goto("/");
    await expect(page.getByPlaceholder("Search")).toBeVisible();
    await expect(page.getByTestId("empty-bots")).toHaveCount(0);
    await expect(page.getByTestId("empty-bots")).toBeVisible({ timeout: 8_000 });
  });

  test("explains a disconnected host and recovers through Retry", async ({ page }) => {
    await page.route("**/health", (route) => route.abort("failed"));
    await page.goto("/");
    await expect(page.getByTestId("host-error")).toContainText("Could not reach the host");
    await expect(page.getByRole("button", { name: "Retry connection" })).toBeVisible();

    await page.unroute("**/health");
    await page.getByRole("button", { name: "Retry connection" }).click();
    await expect(page.getByTestId("host-error")).toHaveCount(0);
    await expect(page.getByTestId("empty-bots")).toBeVisible();
  });

  test("inbox overflow is an action error, not a host outage", async ({ page }) => {
    await openShell(page);
    created.push((await createBot(page)).id);
    await page.route("**/v1/threads/**/messages", async (route) => {
      if (route.request().method() !== "POST") {
        await route.continue();
        return;
      }
      await route.fulfill({
        status: 409,
        contentType: "application/json",
        body: JSON.stringify({
          detail: "Too many messages are already queued. Wait for the bot to finish, then try again.",
        }),
      });
    });
    await page.getByLabel("Message").fill("overflow");
    await page.getByRole("button", { name: "Send" }).click();
    await expect(page.getByTestId("action-error")).toContainText("Too many messages");
    await expect(page.getByRole("button", { name: "Dismiss" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Retry connection" })).toHaveCount(0);
  });

  test("revoked device offers pair again instead of Retry connection", async ({ page }) => {
    await openShell(page);
    created.push((await createBot(page)).id);
    await page.route("**/v1/**", async (route) => {
      await route.fulfill({
        status: 403,
        contentType: "application/json",
        body: JSON.stringify({ detail: "invalid token" }),
      });
    });
    await page.getByLabel("Message").fill("hello after revoke");
    await page.getByRole("button", { name: "Send" }).click();
    await expect(page.getByTestId("auth-error")).toContainText("no longer authorized");
    await expect(page.getByRole("button", { name: "Pair this computer again" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Retry connection" })).toHaveCount(0);
  });

  test("hides streamed reasoning and only paints the finished answer", async ({ page }) => {
    const notifyHits = await blockLocalNotify(page);
    await openShell(page);
    created.push((await createBot(page)).id);

    await sendMessage(page, "e2e-hide-draft look up Belgrade");
    await expect(page.getByTestId("typing-indicator")).toBeVisible();
    await expect(page.getByText(DRAFT_LEAK)).toHaveCount(0);
    await waitUntilIdle(page);

    await expect(botBubbles(page).filter({ hasText: DRAFT_ANSWER })).toBeVisible();
    await expect(page.getByText(DRAFT_LEAK)).toHaveCount(0);
    await expect(page.getByText("Tool", { exact: true })).toHaveCount(0);
    expect(notifyHits).toEqual([]);
  });

  test("close-browser posts a status and never a raw Tool card", async ({ page }) => {
    const notifyHits = await blockLocalNotify(page);
    await openShell(page);
    created.push((await createBot(page)).id);

    await sendMessage(page, "e2e-close-browser");
    await waitUntilIdle(page);

    await expect(botBubbles(page).filter({ hasText: CLOSE_STATUS })).toBeVisible();
    await expect(page.getByText("browser closed")).toHaveCount(0);
    await expect(page.getByText("Tool", { exact: true })).toHaveCount(0);
    expect(notifyHits).toEqual([]);
  });

  test("computer preview iframe stays the same node after send", async ({ page }) => {
    await openShell(page);
    created.push((await createBot(page)).id);

    const preview = page.getByTestId("computer-preview");
    await expect(preview).toBeVisible({ timeout: 20_000 });
    const before = await preview.evaluate((node) => ({
      src: (node as HTMLIFrameElement).src,
      key: node.getAttribute("src"),
    }));
    const identity = await preview.evaluate((node) => {
      (window as unknown as { __abPreview?: Element }).__abPreview = node;
      return true;
    });
    expect(identity).toBe(true);
    expect(before.src).toContain("/novnc/");

    await sendMessage(page, "hello after preview");
    await waitUntilIdle(page);

    await expect(page.getByTestId("computer-connecting")).toHaveCount(0);
    await expect(preview).toBeVisible();
    const after = await preview.evaluate((node) => {
      const held = (window as unknown as { __abPreview?: Element }).__abPreview;
      return {
        sameNode: held === node,
        src: (node as HTMLIFrameElement).src,
      };
    });
    expect(after.sameNode).toBe(true);
    expect(after.src).toBe(before.src);
  });

  test("attention banner is one in-window alert and never POSTs /local/notify", async ({
    page,
  }) => {
    const notifyHits = await blockLocalNotify(page);
    await openShell(page);
    const bot = await createBot(page);
    created.push(bot.id);

    await sendMessage(page, "hello");
    await waitUntilIdle(page);
    await expect(page.getByTestId("attention-alert")).toHaveCount(1);
    await expect(page.getByTestId("attention-alert")).toContainText(`${bot.name} replied`);
    expect(notifyHits).toEqual([]);
  });

  test("notifyOnFinish off skips replied banners but still shows ask cards", async ({ page }) => {
    const notifyHits = await blockLocalNotify(page);
    await openShell(page);
    const bot = await createBot(page);
    created.push(bot.id);

    await page.getByTitle("Settings").click();
    await expect(page.getByTestId("notify-on-finish")).toBeVisible();
    await page.getByTestId("notify-on-finish").uncheck();
    await page.getByLabel("Close settings").click();

    await sendMessage(page, "hello quietly");
    await waitUntilIdle(page);
    await expect(page.getByTestId("attention-alert")).toHaveCount(0);

    await sendMessage(page, "e2e-ask pick a city");
    await expect(page.getByTestId("ask-card")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId("attention-alert")).toContainText(`${bot.name} is asking`);
    await expect(page.getByTestId("ask-option").filter({ hasText: "Belgrade" })).toBeVisible();

    await page.getByTestId("ask-option").filter({ hasText: "Belgrade" }).click();
    await expect(page.getByTestId("ask-card")).toHaveAttribute("data-status", "answered");
    await expect(page.getByText("Answered: Belgrade")).toBeVisible();
    await expect(page.getByTestId("ask-option")).toHaveCount(0);
    await expect(userBubbles(page).filter({ hasText: "Belgrade" })).toBeVisible();
    await waitUntilIdle(page);
    expect(notifyHits).toEqual([]);
  });

  test("send stays enabled while busy so a second message queues", async ({ page }) => {
    await openShell(page);
    created.push((await createBot(page)).id);

    await sendMessage(page, "e2e-slow first");
    await expect(page.getByLabel("Stop")).toBeVisible();
    await page.getByLabel("Message").fill("queued ping");
    await expect(page.getByRole("button", { name: "Send" })).toBeEnabled();
    await page.getByRole("button", { name: "Send" }).click();

    await expect(userBubbles(page).filter({ hasText: "e2e-slow first" })).toBeVisible();
    await expect(userBubbles(page).filter({ hasText: "queued ping" })).toBeVisible();
    await waitUntilIdle(page);
    await expect(botBubbles(page).filter({ hasText: SLOW_ANSWER })).toBeVisible();
    await expect(botBubbles(page).filter({ hasText: "ok" })).toBeVisible();
  });

  test("Stop cancels a slow turn and drops the typing dots", async ({ page }) => {
    await openShell(page);
    created.push((await createBot(page)).id);

    await sendMessage(page, "e2e-slow stop me");
    await expect(page.getByTestId("typing-indicator")).toBeVisible();
    await page.getByLabel("Stop").click();
    await waitUntilIdle(page);
    await expect(page.getByText(SLOW_ANSWER)).toHaveCount(0);
    await expect(page.getByTestId("run-error")).toHaveText("Stopped.");
    await expect(page.getByText("Stopped.")).toHaveCount(1);
    await expect(page.getByText("stopped by user")).toHaveCount(0);
  });

  test("sidebar preview strips markdown and bot switch does not leak the other thread", async ({
    page,
  }) => {
    await openShell(page);
    const first = await createBot(page);
    created.push(first.id);
    await sendMessage(page, "e2e-markdown-preview");
    await waitUntilIdle(page);
    await expect(botBubbles(page).filter({ hasText: "Belgrade" })).toBeVisible();
    await expect(
      page.getByTestId("bot-row").filter({ hasText: first.name }).getByTestId("bot-preview"),
    ).toHaveText(MARKDOWN_PLAIN);
    await expect(page.getByTestId("bot-preview").filter({ hasText: MARKDOWN_RAW })).toHaveCount(0);

    const second = await createBot(page);
    created.push(second.id);
    await expect(page.getByText("e2e-markdown-preview")).toHaveCount(0);
    await expect(botBubbles(page)).toHaveCount(0);

    await page.getByTestId("bot-row").filter({ hasText: first.name }).click();
    await expect(userBubbles(page).filter({ hasText: "e2e-markdown-preview" })).toBeVisible();
    await expect(page.getByText("secret-from-b")).toHaveCount(0);

    await page.getByTestId("bot-row").filter({ hasText: second.name }).click();
    await sendMessage(page, "secret-from-b");
    await waitUntilIdle(page);
    await page.getByTestId("bot-row").filter({ hasText: first.name }).click();
    await expect(page.getByText("secret-from-b")).toHaveCount(0);
    await expect(userBubbles(page).filter({ hasText: "e2e-markdown-preview" })).toBeVisible();
  });

  test("failed scripted turn shows one failed banner and no draft leak", async ({ page }) => {
    const notifyHits = await blockLocalNotify(page);
    await openShell(page);
    const bot = await createBot(page);
    created.push(bot.id);

    await sendMessage(page, "e2e-fail please");
    await waitUntilIdle(page);
    await expect(page.getByTestId("attention-alert")).toHaveCount(1);
    await expect(page.getByTestId("attention-alert")).toContainText(`${bot.name} failed`);
    await expect(page.getByTestId("run-error")).toBeVisible();
    await expect(page.getByText(DRAFT_LEAK)).toHaveCount(0);
    expect(notifyHits).toEqual([]);
  });

  test("a slow thread fetch cannot paint the previous bot after a switch", async ({ page }) => {
    await openShell(page);
    const first = await createBot(page);
    created.push(first.id);
    await sendMessage(page, "alpha-secret");
    await waitUntilIdle(page);
    const second = await createBot(page);
    created.push(second.id);
    await sendMessage(page, "beta-secret");
    await waitUntilIdle(page);

    let releaseFirst: (() => void) | undefined;
    const held = new Promise<void>((resolve) => {
      releaseFirst = resolve;
    });
    await page.route(`**/v1/threads/${first.id}`, async (route) => {
      if (route.request().method() !== "GET") {
        await route.continue();
        return;
      }
      await held;
      await route.continue();
    });

    await page.getByTestId("bot-row").filter({ hasText: first.name }).click();
    await page.getByTestId("bot-row").filter({ hasText: second.name }).click();
    releaseFirst?.();
    await expect(userBubbles(page).filter({ hasText: "beta-secret" })).toBeVisible();
    await expect(page.getByText("alpha-secret")).toHaveCount(0);
  });
});
