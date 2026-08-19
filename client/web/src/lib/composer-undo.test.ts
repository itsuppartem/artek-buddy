import { describe, expect, it } from "vitest";
import {
  composerRedo,
  composerUndo,
  composerUndoKind,
  createComposerHistory,
  pushComposerChange,
} from "./composer-undo";

describe("composer undo", () => {
  it("undoes a burst of typing as one step", () => {
    let history = createComposerHistory("");
    let last = 0;
    for (const value of ["h", "he", "hel", "hell", "hello"]) {
      history = pushComposerChange(history, value, 1_000 + last, last ? 1_000 + last - 20 : 0);
      last += 20;
    }
    const undone = composerUndo(history);
    expect(undone?.value).toBe("");
  });

  it("keeps a later edit as its own step", () => {
    let history = createComposerHistory("");
    history = pushComposerChange(history, "hello", 1_000, 0);
    history = pushComposerChange(history, "hello!", 2_000, 1_000);
    expect(composerUndo(history)?.value).toBe("hello");
  });

  it("redo restores the undone text", () => {
    let history = createComposerHistory("");
    history = pushComposerChange(history, "cat", 1_000, 0);
    const undone = composerUndo(history);
    expect(undone).not.toBeNull();
    const redone = composerRedo(undone!.history);
    expect(redone?.value).toBe("cat");
  });

  it("maps Ctrl+Z / Ctrl+Shift+Z / Ctrl+Y", () => {
    expect(composerUndoKind({ key: "z", ctrlKey: true, metaKey: false, shiftKey: false })).toBe("undo");
    expect(composerUndoKind({ key: "Z", ctrlKey: true, metaKey: false, shiftKey: true })).toBe("redo");
    expect(composerUndoKind({ key: "y", ctrlKey: true, metaKey: false, shiftKey: false })).toBe("redo");
    expect(composerUndoKind({ key: "z", ctrlKey: false, metaKey: false, shiftKey: false })).toBeNull();
  });
});
