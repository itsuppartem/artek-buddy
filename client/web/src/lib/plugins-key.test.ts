import { describe, expect, it } from "vitest";
import {
  nextPluginsFetchGen,
  pluginsFetchIsCurrent,
  pluginsHttpClearsSavedKey,
  pluginsKeyMissingStatus,
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
