import { SuperBrainApiError } from "@/lib/apiClient";
import { getThemes, getVectorSpace } from "@/lib/cache";
import type { Theme, VectorSpacePoint } from "@/types/domain";
import VectorSpaceView from "@/components/VectorSpaceView";

const MIN_POINTS = 4;

interface SpaceData {
  points: VectorSpacePoint[];
  themes: Theme[];
  unclusteredCount: number;
}

async function loadSpaceData(): Promise<SpaceData> {
  const [points, { themes, unclusteredShortcodes }] = await Promise.all([getVectorSpace(), getThemes()]);
  return { points, themes, unclusteredCount: unclusteredShortcodes.length };
}

export default async function SpacePage() {
  let data: SpaceData | null = null;
  let errorMessage: string | null = null;

  try {
    data = await loadSpaceData();
  } catch (err) {
    errorMessage =
      err instanceof SuperBrainApiError ? err.message : "Something went wrong loading the vector space.";
  }

  if (errorMessage) {
    return (
      <div className="mx-auto max-w-2xl px-5 py-8">
        <div className="rounded-2xl border border-danger/30 bg-danger-soft px-4 py-3 text-sm text-coral-ink">
          {errorMessage}
        </div>
      </div>
    );
  }

  if (!data || data.points.length < MIN_POINTS) {
    return (
      <div className="mx-auto max-w-2xl px-5 py-8">
        <h1 className="font-display font-semibold text-3xl">Space</h1>
        <p className="mt-3 text-ink-muted text-sm">
          Analyze at least a few more reels to see them laid out in 3D — the vector space needs a
          handful of embedded posts before the layout means anything.
        </p>
      </div>
    );
  }

  return (
    <VectorSpaceView points={data.points} themes={data.themes} unclusteredCount={data.unclusteredCount} />
  );
}
