import type { Idea } from "@/types/domain";
import LazyPostList from "./LazyPostList";
import GenerateStudyGuideButton from "./GenerateStudyGuideButton";

// One recurring-tag row on /ideas: expand (LazyPostList, same lazy-load
// pattern ThemeAccordion uses) to see the source posts, or generate a study
// guide from just this idea's sources directly — no multi-select needed
// here since the shortcode set is already exactly this idea's sources.
export default function IdeaRow({ idea }: { idea: Idea }) {
  return (
    <div className="rounded-2xl border border-line bg-surface px-4">
      <div className="flex items-center gap-2">
        <div className="flex-1 min-w-0">
          <LazyPostList label={idea.label} shortcodes={idea.shortcodes} />
        </div>
        <GenerateStudyGuideButton shortcodes={idea.shortcodes} sourceLabel={`Idea: "${idea.label}"`} />
      </div>
    </div>
  );
}
