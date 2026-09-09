export function hatchIsOpen(panel: string | null | undefined, hasActive: boolean): boolean {
  if (!panel) return false;
  if (hasActive) return true;
  return panel === "create" || panel === "library" || panel === "models" || panel === "plugins";
}

export function hatchPointerEvents(open: boolean): "none" | "auto" {
  return open ? "auto" : "none";
}
