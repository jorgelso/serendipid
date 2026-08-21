"use client";

import type { ClientPost } from "@/types/domain";
import { useStudyGuideSelection } from "@/lib/useStudyGuideSelection";
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
  const sg = useStudyGuideSelection(`Search: "${query}"`);

  return (
    <div>
      <StudyGuideToolbar
        selecting={sg.selecting}
        selectedCount={sg.selected.size}
        generateState={sg.generateState}
        message={sg.message}
        onToggleSelecting={() => (sg.selecting ? sg.stopSelecting() : sg.setSelecting(true))}
        onGenerate={sg.generate}
      />
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
