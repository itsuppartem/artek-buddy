import { describe, expect, it } from "vitest";
import {
  composerUndo,
  composerUndoKind,
  createComposerHistory,
  pushComposerChange,
} from "./composer-undo";

describe("composerUndoKind", () => {
  it("maps Ctrl+Z to undo and Ctrl+Shift+Z to redo", () => {
    expect(composerUndoKind({ key: "z", ctrlKey: true, metaKey: false, shiftKey: false })).toBe(
      "undo",
    );
    expect(composerUndoKind({ key: "z", ctrlKey: true, metaKey: false, shiftKey: true })).toBe(
      "redo",
    );
    expect(
      composerUndoKind({ key: "v", ctrlKey: true, metaKey: false, shiftKey: false }),
    ).toBeNull();
  });
});

describe("composerUndo", () => {
  it("restores the previous Message draft", () => {
    let history = createComposerHistory("");
    history = pushComposerChange(history, "hello", 1_000, 0);
    const undone = composerUndo(history);
    expect(undone?.value).toBe("");
  });
});
