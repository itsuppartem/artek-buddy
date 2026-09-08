import { describe, expect, it } from "vitest";
import { captureMessageAnchor, restoreThreadScroll } from "./thread-scroll";

type FakeNode = {
  dataset: { messageId: string };
  offsetTop: number;
  offsetHeight: number;
};

function message(id: string, top: number, height: number): FakeNode {
  return { dataset: { messageId: id }, offsetTop: top, offsetHeight: height };
}

function rootOf(nodes: FakeNode[], scrollTop = 0, scrollHeight = 0): HTMLElement {
  const root = {
    scrollTop,
    scrollHeight,
    querySelectorAll: (_selector: string) => nodes,
    querySelector: (selector: string) => {
      const id = /data-message-id="([^"]+)"/.exec(selector)?.[1];
      return nodes.find((node) => node.dataset.messageId === id) ?? null;
    },
  };
  return root as unknown as HTMLElement;
}

describe("thread scroll anchors", () => {
  it("captures the first message that crosses the viewport top", () => {
    const root = rootOf([message("a", 0, 80), message("b", 80, 80), message("c", 160, 80)], 120);
    expect(captureMessageAnchor(root)).toEqual({ id: "b", fromTop: -40 });
  });

  it("pins to the latest when stick-to-latest is set", () => {
    const root = rootOf([], 0, 900);
    restoreThreadScroll(root, { id: "b", fromTop: 12 }, true);
    expect(root.scrollTop).toBe(900);
  });

  it("restores an older message offset when not pinned", () => {
    const root = rootOf([message("mid", 240, 60)]);
    restoreThreadScroll(root, { id: "mid", fromTop: 20 }, false);
    expect(root.scrollTop).toBe(220);
  });
});
