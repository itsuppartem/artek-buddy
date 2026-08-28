import { describe, expect, it } from "vitest";
import { panelEscapeAction } from "./panel-escape";

describe("panelEscapeAction", () => {
  it("closes Settings and New bot, and leaves composer-only Escape alone", () => {
    expect(panelEscapeAction({ computerOpen: false, panel: "settings" })).toBe("close-settings");
    expect(panelEscapeAction({ computerOpen: false, panel: "create" })).toBe("close-create");
    expect(panelEscapeAction({ computerOpen: false, panel: null })).toBeNull();
  });

  it("closes the guest overlay first and does not steal Models or Plugins", () => {
    expect(panelEscapeAction({ computerOpen: true, panel: "settings" })).toBe("close-overlay");
    expect(panelEscapeAction({ computerOpen: false, panel: "models" })).toBeNull();
    expect(panelEscapeAction({ computerOpen: false, panel: "plugins" })).toBeNull();
    expect(panelEscapeAction({ computerOpen: false, panel: "computer" })).toBeNull();
  });
});
