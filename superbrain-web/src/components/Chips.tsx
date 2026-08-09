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

function CategoryPill({ category }: { category: string }) {
  const { bg, fg } = colorFor(category);
  return (
    <span
      className="font-display text-[11px] font-semibold uppercase tracking-wide px-2.5 py-1 rounded-full whitespace-nowrap"
      style={{ backgroundColor: bg, color: fg }}
    >
      {category}
    </span>
  );
}

/** Single pill for the thumbnail overlay — a post can carry up to 3
 * categories, but the overlay only ever shows the primary (first) one to
 * keep the image clean. See CategoryBadges for the full set. */
export function CategoryBadge({ category }: { category: string[] }) {
  if (!category || category.length === 0) return null;
  return <CategoryPill category={category[0]} />;
}

/** Full set of a post's categories (1-3), for use in the card body rather
 * than over the thumbnail. */
export function CategoryBadges({ category }: { category: string[] }) {
  if (!category || category.length === 0) return null;
  return (
    <span className="inline-flex flex-wrap gap-1.5">
      {category.map((c) => (
        <CategoryPill key={c} category={c} />
      ))}
    </span>
  );
}

/** Muted, neutral pills — deliberately not the vibrant category palette, so
 * language reads as descriptive metadata rather than a primary classification. */
export function LanguageBadges({ language }: { language: string[] }) {
  if (!language || language.length === 0) return null;
  return (
    <span className="inline-flex flex-wrap gap-1.5">
      {language.map((lang) => (
        <span
          key={lang}
          className="text-[11px] font-bold px-2.5 py-1 rounded-full bg-surface-2 text-ink-muted"
        >
          🌐 {lang}
        </span>
      ))}
    </span>
  );
}

/** Warning-toned badge for the "missing video, needs re-fetch" case — see
 * lib/media.ts::isMissingVideo for the exact condition. */
export function MissingVideoBadge() {
  return (
    <span className="font-display text-[11px] font-semibold px-2.5 py-1 rounded-full bg-yellow-ink text-bg whitespace-nowrap">
      🎬 no video
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
