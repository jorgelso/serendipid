const CATEGORY_COLORS = [
  "var(--cat-clay)",
  "var(--cat-sage)",
  "var(--cat-ochre)",
  "var(--cat-plum)",
  "var(--cat-teal)",
  "var(--cat-brick)",
  "var(--cat-olive)",
  "var(--cat-dust)",
];

function colorForCategory(category: string): string {
  let hash = 0;
  for (let i = 0; i < category.length; i++) {
    hash = (hash * 31 + category.charCodeAt(i)) % CATEGORY_COLORS.length;
  }
  return CATEGORY_COLORS[Math.abs(hash) % CATEGORY_COLORS.length];
}

export function CategoryBadge({ category }: { category: string | null }) {
  if (!category) return null;
  const color = colorForCategory(category);
  return (
    <span
      className="font-label text-[11px] uppercase tracking-wide px-2 py-0.5 rounded-sm border"
      style={{ color, borderColor: color, backgroundColor: "color-mix(in srgb, " + color + " 12%, transparent)" }}
    >
      {category}
    </span>
  );
}

export function TagChips({ tags, limit }: { tags: string[]; limit?: number }) {
  if (!tags || tags.length === 0) return null;
  const shown = limit ? tags.slice(0, limit) : tags;
  const remaining = limit && tags.length > limit ? tags.length - limit : 0;
  return (
    <span className="inline-flex flex-wrap gap-1.5">
      {shown.map((tag) => (
        <span
          key={tag}
          className="font-label text-[11px] px-2 py-0.5 rounded-sm bg-paper-raised border border-line text-ink-muted"
        >
          {tag}
        </span>
      ))}
      {remaining > 0 && (
        <span className="font-label text-[11px] px-2 py-0.5 text-ink-muted">+{remaining}</span>
      )}
    </span>
  );
}
