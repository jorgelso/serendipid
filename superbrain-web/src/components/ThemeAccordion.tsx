import type { Theme } from "@/types/domain";
import { TagChips } from "./Chips";
import LazyPostList from "./LazyPostList";

export default function ThemeAccordion({ theme }: { theme: Theme }) {
  return (
    <details className="group rounded-md border border-line bg-paper-raised" open={theme.postCount >= 6}>
      <summary className="cursor-pointer select-none list-none flex items-center gap-3 px-4 py-3">
        <span aria-hidden className="text-moss transition-transform group-open:rotate-90">
          &#9656;
        </span>
        <span className="font-display text-xl">{theme.label}</span>
        <TagChips tags={theme.subLabels} />
        <span className="ml-auto font-label text-[11px] uppercase tracking-wide text-ink-muted">
          {theme.postCount} saved
        </span>
      </summary>
      <div className="border-t border-line px-4 py-3 space-y-1">
        {theme.microClusters.map((mc) => (
          <div key={mc.id} className="border-l-2 border-moss-soft pl-3">
            <LazyPostList label={mc.label} subLabels={mc.subLabels} shortcodes={mc.postShortcodes} />
          </div>
        ))}
      </div>
    </details>
  );
}
