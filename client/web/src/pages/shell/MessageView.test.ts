import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import type { ThreadMessage } from "../../types";
import { MessageView, messageCopyText } from "./MessageView";

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

  it("turns Remembered into a Memory button and leaves Using as plain meta", () => {
    const long =
      "Remembered: RN-1935 P1 (biometric absent when Mesa not in boot syslog): stop. Do not change code, rebuild, reboot the phone, or pick error-vs-witness until the owner says so.";
    const remembered: ThreadMessage = {
      id: "msg-remember",
      threadId: "thr-remember",
      runId: "run-remember",
      role: "bot",
      seq: 1,
      createdAt: "2026-09-01T00:00:00Z",
      blocks: [{ kind: "meta", text: long }],
    };
    const using: ThreadMessage = {
      id: "msg-using",
      threadId: "thr-using",
      runId: "run-using",
      role: "bot",
      seq: 2,
      createdAt: "2026-09-01T00:00:00Z",
      blocks: [{ kind: "meta", text: "Using grok-4.0 - Extra high." }],
    };

    const rememberedHtml = renderToStaticMarkup(
      createElement(MessageView, {
        canAnswer: false,
        message: remembered,
        onAnswer: async () => undefined,
        onOpenBot: vi.fn(),
        onOpenMemory: vi.fn(),
      }),
    );
    const usingHtml = renderToStaticMarkup(
      createElement(MessageView, {
        canAnswer: false,
        message: using,
        onAnswer: async () => undefined,
        onOpenBot: vi.fn(),
        onOpenMemory: vi.fn(),
      }),
    );

    expect(rememberedHtml).toContain("Open in Memory");
    expect(rememberedHtml).toContain("data-memory-line");
    expect(rememberedHtml).toContain("Remembered: RN-1935");
    expect(rememberedHtml).toMatch(
      /<span class="min-w-0 truncate">Remembered: RN-1935[^<]*…<\/span>/,
    );
    expect(usingHtml).toContain("Using grok-4.0 - Extra high.");
    expect(usingHtml).not.toContain("Open in Memory");
    expect(usingHtml).not.toContain("<button");
  });
});

describe("messageCopyText", () => {
  it("joins text blocks so a right-click Copy has something to put on the clipboard", () => {
    const user: ThreadMessage = {
      id: "m-user",
      threadId: "t",
      runId: null,
      role: "user",
      seq: 1,
      createdAt: "2026-09-01T12:00:00Z",
      blocks: [{ kind: "text", text: "copy this line" }],
      replyToId: null,
      replyTo: null,
    };
    expect(messageCopyText(user)).toBe("copy this line");
    expect(
      messageCopyText({
        ...user,
        role: "bot",
        blocks: [
          { kind: "text", text: "First" },
          { kind: "text", text: "Second" },
        ],
      }),
    ).toBe("First\n\nSecond");
    expect(messageCopyText({ ...user, blocks: [] })).toBe("");
  });
});
