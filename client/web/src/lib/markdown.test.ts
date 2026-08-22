import { describe, expect, it } from "vitest";
import { closeUnterminatedFence, sanitizeMarkdownUrl } from "./markdown";

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

describe("closeUnterminatedFence", () => {
  it("closes an open code fence so streaming markdown can render", () => {
    expect(closeUnterminatedFence("```js\nconst x = 1;")).toBe("```js\nconst x = 1;\n```");
  });

  it("leaves a closed fence alone", () => {
    expect(closeUnterminatedFence("```\nhi\n```")).toBe("```\nhi\n```");
  });
});
