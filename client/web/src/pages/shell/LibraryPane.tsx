import { IconClose } from "../../ui/icons";
import { ThemePicker } from "./ThemePicker";

export function LibraryPane({
  botName,
  hasActiveBot,
  modelsReady,
  showRoutines,
  onOpenPlugins,
  onOpenModels,
  onOpenMemory,
  onOpenRoutines,
  onOpenSettings,
  onClose,
}: {
  botName?: string;
  hasActiveBot: boolean;
  modelsReady: boolean;
  showRoutines: boolean;
  onOpenPlugins: () => void;
  onOpenModels: () => void;
  onOpenMemory: () => void;
  onOpenRoutines: () => void;
  onOpenSettings: () => void;
  onClose: () => void;
}) {
  return (
    <div data-testid="library-pane">
      <header className="flex items-start justify-between gap-4">
        <div>
          <p className="font-mono text-[10px] tracking-[0.07em] text-tan uppercase">
            Reusable capabilities
          </p>
          <h2 className="mt-1.5 text-[18px] font-bold tracking-[-0.03em] text-paper">Library</h2>
          <p className="mt-1 text-[12px] text-mute">Connections, models, and bot context.</p>
        </div>
        <button
          type="button"
          aria-label="Close Library"
          onClick={onClose}
          className="grid h-9 w-9 place-items-center rounded-[10px] border border-hairline bg-raised text-paper"
        >
          <IconClose />
        </button>
      </header>

      <section className="mt-6">
        <p className="mb-2 font-mono text-[9px] tracking-[0.06em] text-mute uppercase">Workspace</p>
        <LibraryRow
          testId="library-open-plugins"
          title="Connections"
          body="Apps and external tools available to bots"
          onClick={onOpenPlugins}
        />
        <LibraryRow
          testId="library-open-models"
          title="Models"
          body="Providers, reasoning, and the model used next"
          dataModelsReady={modelsReady}
          onClick={onOpenModels}
        />
      </section>

      <ThemePicker />

      <section className="mt-6">
        <p className="mb-2 font-mono text-[9px] tracking-[0.06em] text-mute uppercase">
          {botName ? `Selected bot · ${botName}` : "Select a bot"}
        </p>
        <LibraryRow
          testId="library-open-memory"
          title="Memory"
          body="Identity, work context, and standing rules"
          disabled={!hasActiveBot}
          onClick={onOpenMemory}
        />
        {showRoutines ? (
          <LibraryRow
            title="Routines"
            body="Review recurring work created from successful tasks"
            disabled={!hasActiveBot}
            onClick={onOpenRoutines}
          />
        ) : null}
        <LibraryRow
          testId="library-open-settings"
          title="Bot profile & access"
          body="Role, instructions, secrets, and desktop mode"
          disabled={!hasActiveBot}
          onClick={onOpenSettings}
        />
      </section>
    </div>
  );
}

function LibraryRow({
  testId,
  title,
  body,
  disabled = false,
  dataModelsReady,
  onClick,
}: {
  testId?: string;
  title: string;
  body: string;
  disabled?: boolean;
  dataModelsReady?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      data-testid={testId}
      data-models-ready={dataModelsReady == null ? undefined : dataModelsReady ? "true" : "false"}
      disabled={disabled}
      onClick={onClick}
      className="flex min-h-[64px] w-full items-center justify-between gap-3 border-b border-hairline py-3 text-left disabled:opacity-40"
    >
      <span className="min-w-0">
        <strong className="block text-[13px] text-paper">{title}</strong>
        <span className="mt-1 block text-[11.5px] leading-4 text-mute">{body}</span>
      </span>
      <span className="text-[18px] text-tan" aria-hidden="true">
        ›
      </span>
    </button>
  );
}
