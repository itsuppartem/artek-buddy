import { describe, expect, it } from "vitest";
import { closeUnterminatedFence, sanitizeMarkdownUrl, stripMarkdown } from "./markdown";

describe("sanitizeMarkdownUrl", () => {
  it("allows normal external links and optionally allows local links", () => {
    expect(sanitizeMarkdownUrl("https://example.com/docs")).toBe("https://example.com/docs");
    expect(sanitizeMarkdownUrl("mailto:hello@example.com")).toBe("mailto:hello@example.com");
    expect(sanitizeMarkdownUrl("/docs", true)).toBe("/docs");
    expect(sanitizeMarkdownUrl("#section", true)).toBe("#section");
  });

  it("rejects executable and embedded-data URLs", () => {
    expect(sanitizeMarkdownUrl("javascript:alert(1)", true)).toBeUndefined();
    expect(sanitizeMarkdownUrl("data:text/html,<script>alert(1)</script>", true)).toBeUndefined();
    expect(sanitizeMarkdownUrl("/docs")).toBeUndefined();
  });
});

describe("closeUnterminatedFence", () => {
  it("temporarily closes a partial streaming code fence", () => {
    expect(closeUnterminatedFence("Before\n```ts\nconst value = 1;")).toBe(
      "Before\n```ts\nconst value = 1;\n```",
    );
  });

  it("leaves complete markdown unchanged", () => {
    const markdown = "```ts\nconst value = 1;\n```\n\nDone";
    expect(closeUnterminatedFence(markdown)).toBe(markdown);
  });
});

describe("stripMarkdown", () => {
  it("removes bold, italic, code, links, headers and lists from snippets", () => {
    expect(stripMarkdown("**Белград, сейчас (11:30)**\n- +24.6°C, ощущается как +24.1°C")).toBe(
      "Белград, сейчас (11:30) +24.6°C, ощущается как +24.1°C",
    );
    expect(stripMarkdown("# Header\n[YouTube](https://youtube.com) is `running`")).toBe(
      "Header YouTube is running",
    );
    expect(stripMarkdown("```python\nprint(1)\n```Done")).toBe("Done");
  });
});
