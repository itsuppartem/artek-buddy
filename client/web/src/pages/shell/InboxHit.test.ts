import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { InboxHit } from "./InboxHit";

describe("InboxHit", () => {
  it("marks the first query match so Search can see the hit", () => {
    const html = renderToStaticMarkup(
      createElement(InboxHit, { text: "Research: Novi Sad", query: "res" }),
    );
    expect(html).toContain('data-testid="inbox-hit"');
    expect(html).toContain("Res");
    expect(html).toContain("earch: Novi Sad");
  });

  it("leaves unmatched text unmarked", () => {
    const html = renderToStaticMarkup(createElement(InboxHit, { text: "Lead", query: "res" }));
    expect(html).not.toContain("inbox-hit");
    expect(html).toContain("Lead");
  });
});
