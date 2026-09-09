import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

const surface = vi.hoisted(() => ({
  page: "host" as "host" | "desktop",
  ios: true,
  standalone: false,
}));

vi.mock("../../lib/web-notify", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../lib/web-notify")>();
  return {
    ...actual,
    pageSurface: () => surface.page,
    isIosDevice: () => surface.ios,
    isStandaloneDisplay: () => surface.standalone,
  };
});

import { HostPhoneBanners } from "./HostPhoneBanners";

describe("HostPhoneBanners", () => {
  beforeEach(() => {
    surface.page = "host";
    surface.ios = true;
    surface.standalone = false;
  });

  it("shows the home-screen hint and Turn on alerts on the host page", () => {
    const html = renderToStaticMarkup(
      createElement(HostPhoneBanners, {
        alertOffer: "ask",
        hintDismissed: false,
        onDismissHint: () => undefined,
        onAlertPermission: () => undefined,
      }),
    );
    expect(html).toContain('data-testid="phone-host-banners"');
    expect(html).toContain("home-screen-hint");
    expect(html).toContain("turn-on-alerts");
  });

  it("renders nothing on the Linux window", () => {
    surface.page = "desktop";
    const html = renderToStaticMarkup(
      createElement(HostPhoneBanners, {
        alertOffer: "ask",
        hintDismissed: false,
        onDismissHint: () => undefined,
        onAlertPermission: () => undefined,
      }),
    );
    expect(html).toBe("");
  });
});
