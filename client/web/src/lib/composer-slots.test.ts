import { describe, expect, it } from "vitest";
import {
  applyComposerSendResult,
  beginComposerSend,
  type ComposerSlot,
  emptyComposerSlot,
} from "./composer-slots";
import { createComposerHistory } from "./composer-undo";
import type { PendingFile } from "./uploads";

function fileChip(name: string): PendingFile {
  return { id: name, file: new File(["x"], name, { type: "text/plain" }) };
}

function slot(partial: Partial<ComposerSlot<string>>): ComposerSlot<string> {
  return { ...emptyComposerSlot<string>(), ...partial };
}

describe("beginComposerSend", () => {
  it("clears the originating draft and files and marks sending", () => {
    const started = beginComposerSend(
      slot({
        draft: "hello A",
        history: createComposerHistory("hello A"),
        pendingFiles: [fileChip("note.txt")],
        replyTo: "msg-1",
      }),
    );
    expect(started.draft).toBe("");
    expect(started.pendingFiles).toEqual([]);
    expect(started.sending).toBe(true);
    expect(started.replyTo).toBe("msg-1");
  });
});

describe("applyComposerSendResult", () => {
  it("keeps the open chat's Reply when a background send succeeds", () => {
    const live = slot({ draft: "on B", replyTo: "b-reply" });
    const parked = slot({ sending: true, replyTo: "a-reply" });
    const next = applyComposerSendResult({
      currentBotId: "bot-b",
      targetId: "bot-a",
      live,
      parked,
      result: { ok: true },
    });
    expect(next.live.replyTo).toBe("b-reply");
    expect(next.live.draft).toBe("on B");
    expect(next.live.sending).toBe(false);
    expect(next.parked?.sending).toBe(false);
    expect(next.parked?.replyTo).toBeNull();
  });

  it("restores a failed send onto the originating slot, not the open chat", () => {
    const live = slot({ draft: "on B" });
    const parked = slot({ sending: true });
    const files = [fileChip("note.txt")];
    const next = applyComposerSendResult({
      currentBotId: "bot-b",
      targetId: "bot-a",
      live,
      parked,
      result: { ok: false, draft: "failed A", files },
    });
    expect(next.live.draft).toBe("on B");
    expect(next.live.pendingFiles).toEqual([]);
    expect(next.parked?.draft).toBe("failed A");
    expect(next.parked?.pendingFiles).toEqual(files);
    expect(next.parked?.sending).toBe(false);
  });

  it("restores a failed send into the live composer when that chat is still open", () => {
    const live = slot({ sending: true });
    const files = [fileChip("note.txt")];
    const next = applyComposerSendResult({
      currentBotId: "bot-a",
      targetId: "bot-a",
      live,
      parked: undefined,
      result: { ok: false, draft: "failed A", files },
    });
    expect(next.live.draft).toBe("failed A");
    expect(next.live.pendingFiles).toEqual(files);
    expect(next.live.sending).toBe(false);
    expect(next.parked).toBeUndefined();
  });
});
