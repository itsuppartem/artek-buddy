import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import type { ThreadMessage } from "../../types";
import { MessageView } from "./MessageView";

describe("MessageView", () => {
  it("keeps historical skill-book bodies out of the owner thread", () => {
    const message: ThreadMessage = {
      id: "msg-book",
      threadId: "thr-book",
      runId: "run-book",
      role: "bot",
      seq: 1,
      createdAt: "2026-08-31T00:00:00Z",
      blocks: [
        {
          kind: "book",
          action: "opened",
          name: "git-commit-style",
          text: "---\nname: git-commit-style\ndescription: internal procedure\n---",
        },
      ],
    };

    const html = renderToStaticMarkup(
      createElement(MessageView, {
        canAnswer: false,
        message,
        onAnswer: async () => undefined,
        onOpenBot: vi.fn(),
        onRestoreSkill: vi.fn(),
      }),
    );

    expect(html).not.toContain("book-card");
    expect(html).not.toContain("git-commit-style");
    expect(html).not.toContain("internal procedure");
  });
});
