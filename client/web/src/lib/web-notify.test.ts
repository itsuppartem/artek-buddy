import { describe, expect, it } from "vitest";
import {
  shouldHoldHostAlert,
  shouldOfferWebAlerts,
  shouldShowHomeScreenHint,
  shouldShowWebNotification,
} from "./web-notify";

describe("home screen and web alerts", () => {
  it("asks iPhone users to add the page to the home screen", () => {
    expect(shouldShowHomeScreenHint({ surface: "host", ios: true, standalone: false })).toBe(true);
    expect(shouldShowHomeScreenHint({ surface: "host", ios: true, standalone: true })).toBe(false);
    expect(shouldShowHomeScreenHint({ surface: "desktop", ios: true, standalone: false })).toBe(
      false,
    );
  });

  it("offers alerts on the host page after install, not in an iOS Safari tab", () => {
    expect(
      shouldOfferWebAlerts({
        surface: "host",
        permission: "default",
        standalone: true,
        ios: true,
      }),
    ).toBe("ask");
    expect(
      shouldOfferWebAlerts({
        surface: "host",
        permission: "default",
        standalone: false,
        ios: true,
      }),
    ).toBe("hide");
    expect(
      shouldOfferWebAlerts({
        surface: "host",
        permission: "granted",
        standalone: true,
        ios: true,
      }),
    ).toBe("ready");
    expect(
      shouldOfferWebAlerts({
        surface: "desktop",
        permission: "default",
        standalone: false,
        ios: false,
      }),
    ).toBe("hide");
  });

  it("notifies when the page is hidden or another chat is open", () => {
    expect(
      shouldShowWebNotification({ pageHidden: true, viewingBotId: "bot-a", alertBotId: "bot-a" }),
    ).toBe(true);
    expect(
      shouldShowWebNotification({ pageHidden: false, viewingBotId: "bot-b", alertBotId: "bot-a" }),
    ).toBe(true);
    expect(
      shouldShowWebNotification({ pageHidden: false, viewingBotId: "bot-a", alertBotId: "bot-a" }),
    ).toBe(false);
  });

  it("holds only the open chat while the home-screen app is in front", () => {
    expect(
      shouldHoldHostAlert({ pageHidden: false, viewingBotId: "bot-a", alertBotId: "bot-a" }),
    ).toBe(true);
    expect(
      shouldHoldHostAlert({ pageHidden: true, viewingBotId: "bot-a", alertBotId: "bot-a" }),
    ).toBe(false);
    expect(
      shouldHoldHostAlert({ pageHidden: false, viewingBotId: "bot-b", alertBotId: "bot-a" }),
    ).toBe(false);
  });
});
