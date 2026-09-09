import { externalHttpUrl } from "./markdown";

export function openOwnerBrowser(url: string): boolean {
  const href = externalHttpUrl(url);
  if (!href) return false;
  const popup = globalThis.open?.(href, "_blank") ?? null;
  if (popup) {
    try {
      popup.opener = null;
    } catch {
      // WebKit can throw when the opener is already detached.
    }
    return true;
  }
  globalThis.location.assign(href);
  return true;
}
