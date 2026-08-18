export function embeddableScreenUrl(url: string | null | undefined): string | null {
  if (!url) return null;
  if (url.startsWith("/novnc/")) return url;
  return null;
}

const NOVNC_RE =
  /^\/novnc\/([A-Za-z0-9_-]+)\/(\d+)\/(view|control)\/(\d+)\.([A-Za-z0-9_-]{43})/;
const SCREEN_REFRESH_BEFORE_MS = 2 * 60 * 1000;

export function screenTargetKey(url: string | null | undefined): string | null {
  const match = embeddableScreenUrl(url)?.match(NOVNC_RE);
  if (!match) return null;
  return `${match[1]}/${match[2]}/${match[3]}`;
}

export function screenExpiresAt(url: string | null | undefined): number | null {
  const match = embeddableScreenUrl(url)?.match(NOVNC_RE);
  if (!match) return null;
  const expires = Number(match[4]);
  return Number.isFinite(expires) ? expires : null;
}

export function shouldRefreshScreenUrl(
  current: string | null | undefined,
  nowMs = Date.now(),
): boolean {
  if (!embeddableScreenUrl(current) || !screenTargetKey(current)) return true;
  const expires = screenExpiresAt(current);
  if (expires == null) return true;
  return expires - nowMs <= SCREEN_REFRESH_BEFORE_MS;
}

export function shouldReplaceScreenUrl(
  current: string | null | undefined,
  next: string | null | undefined,
  nowMs = Date.now(),
): boolean {
  const cur = embeddableScreenUrl(current);
  const nxt = embeddableScreenUrl(next);
  if (cur === nxt) return false;
  if (!nxt) return Boolean(cur);
  if (!cur) return true;
  if (screenTargetKey(cur) !== screenTargetKey(nxt)) return true;
  return shouldRefreshScreenUrl(cur, nowMs);
}

export function screenIframeSandbox(url: string | null | undefined): string {
  return embeddableScreenUrl(url) ? "allow-scripts allow-same-origin allow-forms" : "";
}

export function previewPointerEvents(): "none" {
  return "none";
}

export function overlayPointerEvents(controlHolder: string | null | undefined): "auto" | "none" {
  return controlHolder === "user" ? "auto" : "none";
}

export function shouldTakeControl(source: "preview" | "button"): boolean {
  return source === "button";
}

export function shouldAutoBoot(
  state: string | null | undefined,
  screenUrl: string | null | undefined,
  alreadyBooted: boolean,
): boolean {
  if (alreadyBooted && state === "running" && screenUrl) return false;
  if (state === "booting") return false;
  return true;
}

export function computerLabel(mode: string | null | undefined, name: string): string {
  return mode === "dedicated" ? `${name}’s computer` : "Team computer";
}
