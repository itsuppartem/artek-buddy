import { describe, expect, it } from "vitest";
import { captureMessageAnchor, restoreThreadScroll } from "./thread-scroll";

function message(id: string, top: number, height: number): HTMLElement {
  const node = document.createElement("div");
  node.dataset.messageId = id;
  Object.defineProperty(node, "offsetTop", { value: top });
  Object.defineProperty(node, "offsetHeight", { value: height });
  return node;
}

describe("thread scroll anchors", () => {
  it("captures the first message that crosses the viewport top", () => {
    const root = document.createElement("div");
    Object.defineProperty(root, "scrollTop", { value: 120, writable: true });
    root.append(message("a", 0, 80), message("b", 80, 80), message("c", 160, 80));
    expect(captureMessageAnchor(root)).toEqual({ id: "b", fromTop: -40 });
  });

  it("pins to the latest when stick-to-latest is set", () => {
    const root = document.createElement("div");
    Object.defineProperty(root, "scrollTop", { value: 0, writable: true });
    Object.defineProperty(root, "scrollHeight", { value: 900 });
    restoreThreadScroll(root, { id: "b", fromTop: 12 }, true);
    expect(root.scrollTop).toBe(900);
  });

  it("restores an older message offset when not pinned", () => {
    const root = document.createElement("div");
    Object.defineProperty(root, "scrollTop", { value: 0, writable: true });
    const node = message("mid", 240, 60);
    root.append(node);
    root.querySelector = ((selector: string) =>
      selector.includes("mid") ? node : null) as typeof root.querySelector;
    restoreThreadScroll(root, { id: "mid", fromTop: 20 }, false);
    expect(root.scrollTop).toBe(220);
  });
});
