import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { type HostSearchHit, SearchHits } from "./SearchHits";

const hit: HostSearchHit = {
  id: "sdoc_1",
  documentKind: "message",
  resourceId: "bot_abc",
  sourceId: "msg_1",
  title: "Lead",
  snippet: "unique-fts-token in the transcript",
};

describe("SearchHits", () => {
  it("renders a host hit that opens the owning chat", () => {
    const html = renderToStaticMarkup(
      createElement(SearchHits, {
        query: "unique-fts",
        hits: [hit],
        onOpenBot: vi.fn(),
      }),
    );
    expect(html).toContain('data-testid="search-hits"');
    expect(html).toContain('data-testid="search-hit"');
    expect(html).toContain("bot_abc");
    expect(html).toContain("unique-fts");
    expect(html).toContain("inbox-hit");
  });
});
