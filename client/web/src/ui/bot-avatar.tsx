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
  return (
    <div
      className={["relative overflow-hidden", className].filter(Boolean).join(" ")}
      style={{
        width: size,
        height: size,
        background: color,
        borderRadius: radius,
        flex: "none",
        boxShadow: "inset 0 0 0 1px rgba(0,0,0,0.22)",
      }}
      aria-hidden="true"
    >
      <svg viewBox="0 0 40 40" width={size} height={size} className="absolute inset-0">
        <path
          d="M8 25.2 20 11.4 32 25.2h-6.2L20 18.1l-5.8 7.1H8Z"
          fill="rgba(255,255,255,0.94)"
        />
        <rect x="13" y="27.2" width="14" height="3.1" rx="1.4" fill="rgba(255,255,255,0.78)" />
      </svg>
    </div>
  );
}
