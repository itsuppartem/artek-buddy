import type { ButtonHTMLAttributes } from "react";

const variants = {
  default: "bg-raised text-paper hover:bg-plate",
  cream: "bg-tan text-ink hover:bg-tan-press",
  outline: "border border-hairline text-paper hover:bg-raised",
  ghost: "text-paper hover:bg-raised",
} as const;

const sizes = {
  default: "h-10 px-4",
  sm: "h-8 px-3 text-[13px]",
} as const;

export function Button({
  className,
  variant = "default",
  size = "default",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: keyof typeof variants;
  size?: keyof typeof sizes;
}) {
  return (
    <button
      className={[
        "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-[10px] text-sm font-medium transition-all disabled:pointer-events-none disabled:opacity-50",
        variants[variant],
        sizes[size],
        className,
      ]
        .filter(Boolean)
        .join(" ")}
      {...props}
    />
  );
}
