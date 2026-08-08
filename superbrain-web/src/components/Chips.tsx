const PALETTE = [
  { bg: "var(--color-coral-soft)", fg: "var(--color-coral-ink)" },
  { bg: "var(--color-teal-soft)", fg: "var(--color-teal-ink)" },
  { bg: "var(--color-yellow-soft)", fg: "var(--color-yellow-ink)" },
  { bg: "var(--color-lavender-soft)", fg: "var(--color-lavender-ink)" },
  { bg: "var(--color-mint-soft)", fg: "var(--color-mint-ink)" },
  { bg: "var(--color-rose-soft)", fg: "var(--color-rose-ink)" },
  { bg: "var(--color-sky-soft)", fg: "var(--color-sky-ink)" },
];

export function colorFor(label: string): { bg: string; fg: string } {
  let hash = 0;
  for (let i = 0; i < label.length; i++) {
    hash = (hash * 31 + label.charCodeAt(i)) % PALETTE.length;
  }
  return PALETTE[Math.abs(hash) % PALETTE.length];
}

export function CategoryBadge({ category }: { category: string | null }) {
  if (!category) return null;
  const { bg, fg } = colorFor(category);
  return (
    <span
      className="font-display text-[11px] font-semibold uppercase tracking-wide px-2.5 py-1 rounded-full"
      style={{ backgroundColor: bg, color: fg }}
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
      {shown.map((tag) => {
        const { bg, fg } = colorFor(tag);
        return (
          <span
            key={tag}
            className="text-[11px] font-bold px-2.5 py-1 rounded-full"
            style={{ backgroundColor: bg, color: fg }}
          >
            {tag}
          </span>
        );
      })}
      {remaining > 0 && (
        <span className="text-[11px] font-bold px-2 py-1 text-ink-muted">+{remaining}</span>
      )}
    </span>
  );
}
