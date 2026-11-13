"use client";

import type { ClientPost } from "@/types/domain";
import { useStudyGuideSelection } from "@/lib/useStudyGuideSelection";
import GenerateStudyGuideButton from "./GenerateStudyGuideButton";
import MasonryGrid from "./MasonryGrid";
import PostCard from "./PostCard";
import StudyGuideToolbar from "./StudyGuideToolbar";

interface SearchResultsWithStudyGuideProps {
  results: (ClientPost & { similarity?: number })[];
  query: string;
}

// Same selection -> study-guide pattern as HomeFeedWithStudyGuide, but over
// a fixed (non-paginated) search result set — /search always returns a
// single page of matches, so there's no "Load more" state to thread
// selection through here the way InfiniteFeed needs.
export default function SearchResultsWithStudyGuide({ results, query }: SearchResultsWithStudyGuideProps) {
  const sourceLabel = `Search: "${query}"`;
  const sg = useStudyGuideSelection(sourceLabel);

  return (
    <div>
      <div className="mb-4 flex items-center gap-2 flex-wrap">
        {!sg.selecting && (
          <GenerateStudyGuideButton
            shortcodes={results.map((post) => post.shortcode)}
            sourceLabel={sourceLabel}
            label={`Generate study guide from all ${results.length} results`}
            className="rounded-full bg-ink text-bg text-sm font-bold px-4 py-1.5 hover:opacity-85 transition-opacity disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
          />
        )}
        <StudyGuideToolbar
          selecting={sg.selecting}
          selectedCount={sg.selected.size}
          generateState={sg.generateState}
          message={sg.message}
          onToggleSelecting={() => (sg.selecting ? sg.stopSelecting() : sg.setSelecting(true))}
          onGenerate={sg.generate}
        />
      </div>
      <MasonryGrid>
        {results.map((post) => (
          <PostCard
            key={post.shortcode}
            post={post}
            selectable={sg.selecting}
            selected={sg.selected.has(post.shortcode)}
            onToggleSelect={() => sg.toggleSelect(post.shortcode)}
          />
        ))}
      </MasonryGrid>
    </div>
  );
}
