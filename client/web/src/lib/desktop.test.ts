import { describe, expect, it } from "vitest";
import { windowChromeKind } from "./desktop";
import type { DesktopBridge } from "../types";

function desktop(platform: DesktopBridge["platform"]): DesktopBridge {
  return {
    platform,
    window: {
      close: () => undefined,
      minimize: () => undefined,
      toggleMaximize: () => undefined,
    },
  };
}

describe("window chrome", () => {
  it("does not paint window buttons in a plain browser", () => {
    expect(windowChromeKind(undefined)).toBe("spacer");
  });

  it("leaves macOS traffic lights to the desktop shell", () => {
    expect(windowChromeKind(desktop("darwin"))).toBe("darwin");
  });

  it("uses real window-control buttons on Linux and Windows", () => {
    expect(windowChromeKind(desktop("linux"))).toBe("controls");
    expect(windowChromeKind(desktop("win32"))).toBe("controls");
  });
});
