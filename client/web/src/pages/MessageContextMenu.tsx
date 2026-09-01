import { useEffect, useRef, useState } from "react";
import type { ContextMenuPosition } from "./BotContextMenu";

export function MessageContextMenu({
  position,
  url,
  canCopy,
  onClose,
  onCopy,
  onCopyUrl,
  onOpenUrl,
  onReply,
}: {
  position: ContextMenuPosition;
  url?: string;
  canCopy: boolean;
  onClose: () => void;
  onCopy: () => Promise<boolean>;
  onCopyUrl: () => Promise<boolean>;
  onOpenUrl: () => void;
  onReply: () => void;
}) {
  const firstItem = useRef<HTMLButtonElement>(null);
  const [copyState, setCopyState] = useState<"idle" | "copied" | "failed">("idle");
  const [urlCopyState, setUrlCopyState] = useState<"idle" | "copied" | "failed">("idle");

  useEffect(() => {
    firstItem.current?.focus();
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  const menuWidth = 180;
  const menuHeight = url ? 196 : 108;
  const margin = 8;
  const left = Math.min(position.x, window.innerWidth - menuWidth - margin);
  const top = Math.min(position.y, window.innerHeight - menuHeight - margin);
  const itemClass =
    "flex w-full items-center gap-3 rounded-[11px] px-3 py-2.5 text-left text-[15px] text-paper hover:bg-raised focus-visible:bg-raised focus-visible:ring-2 focus-visible:ring-tan disabled:text-mute";

  return (
    <div className="fixed inset-0 z-40">
      <button
        type="button"
        aria-label="Close message menu"
        className="absolute inset-0 cursor-default"
        onClick={onClose}
        onContextMenu={(event) => {
          event.preventDefault();
          onClose();
        }}
      />
      <div
        role="menu"
        aria-label="Message actions"
        className="fixed z-10 w-[180px] rounded-[14px] border border-hairline bg-plate p-1.5 shadow-[0_24px_60px_rgba(0,0,0,.62)]"
        style={{ left: Math.max(margin, left), top: Math.max(margin, top) }}
      >
        <button
          ref={firstItem}
          type="button"
          role="menuitem"
          className={itemClass}
          disabled={!canCopy}
          onClick={() => {
            void onCopy().then((copied) => setCopyState(copied ? "copied" : "failed"));
          }}
        >
          {copyState === "copied" ? "Copied" : copyState === "failed" ? "Copy failed" : "Copy"}
        </button>
        {url ? (
          <>
            <button type="button" role="menuitem" className={itemClass} onClick={onOpenUrl}>
              Open in browser
            </button>
            <button
              type="button"
              role="menuitem"
              aria-live="polite"
              className={itemClass}
              onClick={() => {
                void onCopyUrl().then((copied) => setUrlCopyState(copied ? "copied" : "failed"));
              }}
            >
              {urlCopyState === "copied"
                ? "URL copied"
                : urlCopyState === "failed"
                  ? "Copy failed"
                  : "Copy URL"}
            </button>
          </>
        ) : null}
        <button type="button" role="menuitem" className={itemClass} onClick={onReply}>
          Reply
        </button>
      </div>
    </div>
  );
}
