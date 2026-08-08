import LazyPostList from "./LazyPostList";

export default function MoreSection({
  groupedShortcodesByCategory,
}: {
  groupedShortcodesByCategory: Record<string, string[]>;
}) {
  const categories = Object.keys(groupedShortcodesByCategory).sort();
  const total = categories.reduce((sum, c) => sum + groupedShortcodesByCategory[c].length, 0);

  if (total === 0) return null;

  return (
    <details className="rounded-md border border-line">
      <summary className="cursor-pointer select-none list-none flex items-center gap-3 px-4 py-3">
        <span aria-hidden className="text-ink-muted">
          &#9656;
        </span>
        <span className="font-display text-lg">Everything else</span>
        <span className="ml-auto font-label text-[11px] uppercase tracking-wide text-ink-muted">
          {total} not yet part of a theme
        </span>
      </summary>
      <div className="border-t border-line px-4 py-3 space-y-1">
        {categories.map((category) => (
          <LazyPostList
            key={category}
            label={category}
            shortcodes={groupedShortcodesByCategory[category]}
            variant="category"
          />
        ))}
      </div>
    </details>
  );
}
