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
      }),
    );

    expect(html).not.toContain("book-card");
    expect(html).not.toContain("git-commit-style");
    expect(html).not.toContain("internal procedure");
  });

  it("renders a plugin login URL as an owner-browser link, not a JS popup button", () => {
    const message: ThreadMessage = {
      id: "msg-plugin",
      threadId: "thr-plugin",
      runId: "run-plugin",
      role: "bot",
      seq: 1,
      createdAt: "2026-09-01T00:00:00Z",
      blocks: [
        {
          kind: "plugin",
          name: "GitHub",
          text: "Open this link to sign in, then Finish in Plugins if the row stays pending.",
          url: "https://example.test/authorize?app=github",
        },
      ],
    };

    const html = renderToStaticMarkup(
      createElement(MessageView, {
        canAnswer: false,
        message,
        onAnswer: async () => undefined,
        onOpenBot: vi.fn(),
      }),
    );

    expect(html).toContain("plugin-connect-open");
    expect(html).toContain('href="https://example.test/authorize?app=github"');
    expect(html).toContain('target="_blank"');
    expect(html).toMatch(/<a\b[^>]*href="https:\/\/example\.test\/authorize\?app=github"/);
    expect(html).not.toMatch(/<button[^>]*plugin-connect-open/);
  });
});
