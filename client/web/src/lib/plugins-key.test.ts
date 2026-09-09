import { describe, expect, it } from "vitest";
import {
  nextPluginsFetchGen,
  pluginsFetchIsCurrent,
  pluginsHttpClearsSavedKey,
  pluginsKeyMissingStatus,
  pluginsPaneStatusView,
} from "./plugins-key";

describe("pluginsFetchIsCurrent", () => {
  it("drops a catalog load that started before Remove", () => {
    const refreshStarted = 1;
    const afterRemove = nextPluginsFetchGen(refreshStarted);
    expect(pluginsFetchIsCurrent(refreshStarted, afterRemove)).toBe(false);
    expect(pluginsFetchIsCurrent(afterRemove, afterRemove)).toBe(true);
  });
});

describe("pluginsHttpClearsSavedKey", () => {
  it("treats a missing-key catalog as Paste a key, not Key saved", () => {
    expect(pluginsHttpClearsSavedKey(409)).toBe(true);
    expect(pluginsHttpClearsSavedKey(502)).toBe(false);
    expect(pluginsHttpClearsSavedKey(undefined)).toBe(false);
  });
});

describe("pluginsKeyMissingStatus", () => {
  it("is the empty Plugins key row after Remove", () => {
    expect(pluginsKeyMissingStatus()).toEqual({ configured: false, lastFour: null });
  });
});

describe("pluginsPaneStatusView", () => {
  it("does not stay on Checking when status failed", () => {
    expect(
      pluginsPaneStatusView({
        ready: false,
        configured: false,
        replace: false,
        error: "status down",
      }),
    ).toBe("failed");
  });

  it("does not pretend the key is missing when status has not loaded", () => {
    expect(
      pluginsPaneStatusView({
        ready: false,
        configured: false,
        replace: false,
        error: "",
      }),
    ).toBe("checking");
  });

  it("keeps Key saved when a later catalog call fails", () => {
    expect(
      pluginsPaneStatusView({
        ready: true,
        configured: true,
        replace: false,
        error: "Could not load apps.",
      }),
    ).toBe("saved");
  });
});
