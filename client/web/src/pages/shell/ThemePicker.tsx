import { useState } from "react";
import { applyThemePreference, readThemePreference, type ThemePreference } from "../../lib/theme";

const OPTIONS: { id: ThemePreference; label: string }[] = [
  { id: "system", label: "System" },
  { id: "light", label: "Light" },
  { id: "dark", label: "Dark" },
];

const HELP: Record<ThemePreference, string> = {
  system: "Follows Ubuntu and changes with it.",
  light: "Keeps this device in light mode.",
  dark: "Keeps this device in dark mode.",
};

export function ThemePicker() {
  const [preference, setPreference] = useState(readThemePreference);

  function choose(next: ThemePreference) {
    applyThemePreference(next);
    setPreference(next);
  }

  return (
    <fieldset data-testid="theme-picker" className="mt-6">
      <legend className="mb-2 font-mono text-[9px] tracking-[0.06em] text-mute uppercase">
        Appearance
      </legend>
      <div
        role="radiogroup"
        aria-label="Appearance"
        className="grid grid-cols-3 gap-1 rounded-[12px] border border-hairline bg-raised p-1"
      >
        {OPTIONS.map((option) => {
          const active = preference === option.id;
          return (
            <label key={option.id} className="cursor-pointer">
              <input
                type="radio"
                name="appearance"
                value={option.id}
                checked={active}
                aria-checked={active}
                onChange={() => choose(option.id)}
                className="peer sr-only"
              />
              <span
                className={`flex min-h-10 items-center justify-center rounded-[9px] px-2 text-[12px] font-bold transition peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-tan ${
                  active ? "bg-plate text-paper shadow-sm" : "text-mute hover:text-paper"
                }`}
              >
                {option.label}
              </span>
            </label>
          );
        })}
      </div>
      <p className="mt-2 text-[11.5px] leading-4 text-mute">{HELP[preference]}</p>
    </fieldset>
  );
}
