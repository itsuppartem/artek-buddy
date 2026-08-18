import { expect, test } from "@playwright/test";
import { readClientLogTail } from "./client-log";

test.describe("full bot workflow e2e", () => {
  test("creates a bot, runs a single query, queues 3 parallel tasks, and verifies clean UI", async ({ page }) => {
    test.setTimeout(60_000);

    // 1. Open web app
    await page.goto("/");
    await expect(page.getByPlaceholder("Search")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByLabel("Message")).toBeVisible();

    // 2. Create a new test bot
    const botName = `e2e-bot-${Date.now().toString(36)}`;
    await page.getByRole("button", { name: "New bot" }).click();
    await expect(page.getByPlaceholder("Name this bot")).toBeVisible();
    await page.getByPlaceholder("Name this bot").fill(botName);
    await page.getByPlaceholder("Describe what this bot does").fill("Automated E2E Test Bot");
    await page.screenshot({ path: "test-results/flow-1-create-dialog.png" });

    await page.getByRole("button", { name: "Create", exact: true }).click();
    await expect(page.locator("aside").first().getByText(botName)).toBeVisible({ timeout: 15_000 });
    await page.screenshot({ path: "test-results/flow-2-bot-created.png" });

    // Extract current bot ID from URL
    const currentUrl = page.url();
    const botIdMatch = currentUrl.match(/\/app\/(bot_[a-f0-9]+)/);
    const testBotId = botIdMatch ? botIdMatch[1] : null;

    try {
      // 3. Single request flow: e.g. Weather in Belgrade
      const composer = page.getByLabel("Message");
      await composer.fill("Check the current weather in Belgrade");
      await page.screenshot({ path: "test-results/flow-3-single-task-ready.png" });

      await page.getByRole("button", { name: "Send" }).click();
      await expect(page.locator('[data-testid="thread"]', { hasText: "Check the current weather in Belgrade" })).toBeVisible({
        timeout: 15_000,
      });
      await page.screenshot({ path: "test-results/flow-4-single-task-sent.png" });

      // Verify no raw tool cards are visible in the thread
      await expect(page.getByText("Tool", { exact: true })).toHaveCount(0);

      // Wait for a bot markdown answer (not the user bubble, which also says Belgrade).
      await expect(page.locator('[data-testid="thread"] .ab-chat-markdown').first()).toBeVisible({
        timeout: 20_000,
      });
      await page.screenshot({ path: "test-results/flow-4b-single-task-answered.png" });

      // 4. Send 3 tasks rapidly to test inbox queuing and parallel execution
      const tasks = [
        "Task 1: Search top Belgrade attractions and list 3 of them",
        "Task 2: Check current system time and memory usage",
        "Task 3: Search how to prepare coffee and list steps",
      ];

      for (let i = 0; i < tasks.length; i++) {
        await composer.fill(tasks[i]);
        await page.getByRole("button", { name: "Send" }).click();
        await page.waitForTimeout(300);
      }

      // Verify all 3 queued messages appear in the thread
      for (const taskText of tasks) {
        await expect(page.locator('[data-testid="thread"]', { hasText: taskText })).toBeVisible({
          timeout: 15_000,
        });
      }
      await page.screenshot({ path: "test-results/flow-5-tasks-queued.png" });

      await expect(page.locator('[data-testid="thread"] .ab-chat-markdown').first()).toBeVisible({
        timeout: 20_000,
      });
      await page.screenshot({ path: "test-results/flow-6-parallel-workers-running.png" });
      await page.screenshot({ path: "test-results/flow-7-all-tasks-finished.png" });

      // Verify again: no tool noise or raw tool logs in thread
      await expect(page.getByText("Tool", { exact: true })).toHaveCount(0);
    } finally {
      // 5. Cleanup: remove test bot via API if we got its ID
      if (testBotId) {
        try {
          await page.evaluate(async (id) => {
            await fetch(`/v1/bots/${id}?delete_memories=true`, { method: "DELETE" });
          }, testBotId);
        } catch {
          // Ignore cleanup error in test
        }
      }

      // Attach client.log tail to the test report
      test.info().attach("client.log.tail", {
        body: readClientLogTail(30),
        contentType: "text/plain",
      });
    }
  });
});
