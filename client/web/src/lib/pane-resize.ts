export type ResizablePane = "left" | "right";

const LIMITS: Record<ResizablePane, { min: number; max: number }> = {
  left: { min: 220, max: 420 },
  right: { min: 300, max: 720 },
};

export function paneWidthLimits(pane: ResizablePane): { min: number; max: number } {
  return LIMITS[pane];
}

export function clampPaneWidth(pane: ResizablePane, width: number): number {
  const { min, max } = LIMITS[pane];
  return Math.min(max, Math.max(min, Math.round(width)));
}

export function paneWidthAfterDrag(
  pane: ResizablePane,
  startWidth: number,
  horizontalDelta: number,
): number {
  return clampPaneWidth(pane, startWidth + (pane === "left" ? horizontalDelta : -horizontalDelta));
}

export function paneWidthAfterKey(
  pane: ResizablePane,
  width: number,
  key: string,
  step = 16,
): number {
  if (key !== "ArrowLeft" && key !== "ArrowRight") return width;
  const horizontalDelta = key === "ArrowRight" ? step : -step;
  return paneWidthAfterDrag(pane, width, horizontalDelta);
}

export function constrainPaneWidth(
  pane: ResizablePane,
  requestedWidth: number,
  layout: {
    viewportWidth: number;
    otherPaneWidth: number;
    railWidth: number;
    separatorWidth: number;
    conversationMinWidth: number;
  },
): number {
  const available =
    layout.viewportWidth -
    layout.otherPaneWidth -
    layout.railWidth -
    layout.separatorWidth * 2 -
    layout.conversationMinWidth;
  return clampPaneWidth(pane, Math.min(requestedWidth, available));
}
