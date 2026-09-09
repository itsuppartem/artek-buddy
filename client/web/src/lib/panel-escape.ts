export type HatchPanel =
  | "computer"
  | "settings"
  | "create"
  | "models"
  | "plugins"
  | "memory"
  | "routines"
  | "library"
  | "worklog"
  | null;

export type PanelEscapeAction = "close-overlay" | "close-settings" | "close-create" | "close-panel";

export function panelEscapeAction(opts: {
  computerOpen: boolean;
  panel: HatchPanel;
}): PanelEscapeAction | null {
  if (opts.computerOpen) return "close-overlay";
  if (opts.panel === "settings") return "close-settings";
  if (opts.panel === "create") return "close-create";
  if (opts.panel) return "close-panel";
  return null;
}
