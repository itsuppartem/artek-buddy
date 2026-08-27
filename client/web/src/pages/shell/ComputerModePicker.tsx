import { computerModeHint } from "../../lib/screen";
import type { ComputerMode } from "../../types";

export function ComputerModePicker({
  value,
  onChange,
}: {
  value: ComputerMode;
  onChange: (value: ComputerMode) => void;
}) {
  return (
    <div className="mt-4">
      <div className="text-[14px] text-mute">Computer</div>
      <div className="mt-2 grid grid-cols-2 gap-2">
        {(["team", "dedicated"] as const).map((mode) => (
          <button
            key={mode}
            type="button"
            data-testid={mode === "team" ? "computer-mode-team" : "computer-mode-private"}
            aria-pressed={value === mode}
            onClick={() => onChange(mode)}
            className={`rounded-[11px] border px-3.5 py-3 text-[14px] capitalize ${
              value === mode ? "border-mute bg-plate text-paper" : "border-hairline text-mute"
            }`}
          >
            {mode === "team" ? "Team" : "Private"}
          </button>
        ))}
      </div>
      <p data-testid="computer-mode-hint" className="mt-2 text-[12.5px] leading-5 text-mute">
        {computerModeHint(value)}
      </p>
    </div>
  );
}
