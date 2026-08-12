import type { ChangelogResponse } from "@/types/domain";

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
 * than over the thumbnail. Deduped — a post whose category array has a
 * repeated label (a data-quality slip upstream, not the common case) would
 * otherwise render the same pill twice with a duplicate React key. */
export function CategoryBadges({ category }: { category: string[] }) {
  if (!category || category.length === 0) return null;
  return (
    <span className="inline-flex flex-wrap gap-1.5">
      {Array.from(new Set(category)).map((c) => (
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
      {Array.from(new Set(language)).map((lang) => (
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

/** Colored "N versions behind" pill for a post whose analysis_version is
 * older than the pipeline's current_version (see backend's /changelog and
 * CURRENT_ANALYSIS_VERSION). Color is a continuous red→green spectrum via
 * CSS color-mix() between the existing mint (green, one version behind) and
 * coral (red, as outdated as possible — analysis_version 0) tokens, so it
 * tracks light/dark theme automatically without new hex values or JS color
 * math. Renders nothing while the changelog hasn't loaded yet, or once the
 * post is already current. */
export function VersionBehindBadge({
  analysisVersion,
  changelog,
}: {
  analysisVersion: number;
  changelog: ChangelogResponse | null;
}) {
  if (!changelog || changelog.current_version == null) return null;
  const versionsBehind = changelog.current_version - analysisVersion;
  if (versionsBehind <= 0) return null;

  const span = Math.max(changelog.current_version - 1, 1);
  const percent = Math.min(1, Math.max(0, (versionsBehind - 1) / span)) * 100;
  const bg = `color-mix(in srgb, var(--color-mint-soft) ${100 - percent}%, var(--color-coral-soft) ${percent}%)`;
  const fg = `color-mix(in srgb, var(--color-mint-ink) ${100 - percent}%, var(--color-coral-ink) ${percent}%)`;
  const label = `${versionsBehind} version${versionsBehind === 1 ? "" : "s"} behind`;

  return (
    <span
      title={`Analyzed with an older pipeline version — ${label} the current one`}
      className="shrink-0 text-[11px] font-bold px-2 py-0.5 rounded-full whitespace-nowrap"
      style={{ backgroundColor: bg, color: fg }}
    >
      {label}
    </span>
  );
}

/** Thumbnail-overlay badge for a post's 1-5 importance score (backend/core/
 * importance.py) — renders nothing for unscored posts (null), same "don't
 * claim a score that isn't there" reasoning as the rest of this field.
 * Intensity scales continuously from neutral (1) to a saturated yellow (5)
 * via CSS color-mix(), same technique as VersionBehindBadge's red→green
 * gradient, so it tracks light/dark theme automatically. */
export function ImportanceBadge({ importance }: { importance: number | null }) {
  if (importance == null) return null;
  const percent = ((importance - 1) / 4) * 100;
  const bg = `color-mix(in srgb, var(--color-surface-2) ${100 - percent}%, var(--color-yellow-soft) ${percent}%)`;
  const fg = `color-mix(in srgb, var(--color-ink-muted) ${100 - percent}%, var(--color-yellow-ink) ${percent}%)`;

  return (
    <span
      title={`Importance: ${importance}/5`}
      className="shrink-0 font-display text-[11px] font-bold px-2.5 py-1 rounded-full whitespace-nowrap"
      style={{ backgroundColor: bg, color: fg }}
    >
      ⭐ {importance}
    </span>
  );
}

/** Thumbnail-overlay badge for eloquence-judged posts (backend/core/
 * eloquence.py) — renders nothing for unscored posts or ones judged not
 * eloquent (see /eloquent, which already filters to is_eloquent===1, so
 * only the tutorial/speech distinction needs surfacing here). */
export function EloquentBadge({ isTutorial }: { isTutorial: 0 | 1 | null }) {
  const label = isTutorial ? "🎙️ Tutorial" : "🎙️ Speech";
  return (
    <span
      title={isTutorial ? "Eloquent tutorial-style delivery" : "Eloquent speech/commentary-style delivery"}
      className="shrink-0 font-display text-[11px] font-bold px-2.5 py-1 rounded-full whitespace-nowrap bg-lavender-soft text-lavender-ink"
    >
      {label}
    </span>
  );
}

export function TagChips({ tags, limit }: { tags: string[]; limit?: number }) {
  if (!tags || tags.length === 0) return null;
  const uniqueTags = Array.from(new Set(tags));
  const shown = limit ? uniqueTags.slice(0, limit) : uniqueTags;
  const remaining = limit && uniqueTags.length > limit ? uniqueTags.length - limit : 0;
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
