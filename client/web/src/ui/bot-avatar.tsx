export function BotAvatar({
  color,
  size = 38,
  className,
}: {
  color: string;
  size?: number;
  className?: string;
}) {
  const radius = Math.round(size * 0.26);
  const inset = Math.max(2, Math.round(size * 0.08));
  return (
    <div
      data-testid="bot-avatar"
      className={["relative overflow-hidden", className].filter(Boolean).join(" ")}
      style={{
        width: size,
        height: size,
        background: color,
        borderRadius: radius,
        flex: "none",
        padding: inset,
        boxShadow: "inset 0 0 0 1px rgba(0,0,0,0.22)",
      }}
      aria-hidden="true"
    >
      <img
        src="/bot-mark.png"
        alt=""
        draggable={false}
        className="h-full w-full rounded-[inherit] object-cover"
        style={{ background: "rgba(22,19,16,0.35)" }}
      />
    </div>
  );
}
