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
    `[data-message-id="${CSS.escape(anchor.id)}"]`,
  );
  if (!node) return;
  element.scrollTop = node.offsetTop - anchor.fromTop;
}
