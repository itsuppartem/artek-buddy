import { desktopBridge, windowChromeKind } from "../lib/desktop";

export function WindowChrome() {
  const desktop = desktopBridge();
  const kind = windowChromeKind(desktop);
  if (kind === "spacer") {
    return <div className="h-7 w-[84px]" aria-hidden="true" />;
  }
  if (kind === "darwin") {
    return <div className="app-drag h-7 w-[84px]" aria-hidden="true" />;
  }
  return (
    <div className="app-drag flex items-center gap-0.5">
      <button
        type="button"
        className="app-no-drag grid h-7 w-7 place-items-center"
        aria-label="Close"
        onClick={() => desktop?.window.close()}
      >
        <span className="h-3 w-3 rounded-full bg-close" />
      </button>
      <button
        type="button"
        className="app-no-drag grid h-7 w-7 place-items-center"
        aria-label="Minimize"
        onClick={() => desktop?.window.minimize()}
      >
        <span className="h-3 w-3 rounded-full bg-min" />
      </button>
      <button
        type="button"
        className="app-no-drag grid h-7 w-7 place-items-center"
        aria-label="Fullscreen"
        onClick={() => desktop?.window.toggleMaximize()}
      >
        <span className="h-3 w-3 rounded-full bg-full" />
      </button>
    </div>
  );
}
