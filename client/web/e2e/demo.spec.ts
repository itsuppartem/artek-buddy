import { expect, test, type Page } from "@playwright/test";
import { openComputerPane, waitUntilIdle } from "./helpers";

async function hold(page: Page, ms = 1600): Promise<void> {
  await page.waitForTimeout(ms);
}

async function typeInto(
  page: Page,
  locator: ReturnType<Page["getByLabel"]>,
  text: string,
  delay = 42,
): Promise<void> {
  await locator.click();
  await locator.fill("");
  await locator.pressSequentially(text, { delay });
}

async function scrollThread(page: Page): Promise<void> {
  const thread = page.getByTestId("thread");
  await thread.evaluate((el) => {
    el.scrollTop = el.scrollHeight;
  });
  await page.waitForTimeout(120);
  await thread.evaluate((el) => {
    el.scrollTop = el.scrollHeight;
  });
}

async function showInThread(page: Page, locator: ReturnType<Page["getByText"]>): Promise<void> {
  await scrollThread(page);
  await locator.evaluate((el) => {
    el.scrollIntoView({ block: "center", inline: "nearest" });
  });
  await page.waitForTimeout(200);
}

async function waitForLivePreview(page: Page): Promise<void> {
  await expect(page.getByTestId("computer-preview")).toBeVisible({ timeout: 90_000 });
  const starting = page.getByText("Desktop is starting…");
  const deadline = Date.now() + 90_000;
  while (Date.now() < deadline) {
    if ((await starting.count()) === 0) {
      const frameText = await page
        .frameLocator('[data-testid="computer-preview"]')
        .locator("body")
        .innerText()
        .catch(() => "");
      if (!frameText.includes("Desktop is starting")) return;
    }
    const retry = page.getByRole("button", { name: "Retry" });
    if (await retry.isVisible().catch(() => false)) {
      await retry.click();
    }
    await page.waitForTimeout(1500);
  }
  await expect(starting).toHaveCount(0);
}

async function typeAndSend(page: Page, text: string): Promise<void> {
  const composer = page.getByLabel("Message");
  await typeInto(page, composer, text, 40);
  await hold(page, 700);
  await page.getByRole("button", { name: "Send" }).click();
  const bubble = page.locator('[data-testid="thread-message"][data-role="user"]').filter({ hasText: text });
  await expect(bubble).toBeVisible({ timeout: 15_000 });
  await scrollThread(page);
}

async function mintPairingCode(): Promise<string> {
  const host = (process.env.ARTEK_UI_HOST_URL || "").replace(/\/$/, "");
  const token = process.env.ARTEK_E2E_TOKEN || "";
  const response = await fetch(`${host}/v1/devices/pairing`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, Accept: "application/json" },
  });
  if (!response.ok) throw new Error(`pairing mint failed: ${response.status}`);
  const body = (await response.json()) as { code?: string };
  if (!body.code) throw new Error("pairing code missing");
  return body.code;
}

test("readme demo: pair, ask, reply, real desktop, grok-style notes", async ({ page }) => {
  test.setTimeout(240_000);
  await page.goto("/");
  await expect(page.getByTestId("pairing")).toBeVisible({ timeout: 15_000 });
  await hold(page, 1400);

  const hostUrl = (process.env.ARTEK_UI_HOST_URL || "http://127.0.0.1:18081").replace(/\/$/, "");
  const urlBox = page.getByPlaceholder("https://host.example");
  await urlBox.click();
  await urlBox.fill("");
  await urlBox.pressSequentially(hostUrl, { delay: 28 });
  await hold(page, 500);

  const code = await mintPairingCode();
  await page.getByPlaceholder("XXXX-XXXX").click();
  await page.getByPlaceholder("XXXX-XXXX").pressSequentially(code, { delay: 80 });
  await hold(page, 400);
  await typeInto(page, page.getByLabel("Device name"), "Laptop", 50);
  await hold(page, 500);
  await page.getByRole("button", { name: "Pair" }).click();

  await expect(page.getByPlaceholder("Search")).toBeVisible({ timeout: 20_000 });
  await hold(page, 900);

  await page.getByRole("button", { name: "New bot" }).click();
  await expect(page.getByPlaceholder("Name this bot")).toBeVisible();
  await page.getByPlaceholder("Name this bot").pressSequentially("Research", { delay: 60 });
  await page.getByPlaceholder("Describe what this bot does").fill("Sources, briefings, and desktop work");
  await page.getByRole("button", { name: "Private" }).click();
  await hold(page, 600);
  await page.getByRole("button", { name: "Create", exact: true }).click();
  await expect(page.getByTestId("bot-row").filter({ hasText: "Research" })).toBeVisible({
    timeout: 15_000,
  });
  await openComputerPane(page);
  await expect(page.getByText("Running")).toBeVisible({ timeout: 90_000 });
  await waitForLivePreview(page);
  await hold(page, 2200);

  const thread = page.getByTestId("thread");
  await typeAndSend(page, "Morning briefing for today.");
  await expect(page.getByTestId("typing-indicator")).toBeVisible({ timeout: 10_000 });
  await waitUntilIdle(page);
  const briefing = thread.getByText(/Pi host is up/);
  await expect(briefing).toBeVisible();
  await showInThread(page, briefing);
  await hold(page, 2800);

  await typeAndSend(page, "I want to research a city.");
  await expect(page.getByTestId("typing-indicator")).toBeVisible({ timeout: 10_000 });
  const cityAsk = page.getByTestId("ask-card").getByText("Which city should we research?");
  await expect(cityAsk).toBeVisible({ timeout: 20_000 });
  await showInThread(page, cityAsk);
  await expect(page.getByTestId("ask-option").filter({ hasText: "Belgrade" })).toBeVisible();
  await hold(page, 3500);
  await page.getByTestId("ask-option").filter({ hasText: "Belgrade" }).click();
  await expect(page.getByTestId("typing-indicator")).toBeVisible({ timeout: 10_000 });
  await waitUntilIdle(page);
  const cityAnswer = thread.getByText(/Danube \+ Sava, Kalemegdan/);
  await expect(cityAnswer).toBeVisible();
  await showInThread(page, cityAnswer);
  await hold(page, 2600);

  const brief = thread
    .locator('[data-testid="thread-message"][data-role="bot"]')
    .filter({ hasText: /Danube \+ Sava, Kalemegdan/ });
  await brief.scrollIntoViewIfNeeded();
  await brief.click({ button: "right" });
  await expect(page.getByRole("menuitem", { name: "Reply" })).toBeVisible();
  await hold(page, 1400);
  await page.getByRole("menuitem", { name: "Reply" }).click();
  await expect(page.getByText(/Replying to/)).toBeVisible();
  await hold(page, 1800);
  await typeAndSend(page, "Open Wikipedia for Belgrade on the desktop.");
  await expect(page.getByTestId("typing-indicator")).toBeVisible({ timeout: 10_000 });
  await waitUntilIdle(page);
  const wikiNote = thread.getByText(/Wikipedia is on this computer/);
  await expect(wikiNote).toBeVisible();
  await showInThread(page, wikiNote);
  await waitForLivePreview(page);
  await hold(page, 4000);

  await openComputerPane(page);
  const openScreen = page.getByRole("button", { name: "Open screen" });
  if (await openScreen.isVisible().catch(() => false)) {
    await openScreen.click();
  } else {
    await page.getByRole("button", { name: "Take control" }).first().click();
  }
  await expect(page.getByLabel("Close computer")).toBeVisible({ timeout: 20_000 });
  await hold(page, 5000);
  const overlayTake = page.getByRole("button", { name: "Take control" });
  if (await overlayTake.isVisible().catch(() => false)) {
    await overlayTake.click();
    await expect(page.getByText("You have control")).toBeVisible({ timeout: 15_000 });
  }
  await hold(page, 3200);
  await page.keyboard.press("Escape");
  await hold(page, 1200);

  await typeAndSend(page, "Also give me attractions, weather, and cafes.");
  await expect(page.getByTestId("typing-indicator")).toBeVisible({ timeout: 10_000 });
  const attractions = thread.getByText(/Attractions: Kalemegdan/);
  await expect(attractions).toBeVisible({ timeout: 20_000 });
  await showInThread(page, attractions);
  await hold(page, 1200);
  const weather = thread.getByText(/Weather: clear/);
  await expect(weather).toBeVisible({ timeout: 20_000 });
  await showInThread(page, weather);
  await hold(page, 1200);
  const cafes = thread.getByText(/Beton Hala/);
  await expect(cafes).toBeVisible({ timeout: 20_000 });
  await showInThread(page, cafes);
  await waitUntilIdle(page);
  await scrollThread(page);
  await hold(page, 3000);
});
