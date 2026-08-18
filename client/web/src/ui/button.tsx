import type { ButtonHTMLAttributes } from "react";

const variants = {
  default: "bg-[#121215] text-[#FBFBF9] hover:bg-[#26262B]",
  cream: "bg-[#F1F1EF] text-[#17171A] hover:opacity-90",
  outline: "border border-[#26262A] text-[#ECECEE] hover:bg-[#1A1A1D]",
  ghost: "text-[#C9C9CE] hover:bg-[#131315]",
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
        "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-[13px] text-sm font-medium transition-all disabled:pointer-events-none disabled:opacity-50",
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
