export type ScrollAnchor = { id: string; fromTop: number };

export function captureMessageAnchor(element: HTMLElement): ScrollAnchor | null {
  const nodes = element.querySelectorAll<HTMLElement>("[data-message-id]");
  for (const node of nodes) {
    const id = node.dataset.messageId;
    if (!id) continue;
    if (node.offsetTop + node.offsetHeight > element.scrollTop) {
      return { id, fromTop: node.offsetTop - element.scrollTop };
    }
  }
  return null;
}

function escapeMessageId(value: string): string {
  if (typeof CSS !== "undefined" && typeof CSS.escape === "function") {
    return CSS.escape(value);
  }
  return value.replace(/\\/g, "\\\\").replace(/"/g, '\\"');
}

export function restoreThreadScroll(
  element: HTMLElement,
  anchor: ScrollAnchor | null,
  stickToLatest: boolean,
): void {
  if (stickToLatest) {
    element.scrollTop = element.scrollHeight;
    return;
  }
  if (!anchor) return;
  const node = element.querySelector<HTMLElement>(
    `[data-message-id="${escapeMessageId(anchor.id)}"]`,
  );
  if (!node) return;
  element.scrollTop = node.offsetTop - anchor.fromTop;
}
