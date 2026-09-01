import { afterEach, describe, expect, it, vi } from "vitest";
import { openOwnerBrowser } from "./owner-browser";

describe("openOwnerBrowser", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("uses window.open when the browser allows a tab", () => {
    const popup = { opener: {} as unknown };
    const open = vi.fn(() => popup);
    vi.stubGlobal("open", open);

    expect(openOwnerBrowser("https://example.test/authorize?app=mail")).toBe(true);
    expect(open).toHaveBeenCalledWith("https://example.test/authorize?app=mail", "_blank");
    expect(popup.opener).toBeNull();
  });

  it("falls back to a same-window navigation when window.open is dropped", () => {
    const assign = vi.fn();
    vi.stubGlobal("open", () => null);
    vi.stubGlobal("location", { assign });

    expect(openOwnerBrowser("https://github.com/login")).toBe(true);
    expect(assign).toHaveBeenCalledWith("https://github.com/login");
  });

  it("rejects javascript and credential-bearing targets", () => {
    const open = vi.fn(() => null);
    const assign = vi.fn();
    vi.stubGlobal("open", open);
    vi.stubGlobal("location", { assign });

    expect(openOwnerBrowser("javascript:alert(1)")).toBe(false);
    expect(openOwnerBrowser("https://owner@example.com")).toBe(false);
    expect(open).not.toHaveBeenCalled();
    expect(assign).not.toHaveBeenCalled();
  });
});
