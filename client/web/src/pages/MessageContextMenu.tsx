import { useEffect, useRef } from "react";
import type { ContextMenuPosition } from "./BotContextMenu";

export function MessageContextMenu({
  position,
  onClose,
  onReply,
}: {
  position: ContextMenuPosition;
  onClose: () => void;
  onReply: () => void;
}) {
  const firstItem = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    firstItem.current?.focus();
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  const menuWidth = 180;
  const menuHeight = 56;
  const margin = 8;
  const left = Math.min(position.x, window.innerWidth - menuWidth - margin);
  const top = Math.min(position.y, window.innerHeight - menuHeight - margin);

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
        className="fixed w-[180px] rounded-[14px] border border-[#343438] bg-[#1A1A1D] p-1.5 shadow-[0_24px_60px_rgba(0,0,0,.62)]"
        style={{ left: Math.max(margin, left), top: Math.max(margin, top) }}
      >
        <button
          ref={firstItem}
          type="button"
          role="menuitem"
          className="flex w-full items-center gap-3 rounded-[11px] px-3 py-2.5 text-left text-[15px] text-[#ECECEE] outline-none hover:bg-[#29292D] focus-visible:bg-[#29292D]"
          onClick={onReply}
        >
          Reply
        </button>
      </div>
    </div>
  );
}
