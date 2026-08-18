import { expect, test } from "@playwright/test";
import { readClientLogTail } from "./client-log";

test.describe("paired shell", () => {
  test("walks the live panes and does not paint raw tool cards", async ({ page }) => {
    await page.goto("/");
    const closeComputer = page.getByLabel("Close computer");
    if (await closeComputer.isVisible()) {
      await closeComputer.click();
    }
    await expect(page.getByPlaceholder("Search")).toBeVisible();
    await expect(page.locator("aside button").first()).toBeVisible({ timeout: 15_000 });
    await expect(page.getByLabel("Message")).toBeVisible();
    await expect(page.getByLabel("Message")).not.toHaveAttribute("placeholder", "Message…");
    await page.screenshot({ path: "test-results/shell-thread.png" });

    await expect(page.getByText("Tool", { exact: true })).toHaveCount(0);

    const memoryHeading = page.getByText("Memory", { exact: true });
    if (!(await memoryHeading.isVisible())) {
      const computerToggle = page.getByTitle("Agent computer");
      if (await computerToggle.isVisible()) {
        await computerToggle.click();
      }
    }

    await expect(page.getByText("Memory", { exact: true })).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText("Routines", { exact: true })).toBeVisible({ timeout: 15_000 });
    const takeControlBtn = page.getByRole("button", { name: "Take control" });
    if (await takeControlBtn.isVisible()) {
      await takeControlBtn.click();
    }
    await expect(page.getByRole("button", { name: "Open screen" }).first()).toBeVisible({ timeout: 15_000 });
    // Wait for screen preview iframe to attach and render
    await page.waitForTimeout(3000);
    await page.screenshot({ path: "test-results/shell-computer.png" });

    // Fullscreen screen view check
    const closeBtn = page.getByLabel("Close computer");
    if (await closeBtn.isVisible()) {
      await expect(closeBtn).toBeVisible();
      await page.waitForTimeout(1000);
      await page.screenshot({ path: "test-results/shell-computer-fullscreen.png" });
      await closeBtn.click();
      await expect(page.locator('iframe[title="Bot screen"]')).toHaveCount(0);
    } else {
      const openScreenBtn = page.getByRole("button", { name: "Open screen" }).first();
      if (await openScreenBtn.isVisible()) {
        await openScreenBtn.click();
        await expect(page.getByLabel("Close computer")).toBeVisible({ timeout: 15_000 });
        await page.waitForTimeout(1000);
        await page.screenshot({ path: "test-results/shell-computer-fullscreen.png" });
        await page.getByLabel("Close computer").click();
        await expect(page.locator('iframe[title="Bot screen"]')).toHaveCount(0);
      }
    }

    await page.getByText("Plugins").click();
    await expect(page.getByText("Plugins ship with a later stage.")).toBeVisible();
    await page.screenshot({ path: "test-results/shell-plugins-stub.png" });

    await page.getByRole("button", { name: "New bot" }).click();
    await expect(page.getByPlaceholder("Name this bot")).toBeVisible();
    await page.screenshot({ path: "test-results/shell-create.png" });
    await page.getByText("✕").first().click();

    const userBubble = page.locator('[data-testid="thread"] .justify-end').first();
    if (await userBubble.count()) {
      await userBubble.click({ button: "right" });
      await expect(page.getByRole("menuitem", { name: "Reply" })).toBeVisible();
      await page.screenshot({ path: "test-results/shell-reply-menu.png" });
      await page.getByRole("menuitem", { name: "Reply" }).click();
      await expect(page.getByText(/Replying to/)).toBeVisible();
      await page.screenshot({ path: "test-results/shell-reply-composer.png" });
      await page.getByLabel("Cancel reply").click();
    }

    await page.getByLabel("Message").fill("ui-harness probe (do not run)");
    await expect(page.getByRole("button", { name: "Send" })).toBeEnabled();
    await page.screenshot({ path: "test-results/shell-composer-ready.png" });
    await page.getByLabel("Message").fill("");

    await page.getByTitle("Agent computer").click();
    await expect(page.getByTitle("Settings")).toBeVisible({ timeout: 15_000 });
    await page.getByTitle("Settings").click();
    await expect(page.getByText("Bot Settings")).toBeVisible();
    await expect(page.getByTestId("notify-on-finish")).toBeVisible();
    await page.screenshot({ path: "test-results/shell-settings-notify.png" });
    await page.getByLabel("Close settings").click();

    const tail = readClientLogTail(20);
    test.info().attach("client.log.tail", { body: tail, contentType: "text/plain" });
    expect(tail.length).toBeGreaterThan(0);
  });
});
