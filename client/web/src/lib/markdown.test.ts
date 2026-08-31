import { describe, expect, it } from "vitest";
import {
  closeUnterminatedFence,
  contextLinkUrl,
  externalHttpUrl,
  sanitizeMarkdownUrl,
  stripMarkdown,
} from "./markdown";

describe("stripMarkdown", () => {
  it("strips nested leftover html markers", () => {
    expect(stripMarkdown("<<b>hi")).toBe("hi");
    expect(stripMarkdown("hello **there**")).toBe("hello there");
  });
});

describe("sanitizeMarkdownUrl", () => {
  it("keeps http(s) and drops javascript", () => {
    expect(sanitizeMarkdownUrl("https://example.com/a")).toBe("https://example.com/a");
    expect(sanitizeMarkdownUrl("javascript:alert(1)")).toBeUndefined();
  });

  it("allows relative paths only when asked", () => {
    expect(sanitizeMarkdownUrl("/v1/artifacts/x")).toBeUndefined();
    expect(sanitizeMarkdownUrl("/v1/artifacts/x", true)).toBe("/v1/artifacts/x");
  });
});

describe("externalHttpUrl", () => {
  it("keeps only absolute http(s) links without credentials", () => {
    expect(externalHttpUrl("https://example.com/docs")).toBe("https://example.com/docs");
    expect(externalHttpUrl("http://example.com")).toBe("http://example.com/");
    expect(externalHttpUrl("mailto:owner@example.com")).toBeUndefined();
    expect(externalHttpUrl("/relative")).toBeUndefined();
    expect(externalHttpUrl("https://owner@example.com")).toBeUndefined();
  });

  it("finds the http(s) link under a nested context-menu target", () => {
    const target = {
      closest: () => ({ getAttribute: () => "https://example.com/nested" }),
    };
    expect(contextLinkUrl(target)).toBe("https://example.com/nested");
    expect(contextLinkUrl({ closest: () => null })).toBeUndefined();
  });
});

describe("closeUnterminatedFence", () => {
  it("closes an open code fence so streaming markdown can render", () => {
    expect(closeUnterminatedFence("```js\nconst x = 1;")).toBe("```js\nconst x = 1;\n```");
  });

  it("leaves a closed fence alone", () => {
    expect(closeUnterminatedFence("```\nhi\n```")).toBe("```\nhi\n```");
  });
});
