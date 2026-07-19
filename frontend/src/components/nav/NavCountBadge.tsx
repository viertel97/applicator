// Small count pill for nav items. Hidden when count is 0.
export function NavCountBadge({ count }: { count: number }) {
  if (count <= 0) return null;
  return (
    <span className="inline-flex items-center justify-center min-w-[1.25rem] h-5 px-1 rounded-full bg-red-600 text-white text-xs font-semibold">
      {count}
    </span>
  );
}
