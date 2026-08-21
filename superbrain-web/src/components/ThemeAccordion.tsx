import Link from "next/link";
import type { Theme } from "@/types/domain";
import { TagChips } from "./Chips";
import LazyPostList from "./LazyPostList";
import GenerateStudyGuideButton from "./GenerateStudyGuideButton";

export default function ThemeAccordion({ theme }: { theme: Theme }) {
  const groups = theme.microClusters.map((mc) => mc.postShortcodes);
  const shortcodes = groups.flat();
  return (
    <details className="group rounded-2xl border border-line bg-surface" open={theme.postCount >= 6}>
      <summary className="cursor-pointer select-none list-none flex items-center gap-3 px-5 py-4">
        <span aria-hidden className="text-coral-ink transition-transform group-open:rotate-90">
          &#9656;
        </span>
        <span className="font-display font-semibold text-xl">{theme.label}</span>
        <TagChips tags={theme.subLabels} />
        <span className="ml-auto text-[11px] font-bold uppercase tracking-wide text-ink-muted">
          {theme.postCount} saved
        </span>
      </summary>
      <div className="border-t border-line px-5 py-4 space-y-1">
        {theme.microClusters.map((mc) => (
          <div key={mc.id} className="border-l-2 border-coral-soft pl-3">
            <LazyPostList label={mc.label} subLabels={mc.subLabels} shortcodes={mc.postShortcodes} />
          </div>
        ))}
        <div className="mt-2 flex items-center gap-3">
          <Link
            href={`/ideas?themeId=${encodeURIComponent(theme.id)}`}
            className="text-xs text-ink-muted hover:text-coral-ink transition-colors"
          >
            View recurring ideas in this theme →
          </Link>
          <GenerateStudyGuideButton shortcodes={shortcodes} groups={groups} sourceLabel={`Theme: "${theme.label}"`} />
        </div>
      </div>
    </details>
  );
}
