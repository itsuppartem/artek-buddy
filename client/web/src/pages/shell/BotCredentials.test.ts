import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { BotCredentials } from "./BotCredentials";

describe("BotCredentials", () => {
  it("starts with one arbitrary named secret instead of provider-specific fields", () => {
    const html = renderToStaticMarkup(createElement(BotCredentials, { botId: "bot_test" }));

    expect(html).toContain("Add secret");
    expect(html).toContain("Secret name");
    expect(html).not.toContain("GitHub token");
    expect(html).not.toContain("PyPI token");
  });
});
