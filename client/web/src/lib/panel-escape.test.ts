import { describe, expect, it } from "vitest";
import { panelEscapeAction } from "./panel-escape";

describe("panelEscapeAction", () => {
  it("closes Settings and New bot, and leaves composer-only Escape alone", () => {
    expect(panelEscapeAction({ computerOpen: false, panel: "settings" })).toBe("close-settings");
    expect(panelEscapeAction({ computerOpen: false, panel: "create" })).toBe("close-create");
    expect(panelEscapeAction({ computerOpen: false, panel: null })).toBeNull();
  });

  it("closes the guest overlay first, then any contextual pane", () => {
    expect(panelEscapeAction({ computerOpen: true, panel: "settings" })).toBe("close-overlay");
    expect(panelEscapeAction({ computerOpen: false, panel: "models" })).toBe("close-panel");
    expect(panelEscapeAction({ computerOpen: false, panel: "plugins" })).toBe("close-panel");
    expect(panelEscapeAction({ computerOpen: false, panel: "computer" })).toBe("close-panel");
    expect(panelEscapeAction({ computerOpen: false, panel: "library" })).toBe("close-panel");
    expect(panelEscapeAction({ computerOpen: false, panel: "worklog" })).toBe("close-panel");
  });
});
