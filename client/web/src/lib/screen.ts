export function embeddableScreenUrl(url: string | null | undefined): string | null {
  if (!url) return null;
  if (url.startsWith("/novnc/")) return url;
  return null;
}

const NOVNC_RE = /^\/novnc\/([^/?#]+)\/(\d+)\/(view|control)(?:\/(\d+)\.([A-Za-z0-9_-]+))?/;
const SCREEN_REFRESH_BEFORE_MS = 2 * 60 * 1000;

export function screenTargetKey(url: string | null | undefined): string | null {
  const match = embeddableScreenUrl(url)?.match(NOVNC_RE);
  if (!match) return null;
  return `${match[1]}/${match[2]}/${match[3]}`;
}

export function screenExpiresAt(url: string | null | undefined): number | null {
  const match = embeddableScreenUrl(url)?.match(NOVNC_RE);
  if (!match || match[4] == null) return null;
  const expires = Number(match[4]);
  if (!Number.isFinite(expires) || expires < 1_000_000_000_000) return null;
  return expires;
}

export function shouldRefreshScreenUrl(
  current: string | null | undefined,
  nowMs = Date.now(),
): boolean {
  if (!embeddableScreenUrl(current)) return true;
  const expires = screenExpiresAt(current);
  if (expires == null) return false;
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

export const OWNER_ACTIVITY_GAP_MS = 5_000;

export function shouldReportOwnerActivity(
  lastMs: number,
  nowMs: number,
  minGapMs = OWNER_ACTIVITY_GAP_MS,
): boolean {
  return nowMs - lastMs >= minGapMs;
}

export function shouldTakeControl(source: "preview" | "button"): boolean {
  return source === "button";
}

export function shouldFetchScreenUrl(
  paneOpen: boolean,
  overlayOpen: boolean,
  state: string | null | undefined,
): boolean {
  if (!paneOpen && !overlayOpen) return false;
  return state === "running" || state === "booting";
}

export function shouldAutoBoot(
  state: string | null | undefined,
  screenUrl: string | null | undefined,
  alreadyBooted: boolean,
): boolean {
  if (state === "booting" || state === "error") return false;
  if (alreadyBooted && (state === "running" || state === "stopped" || state === "suspended")) {
    return false;
  }
  if (alreadyBooted && state === "running" && screenUrl) return false;
  return true;
}

export function computerPaneState(
  state: string | null | undefined,
  booting: boolean,
): "running" | "booting" | "error" | "sleeping" | "offline" {
  if (booting || state === "booting") return "booting";
  if (state === "running") return "running";
  if (state === "error") return "error";
  if (state === "suspended") return "sleeping";
  return "offline";
}

export function computerLabel(mode: string | null | undefined, name: string): string {
  return mode === "dedicated" ? `${name}’s computer` : "Team computer";
}

export function computerModeHint(mode: string | null | undefined): string {
  return mode === "dedicated"
    ? "This bot gets its own Linux container and home on the Pi. It can run at the same time as the shared desktop."
    : "Team bots share one Linux desktop and home. If one is using it, the others wait.";
}

export function isScreenFailureDocument(text: string | null | undefined): boolean {
  const value = (text || "").trim();
  if (!value) return false;
  return (
    value.includes("screen unreachable") ||
    value.includes("Desktop is starting") ||
    value.trimStart().startsWith('{"detail"')
  );
}

export function screenFrameLooksFailed(frame: HTMLIFrameElement | null): boolean {
  try {
    const doc = frame?.contentDocument;
    if (!doc) return false;
    if (doc.documentElement?.getAttribute("data-artek-screen-error") === "1") return true;
    return isScreenFailureDocument(doc.body?.innerText);
  } catch {
    return false;
  }
}
