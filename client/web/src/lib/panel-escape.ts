export type HatchPanel = "computer" | "settings" | "create" | "models" | "plugins" | null;

export type PanelEscapeAction = "close-overlay" | "close-settings" | "close-create";

export function panelEscapeAction(opts: {
  computerOpen: boolean;
  panel: HatchPanel;
}): PanelEscapeAction | null {
  if (opts.computerOpen) return "close-overlay";
  if (opts.panel === "settings") return "close-settings";
  if (opts.panel === "create") return "close-create";
  return null;
}
