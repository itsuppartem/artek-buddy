import { expect, test } from "@playwright/test";
import { Buffer } from "node:buffer";
import { mkdirSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import { readClientLogTail } from "./client-log";
import { botBubbles, createBot, deleteBots, downloadFileCard, openShell, sendMessage, waitUntilIdle } from "./helpers";

test.describe("shipped feature UI", () => {
  const created: string[] = [];

  test.afterEach(async ({ request }, testInfo) => {
    await deleteBots(request, created.splice(0));
    testInfo.attach("client.log.tail", {
      body: readClientLogTail(20),
      contentType: "text/plain",
    });
  });

  test("shift-enter adds a newline and enter sends", async ({ page }) => {
    await openShell(page);
    const bot = await createBot(page, `e2e-nl-${Date.now().toString(36)}`);
    created.push(bot.id);
    const box = page.getByLabel("Message");
    await box.click();
    await box.pressSequentially("line one");
    await box.press("Shift+Enter");
    await box.pressSequentially("line two");
    await expect(box).toHaveValue("line one\nline two");
    await box.press("Enter");
    await expect(box).toHaveValue("");
    await expect(page.locator('[data-testid="thread-message"][data-role="user"]').last()).toContainText(
      "line one",
    );
    await expect(page.locator('[data-testid="thread-message"][data-role="user"]').last()).toContainText(
      "line two",
    );
    await waitUntilIdle(page);
  });

  test("ctrl-z undoes composer typing", async ({ page }) => {
    await openShell(page);
    const bot = await createBot(page, `e2e-undo-${Date.now().toString(36)}`);
    created.push(bot.id);
    const box = page.getByLabel("Message");
    await box.click();
    await box.pressSequentially("hello", { delay: 15 });
    await page.waitForTimeout(450);
    await box.pressSequentially(" world", { delay: 15 });
    await expect(box).toHaveValue("hello world");
    await box.press("Control+z");
    await expect(box).toHaveValue("hello");
    await box.press("Control+Shift+z");
    await expect(box).toHaveValue("hello world");
  });

  test("plus button attaches files and sends them with the message", async ({ page }) => {
    await openShell(page);
    const bot = await createBot(page, `e2e-attach-${Date.now().toString(36)}`);
    created.push(bot.id);
    await page.getByTestId("attach-files").setInputFiles([
      { name: "notes.txt", mimeType: "text/plain", buffer: Buffer.from("hello from plus") },
    ]);
    await expect(page.getByTestId("attach-chip")).toContainText("notes.txt");
    await sendMessage(page, "please read the file");
    await expect(page.getByTestId("attach-chip")).toHaveCount(0);
    const user = page.locator('[data-testid="thread-message"][data-role="user"]').last();
    await expect(user.getByTestId("file-card")).toContainText("notes.txt");
    await waitUntilIdle(page);
  });

  test("image attachment shows a preview before send", async ({ page }) => {
    await openShell(page);
    const bot = await createBot(page, `e2e-preview-${Date.now().toString(36)}`);
    created.push(bot.id);
    await page.getByTestId("attach-files").setInputFiles([
      {
        name: "shot.png",
        mimeType: "image/png",
        buffer: Buffer.from(
          "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
          "base64",
        ),
      },
    ]);
    await expect(page.getByTestId("attach-chip")).toContainText("shot.png");
    await expect(page.getByTestId("attach-preview")).toBeVisible();
    await sendMessage(page, "preview image");
    await expect(page.getByTestId("attach-chip")).toHaveCount(0);
    const user = page.locator('[data-testid="thread-message"][data-role="user"]').last();
    await expect(user.getByTestId("file-card")).toContainText("shot.png");
    await expect(user.getByTestId("file-preview")).toBeVisible();
    await waitUntilIdle(page);
  });

  test("ctrl-v of a local file path attaches the file not the path text", async ({ page }) => {
    await openShell(page);
    const bot = await createBot(page, `e2e-path-${Date.now().toString(36)}`);
    created.push(bot.id);
    const home = process.env.ARTEK_E2E_HOME || homedir();
    const folder = join(home, "Изображения", "Снимки экрана");
    mkdirSync(folder, { recursive: true });
    const name = `paste-${Date.now().toString(36)}.jpeg`;
    const dest = join(folder, name);
    writeFileSync(dest, Buffer.from("jpeg-from-path"));
    const box = page.getByLabel("Message");
    await box.click();
    await box.evaluate((el, path) => {
      const dt = new DataTransfer();
      dt.setData("text/plain", path);
      dt.setData("text/uri-list", `file://${encodeURI(path)}`);
      const event = new Event("paste", { bubbles: true, cancelable: true });
      Object.defineProperty(event, "clipboardData", { value: dt });
      el.dispatchEvent(event);
    }, dest);
    await expect(page.getByTestId("attach-chip")).toContainText(name);
    await expect(box).toHaveValue("");
    await expect(page.getByTestId("attach-preview")).toBeVisible();
  });

  test("ctrl-v pastes a file into the composer", async ({ page }) => {
    await openShell(page);
    const bot = await createBot(page, `e2e-paste-${Date.now().toString(36)}`);
    created.push(bot.id);
    await page.getByLabel("Message").evaluate((el) => {
      const dt = new DataTransfer();
      dt.items.add(new File(["hello from paste"], "pasted.txt", { type: "text/plain" }));
      const event = new Event("paste", { bubbles: true, cancelable: true });
      Object.defineProperty(event, "clipboardData", { value: dt });
      el.dispatchEvent(event);
    });
    await expect(page.getByTestId("attach-chip")).toContainText("pasted.txt");
    await sendMessage(page, "pasted file");
    await expect(
      page.locator('[data-testid="thread-message"][data-role="user"]').last().getByTestId("file-card"),
    ).toContainText("pasted.txt");
    await waitUntilIdle(page);
  });

  test("ctrl-v pastes a screenshot with a thumbnail", async ({ page }) => {
    await openShell(page);
    const bot = await createBot(page, `e2e-shot-${Date.now().toString(36)}`);
    created.push(bot.id);
    await page.getByLabel("Message").evaluate((el) => {
      const dt = new DataTransfer();
      dt.items.add(new File([new Uint8Array([137, 80, 78, 71, 13, 10, 26, 10])], "", { type: "image/png" }));
      const event = new Event("paste", { bubbles: true, cancelable: true });
      Object.defineProperty(event, "clipboardData", { value: dt });
      el.dispatchEvent(event);
    });
    await expect(page.getByTestId("attach-chip")).toContainText("screenshot-1.png");
    await expect(page.getByTestId("attach-preview")).toBeVisible();
    await sendMessage(page, "pasted screenshot");
    await expect(
      page.locator('[data-testid="thread-message"][data-role="user"]').last().getByTestId("file-card"),
    ).toContainText("screenshot-1.png");
    await expect(
      page.locator('[data-testid="thread-message"][data-role="user"]').last().getByTestId("file-preview"),
    ).toBeVisible();
    await waitUntilIdle(page);
  });

  test("several files can be attached at once", async ({ page }) => {
    await openShell(page);
    const bot = await createBot(page, `e2e-many-${Date.now().toString(36)}`);
    created.push(bot.id);
    await page.getByTestId("attach-files").setInputFiles([
      { name: "a.txt", mimeType: "text/plain", buffer: Buffer.from("one") },
      { name: "b.txt", mimeType: "text/plain", buffer: Buffer.from("two") },
    ]);
    await expect(page.getByTestId("attach-chip")).toHaveCount(2);
    await sendMessage(page, "two files");
    await expect(
      page.locator('[data-testid="thread-message"][data-role="user"]').last().getByTestId("file-card"),
    ).toHaveCount(2);
    await waitUntilIdle(page);
  });

  test("file card in the thread downloads the attached file", async ({ page }) => {
    await openShell(page);
    const bot = await createBot(page, `e2e-file-${Date.now().toString(36)}`);
    created.push(bot.id);
    await sendMessage(page, "e2e-send-file");
    await waitUntilIdle(page);

    const card = page.getByTestId("file-card");
    await expect(card).toBeVisible();
    await expect(card).toContainText("notes.txt");
    await expect(card).toContainText("18 B");
    await expect(botBubbles(page)).toContainText("Here is notes.txt");
    await expect(card.getByRole("button", { name: "Download" })).toBeVisible();

    const onDisk = await downloadFileCard(page, "notes.txt");
    expect(readFileSync(onDisk, "utf8")).toBe("hello from the bot");
  });

  test("download shows an error when the .deb cannot write Downloads", async ({ page }) => {
    await openShell(page);
    const bot = await createBot(page, `e2e-dlfail-${Date.now().toString(36)}`);
    created.push(bot.id);
    await sendMessage(page, "e2e-send-file");
    await waitUntilIdle(page);
    await page.route("**/local/save-artifact", (route) =>
      route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({ ok: false, error: "Could not write the file" }),
      }),
    );
    const card = page.getByTestId("file-card");
    await card.getByRole("button", { name: "Download" }).click();
    await expect(card.getByTestId("file-saved")).toHaveCount(0);
    await expect(card).toContainText("Could not");
    expect(await page.evaluate(() => (window as unknown as { __artekAnchorDownloads?: number }).__artekAnchorDownloads || 0)).toBe(0);
  });

  test("cancelled Save dialog leaves the file card idle", async ({ page }) => {
    await openShell(page);
    const bot = await createBot(page, `e2e-dlcancel-${Date.now().toString(36)}`);
    created.push(bot.id);
    await sendMessage(page, "e2e-send-file");
    await waitUntilIdle(page);
    await page.route("**/local/save-artifact", (route) =>
      route.fulfill({
        status: 409,
        contentType: "application/json",
        body: JSON.stringify({ ok: false, cancelled: true, error: "Save cancelled" }),
      }),
    );
    const card = page.getByTestId("file-card");
    await card.getByRole("button", { name: "Download" }).click();
    await expect(card.getByTestId("file-saved")).toHaveCount(0);
    await expect(card).not.toContainText("Could not");
    await expect(card.getByRole("button", { name: "Download" })).toBeEnabled();
    expect(await page.evaluate(() => (window as unknown as { __artekAnchorDownloads?: number }).__artekAnchorDownloads || 0)).toBe(0);
  });

  test("missing send_file does not paint a file card", async ({ page }) => {
    await openShell(page);
    const bot = await createBot(page, `e2e-filemiss-${Date.now().toString(36)}`);
    created.push(bot.id);
    await sendMessage(page, "e2e-send-file-missing");
    await waitUntilIdle(page);
    await expect(page.getByTestId("file-card")).toHaveCount(0);
    await expect(botBubbles(page)).toContainText("I could not find that file.");
  });

  test("form fill on the remote browser asks Allow once / Always / Deny", async ({ page }) => {
    await openShell(page);
    const bot = await createBot(page, `e2e-page-${Date.now().toString(36)}`);
    created.push(bot.id);
    await sendMessage(page, "e2e-consent-page");
    const card = page.getByTestId("consent-card");
    await expect(card).toBeVisible({ timeout: 15_000 });
    await expect(card).toContainText("Fill, type, or click on https://example.com");
    await expect(card).toHaveAttribute("data-status", "pending");
    await expect(page.getByTestId("ask-option").filter({ hasText: "Allow once" })).toBeVisible();
    await expect(page.getByTestId("ask-option").filter({ hasText: "Always" })).toBeVisible();
    await expect(page.getByTestId("ask-option").filter({ hasText: "Deny" })).toBeVisible();

    await page.getByTestId("ask-option").filter({ hasText: "Allow once" }).click();
    await expect(card).toHaveAttribute("data-status", "answered");
    await expect(card).toContainText("Answered: Allow once");
    await expect(page.getByTestId("ask-option")).toHaveCount(0);
    await waitUntilIdle(page);
  });

  test("page input Deny stays on the card", async ({ page }) => {
    await openShell(page);
    const bot = await createBot(page, `e2e-pagedeny-${Date.now().toString(36)}`);
    created.push(bot.id);
    await sendMessage(page, "e2e-consent-page");
    const card = page.getByTestId("consent-card");
    await expect(card).toBeVisible({ timeout: 15_000 });
    await page.getByTestId("ask-option").filter({ hasText: "Deny" }).click();
    await expect(card).toHaveAttribute("data-status", "answered");
    await expect(card).toContainText("Answered: Deny");
    await waitUntilIdle(page);
  });

  test("a long owner_exec command wraps inside the consent card", async ({ page }) => {
    await openShell(page);
    const bot = await createBot(page, `e2e-execwrap-${Date.now().toString(36)}`);
    created.push(bot.id);
    await sendMessage(page, "e2e-consent-exec-long");
    const card = page.getByTestId("consent-card");
    await expect(card).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId("ask-detail")).toContainText("owner_exec:");
    const overflow = await page.evaluate(() => {
      const pane = document.querySelector('[data-testid="thread-pane"]');
      const detail = document.querySelector('[data-testid="ask-detail"]');
      if (!pane || !detail) return true;
      return pane.scrollWidth > pane.clientWidth + 2 || detail.scrollWidth > detail.clientWidth + 2;
    });
    expect(overflow).toBe(false);
  });

  test("opening a site asks before the remote browser", async ({ page }) => {
    await openShell(page);
    const bot = await createBot(page, `e2e-browse-${Date.now().toString(36)}`);
    created.push(bot.id);
    await sendMessage(page, "e2e-consent-browse");
    const card = page.getByTestId("consent-card");
    await expect(card).toBeVisible({ timeout: 15_000 });
    await expect(card).toContainText("Open https://example.com on the remote desktop?");
    await page.getByTestId("ask-option").filter({ hasText: "Always" }).click();
    await expect(card).toHaveAttribute("data-status", "answered");
    await expect(card).toContainText("Answered: Always");
    await waitUntilIdle(page);
  });
});
