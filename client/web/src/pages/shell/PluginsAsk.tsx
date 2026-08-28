import { useRef } from "react";
import { pluginChipClickShouldFill } from "../../lib/plugins-ask";

export function PluginsAsk({
  apps,
  disabled,
  onAsk,
  onDismiss,
}: {
  apps: { slug: string; name: string }[];
  disabled?: boolean;
  onAsk: (name: string) => void;
  onDismiss: (slug: string) => void;
}) {
  const pointerDown = useRef(new Set<string>());
  if (!apps.length) return null;
  return (
    <div data-testid="plugins-ask" className="mb-2 flex flex-wrap gap-2">
      {apps.map((app) => (
        <span
          key={app.slug}
          className="flex items-center gap-1 rounded-[8px] border border-hairline bg-raised py-0.5 pl-2.5 pr-1 text-[13px] text-paper"
        >
          <button
            type="button"
            data-testid={`plugin-ask-${app.slug}`}
            aria-label={`Ask ${app.name}`}
            disabled={disabled}
            onPointerDown={() => {
              pointerDown.current.add(app.slug);
            }}
            onClick={(event) => {
              event.preventDefault();
              event.stopPropagation();
              if (!pluginChipClickShouldFill(pointerDown.current.has(app.slug))) return;
              pointerDown.current.delete(app.slug);
              onAsk(app.name);
            }}
            className="py-0.5 text-paper hover:text-tan disabled:opacity-40"
          >
            {app.name}
          </button>
          <button
            type="button"
            data-testid={`plugin-ask-${app.slug}-remove`}
            aria-label={`Remove ${app.name}`}
            disabled={disabled}
            onClick={(event) => {
              event.preventDefault();
              event.stopPropagation();
              onDismiss(app.slug);
            }}
            className="px-1.5 py-0.5 text-mute hover:text-paper disabled:opacity-40"
          >
            ✕
          </button>
        </span>
      ))}
    </div>
  );
}
