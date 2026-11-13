import type { VectorSpacePoint } from "@/types/domain";
import { CategoryBadges } from "./Chips";

// Rendered inside the r3f <Canvas> via drei's <Html>, anchored next to the
// hovered point in 3D space — see VectorSpaceScene. Deliberately light: just
// enough to place the point (video/title/category), not the full post — the
// full detail only loads on click (see VectorSpaceView's onSelect).
export default function HoverPreviewCard({ point }: { point: VectorSpacePoint }) {
  return (
    <div className="pointer-events-none w-64 rounded-2xl bg-surface border border-line shadow-[0_16px_40px_-12px_rgba(0,0,0,0.7)] overflow-hidden">
      {/* Reels are vertical (9:16) — matching that instead of a square crop
          shows the actual frame rather than cutting off top/bottom. */}
      <div className="relative bg-ink aspect-[9/16]">
        {point.videoUrl ? (
          <video
            key={point.videoUrl}
            src={point.videoUrl}
            poster={point.thumbnail ?? undefined}
            autoPlay
            muted
            loop
            playsInline
            className="w-full h-full object-cover"
          />
        ) : point.thumbnail ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={point.thumbnail} alt="" className="w-full h-full object-cover" />
        ) : (
          <div className="w-full h-full flex items-center justify-center text-bg/40 text-4xl">🎬</div>
        )}
      </div>
      <div className="p-3">
        <p className="font-display font-semibold text-sm leading-snug line-clamp-2">
          {point.title || "Untitled reel"}
        </p>
        <div className="mt-1.5 flex flex-wrap gap-1">
          <CategoryBadges category={point.category} />
        </div>
      </div>
    </div>
  );
}
