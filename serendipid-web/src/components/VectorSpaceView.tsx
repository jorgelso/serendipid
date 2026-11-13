"use client";

import { useMemo, useRef, useState } from "react";
import dynamic from "next/dynamic";
import type { ClientPost, Theme, VectorSpacePoint } from "@/types/domain";
import { useStudyGuideSelection } from "@/lib/useStudyGuideSelection";
import type { VectorSpaceSceneHandle } from "./VectorSpaceScene";
import GenerateStudyGuideButton from "./GenerateStudyGuideButton";
import VectorSpaceLegend, { UNCLUSTERED_SELECTION } from "./VectorSpaceLegend";
import VectorSpaceSearch from "./VectorSpaceSearch";
import StudyGuideToolbar from "./StudyGuideToolbar";
import PostModal from "./PostModal";

// react-three-fiber's <Canvas> needs a real WebGL context, so it can't be
// part of the server-rendered HTML — loaded client-only, same reasoning as
// any browser-API-only widget in the App Router.
const VectorSpaceScene = dynamic(() => import("./VectorSpaceScene"), {
  ssr: false,
  loading: () => (
    <div className="flex h-full w-full items-center justify-center text-ink-muted text-sm">
      Loading scene…
    </div>
  ),
});

interface VectorSpaceViewProps {
  points: VectorSpacePoint[];
  themes: Theme[];
  unclusteredCount: number;
}

export default function VectorSpaceView({ points, themes, unclusteredCount }: VectorSpaceViewProps) {
  // Theme selection (legend) and text search are two ways of picking the
  // same thing — a set of shortcodes to light up — and are mutually
  // exclusive: starting one clears the other so there's never an ambiguous
  // "both active" state.
  const [legendSelection, setLegendSelection] = useState<string | null>(null);
  const [searchShortcodes, setSearchShortcodes] = useState<Set<string> | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  // Clicking a point isolates it (dims every other point, same mechanism as
  // the legend/search highlight) so it stays visually findable even after
  // FocusOrbit re-centers the camera on it and the cursor is no longer over
  // it. Clicking the same point again clears it — same toggle as the legend.
  const [pointSelection, setPointSelection] = useState<string | null>(null);
  const [selectedPost, setSelectedPost] = useState<ClientPost | null>(null);
  const [loadingShortcode, setLoadingShortcode] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  // Owned here (not inside VectorSpaceLegend) so VectorSpaceScene can also
  // read it: collapsing the legend to the top 8 clusters grays out every
  // point past that rank too, not just the legend rows.
  const [legendExpanded, setLegendExpanded] = useState(true);
  const sceneRef = useRef<VectorSpaceSceneHandle>(null);

  // Study-guide multi-select: same shared hook/toolbar as the home feed and
  // search results (see useStudyGuideSelection.ts), just repurposed here so
  // clicking a point toggles it into the selection instead of opening the
  // post modal — see handleSelect below. sg.selecting takes over
  // highlightedShortcodes entirely while active (mutually exclusive with
  // legend/search/single-point selection, same as those three already are
  // with each other).
  const sg = useStudyGuideSelection("3D space selection");

  const legendHighlight = useMemo(() => {
    if (legendSelection === null) return null;
    const matches = new Set<string>();
    for (const point of points) {
      const key = point.themeId ?? UNCLUSTERED_SELECTION;
      if (key === legendSelection) matches.add(point.shortcode);
    }
    return matches;
  }, [points, legendSelection]);

  const pointHighlight = useMemo(
    () => (pointSelection ? new Set([pointSelection]) : null),
    [pointSelection]
  );

  // The active legend theme's micro-clusters, for GenerateStudyGuideButton's
  // chunk-packing hint (see VectorSpaceLegend's activeGroups doc comment) —
  // null for the "Unclustered" bucket (UNCLUSTERED_SELECTION isn't a real
  // theme id, has no micro-cluster structure) or when nothing is selected.
  const legendGroups = useMemo(() => {
    if (legendSelection === null) return null;
    const theme = themes.find((t) => t.id === legendSelection);
    return theme ? theme.microClusters.map((mc) => mc.postShortcodes) : null;
  }, [themes, legendSelection]);

  const highlightedShortcodes = sg.selecting
    ? (sg.selected.size > 0 ? sg.selected : null)
    : (searchShortcodes ?? legendHighlight ?? pointHighlight);

  function handleSelectTheme(key: string | null) {
    setSearchShortcodes(null);
    setPointSelection(null);
    setLegendSelection(key);
  }

  function handleSearchResults(shortcodes: Set<string> | null, query: string) {
    setLegendSelection(null);
    setPointSelection(null);
    setSearchShortcodes(shortcodes);
    setSearchQuery(query);
  }

  function handleToggleSelectMode() {
    if (sg.selecting) {
      sg.stopSelecting();
      return;
    }
    setLegendSelection(null);
    setSearchShortcodes(null);
    setPointSelection(null);
    sg.setSelecting(true);
  }

  async function handleSelect(shortcode: string) {
    if (sg.selecting) {
      sg.toggleSelect(shortcode);
      return;
    }

    setLegendSelection(null);
    setSearchShortcodes(null);
    setPointSelection((prev) => (prev === shortcode ? null : shortcode));

    setLoadingShortcode(shortcode);
    setLoadError(null);
    try {
      const res = await fetch(`/api/posts?shortcodes=${encodeURIComponent(shortcode)}`);
      const data: { posts: ClientPost[] } = await res.json();
      const post = data.posts[0];
      if (post) {
        setSelectedPost(post);
      } else {
        setLoadError("Couldn't load that reel.");
      }
    } catch {
      setLoadError("Couldn't load that reel.");
    } finally {
      setLoadingShortcode(null);
    }
  }

  return (
    <div className="fixed inset-0 z-0">
      <VectorSpaceScene
        ref={sceneRef}
        points={points}
        highlightedShortcodes={highlightedShortcodes}
        onSelect={handleSelect}
        legendExpanded={legendExpanded}
      />

      <div className="pointer-events-none absolute inset-0 flex items-start justify-between px-4 pb-4 pt-20">
        <div className="pointer-events-auto flex flex-wrap items-center gap-2">
          <div className="rounded-2xl border border-line bg-surface/90 px-4 py-2.5 text-xs text-ink-muted shadow-[0_10px_24px_-16px_rgba(0,0,0,0.35)] backdrop-blur-md">
            <span className="font-display font-bold text-ink">{points.length} reels</span> · drag to
            rotate · scroll to zoom
          </div>
          <button
            type="button"
            onClick={() => {
              sceneRef.current?.resetCamera();
              setLegendSelection(null);
              setSearchShortcodes(null);
              setSearchQuery("");
              setPointSelection(null);
              sg.stopSelecting();
            }}
            title="Reset view"
            className="rounded-2xl border border-line bg-surface/90 px-3 py-2.5 text-xs font-bold text-ink-muted shadow-[0_10px_24px_-16px_rgba(0,0,0,0.35)] backdrop-blur-md transition-colors hover:text-ink"
          >
            ↺ Reset view
          </button>
          {!sg.selecting && <VectorSpaceSearch onResults={handleSearchResults} />}
          {!sg.selecting && searchShortcodes && searchShortcodes.size > 0 && (
            <GenerateStudyGuideButton
              shortcodes={Array.from(searchShortcodes)}
              sourceLabel={`Search: "${searchQuery}"`}
              className="shrink-0 rounded-2xl border border-line bg-surface/90 px-3 py-2.5 text-xs font-bold text-ink shadow-[0_10px_24px_-16px_rgba(0,0,0,0.35)] backdrop-blur-md transition-colors hover:bg-surface-2 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
            />
          )}
          <div className="[&>div]:mb-0 rounded-2xl border border-line bg-surface/90 px-3 py-2 shadow-[0_10px_24px_-16px_rgba(0,0,0,0.35)] backdrop-blur-md">
            <StudyGuideToolbar
              selecting={sg.selecting}
              selectedCount={sg.selected.size}
              generateState={sg.generateState}
              message={sg.message}
              onToggleSelecting={handleToggleSelectMode}
              onGenerate={sg.generate}
            />
          </div>
          {sg.selecting && sg.selected.size === 0 && (
            <div className="rounded-2xl border border-line bg-surface/90 px-3 py-2.5 text-xs text-ink-muted shadow-[0_10px_24px_-16px_rgba(0,0,0,0.35)] backdrop-blur-md">
              Click points below to select them
            </div>
          )}
        </div>
        {!sg.selecting && (
          <VectorSpaceLegend
            themes={themes}
            unclusteredCount={unclusteredCount}
            activeSelection={legendSelection}
            onSelect={handleSelectTheme}
            expanded={legendExpanded}
            onExpandedChange={setLegendExpanded}
            activeShortcodes={legendHighlight ? Array.from(legendHighlight) : null}
            activeGroups={legendGroups}
          />
        )}
      </div>

      {loadingShortcode && (
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
          <div className="pointer-events-auto rounded-full bg-ink/80 px-4 py-2 text-sm font-bold text-bg backdrop-blur-sm">
            Loading reel…
          </div>
        </div>
      )}

      {loadError && (
        <div className="pointer-events-none absolute inset-x-0 bottom-4 flex justify-center">
          <div className="pointer-events-auto rounded-full bg-danger-soft px-4 py-2 text-sm font-bold text-coral-ink">
            {loadError}
          </div>
        </div>
      )}

      {selectedPost && <PostModal post={selectedPost} onClose={() => setSelectedPost(null)} />}
    </div>
  );
}
