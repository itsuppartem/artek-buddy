export function PluginsAsk({
  apps,
  disabled,
  onAsk,
}: {
  apps: { slug: string; name: string }[];
  disabled?: boolean;
  onAsk: (name: string) => void;
}) {
  if (!apps.length) return null;
  return (
    <div data-testid="plugins-ask" className="mb-2 flex flex-wrap gap-2">
      {apps.map((app) => (
        <button
          key={app.slug}
          type="button"
          data-testid={`plugin-ask-${app.slug}`}
          aria-label={`Ask ${app.name}`}
          disabled={disabled}
          onClick={() => onAsk(app.name)}
          className="rounded-[8px] border border-hairline bg-raised px-2.5 py-1 text-[13px] text-paper hover:bg-plate disabled:opacity-40"
        >
          {app.name}
        </button>
      ))}
    </div>
  );
}
