import type { ReactNode } from "react";
import { IconChat, IconLibrary, IconRoutines, IconToday } from "../../ui/icons";

export type WorkspaceView = "today" | "chats" | "routines" | "library";

export function WorkspaceRail({
  active,
  attentionCount,
  onToday,
  onChats,
  onRoutines,
  onLibrary,
}: {
  active: WorkspaceView;
  attentionCount: number;
  onToday: () => void;
  onChats: () => void;
  onRoutines: () => void;
  onLibrary: () => void;
}) {
  return (
    <nav
      data-testid="workspace-rail"
      aria-label="Workspace"
      className="app-drag flex w-[88px] shrink-0 flex-col bg-navy px-2 py-3 text-nav-mute"
    >
      <img
        src="/favicon.png"
        alt=""
        width={28}
        height={28}
        className="mx-auto mb-3 h-7 w-7 rounded-[9px]"
      />
      <RailButton active={active === "today"} label="Today" onClick={onToday}>
        <IconToday />
      </RailButton>
      <RailButton active={active === "chats"} label="Chats" onClick={onChats}>
        <span className="relative">
          <IconChat />
          {attentionCount > 0 ? (
            <span
              data-testid="workspace-attention-count"
              className="absolute -top-2 -right-2 grid h-[17px] min-w-[17px] place-items-center rounded-full border-2 border-navy bg-copper px-0.5 text-[8px] font-bold text-white"
            >
              {Math.min(attentionCount, 9)}
            </span>
          ) : null}
        </span>
      </RailButton>
      <RailButton active={active === "routines"} label="Routines" onClick={onRoutines}>
        <IconRoutines />
      </RailButton>
      <RailButton active={active === "library"} label="Library" onClick={onLibrary}>
        <IconLibrary />
      </RailButton>
    </nav>
  );
}

function RailButton({
  active,
  label,
  onClick,
  children,
}: {
  active: boolean;
  label: string;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      aria-current={active ? "page" : undefined}
      onClick={onClick}
      className={`app-no-drag mb-1 flex min-h-[58px] flex-col items-center justify-center gap-1 rounded-[11px] text-[10px] font-medium transition ${
        active ? "bg-navy-raised text-white" : "text-nav-mute hover:bg-navy-raised hover:text-white"
      }`}
    >
      {children}
      <span>{label}</span>
    </button>
  );
}
