import type { ButtonHTMLAttributes } from "react";

export function IconButton({
  className = "",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      className={`inline-flex h-11 w-11 items-center justify-center rounded text-muted hover:text-fg hover:bg-surface2 focus:outline-none focus:ring-2 focus:ring-ring ${className}`}
      {...props}
    />
  );
}
