"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import type { Board } from "@/types/domain";
import { refreshBoards } from "@/lib/useBoards";
import { seededRotation, seededTapeColor, seededOffset, seededZIndex, hashSeed } from "@/lib/collage";
import ConfirmDialog from "./ConfirmDialog";
import WashiTape from "./WashiTape";
import PushPin from "./PushPin";
import PolaroidThumb from "./PolaroidThumb";
import CutoutChip from "./CutoutChip";
import TypewriterTag from "./TypewriterTag";
import StickerLabel from "./StickerLabel";

// Fan positions for extra post thumbnails peeking out from behind a board's
// main photo — same idea as StudyGuideCorkboard's fanOffset, deterministic
// per board+index so the pile doesn't jitter between renders.
function fanOffset(seed: number, i: number) {
  const s = seed + i * 13;
  const side = i % 2 === 0 ? 1 : -1;
  return {
    top: 26 + i * 20 + seededOffset(s, 8),
    left: side * (14 + i * 16) + seededOffset(s + 1, 8),
    rotate: seededRotation(s + 2, 16),
    z: seededZIndex(s + 3, 1, 4),
  };
}

// A board rendered as a little pile of pinned-up reel polaroids, not a UI
// card — matching how StudyGuideCorkboard renders a study guide collection.
// The board's own post thumbnails (proxied via /api/thumbnail/[shortcode],
// the same route the board detail grid already uses) stand in for a photo
// of what's actually inside, fanned out behind a main photo with a pushpin
// and washi tape holding it down, a magazine-cutout title pasted across its
// corner, and a typewritten post-count tag overlapping its bottom edge.
export default function BoardCard({ board, index }: { board: Board; index: number }) {
  const router = useRouter();
  const [deleting, setDeleting] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleDelete() {
    setDeleting(true);
    setError(null);
    try {
      const res = await fetch(`/api/boards/${board.id}`, { method: "DELETE" });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? "Couldn't delete this board.");
      await refreshBoards();
      router.refresh();
    } catch (err) {
      setDeleting(false);
      setConfirming(false);
      setError(err instanceof Error ? err.message : "Couldn't delete this board.");
    }
  }

  const seed = hashSeed(board.id);
  const tapeColor = seededTapeColor(seed + 3);
  const mainShortcode = board.post_ids[0];
  const fanned = board.post_ids.slice(1, 4);
  const overflowCount = Math.max(0, board.post_ids.length - 1 - fanned.length);
  // Staggered vertical + horizontal offset by index parity — breaks the
  // columns layout's tidy top-aligned rhythm so piles read as a scattered
  // spread, and negative bottom margin lets consecutive piles in a column
  // crowd/overlap rather than sit in clean rows (mirrors StudyGuideCorkboard).
  const stagger = ["4px", "58px", "26px", "42px"][index % 4];

  return (
    <div
      style={{ marginTop: stagger, marginLeft: index % 2 === 0 ? "0px" : "14px", zIndex: seededZIndex(seed, 1, 5) }}
      className="group relative mb-[-8px] w-fit break-inside-avoid pt-9 pr-7 pb-11 pl-2"
    >
      {/* Fanned-out post thumbnails, tucked behind the main photo */}
      {fanned.map((shortcode, i) => {
        const f = fanOffset(seed, i);
        return (
          <Link
            key={shortcode}
            href={`/boards/${board.id}`}
            className="absolute"
            style={{ top: `${f.top}px`, left: `${f.left}px`, zIndex: f.z }}
          >
            <PolaroidThumb src={`/api/thumbnail/${shortcode}`} alt="" seed={hashSeed(shortcode)} rotation={f.rotate} size="sm" />
          </Link>
        );
      })}

      {/* Main photo — the only normal-flow element, so it sets the pile's footprint */}
      <Link href={`/boards/${board.id}`} className="relative inline-block" style={{ zIndex: 10 }}>
        {mainShortcode ? (
          <PolaroidThumb src={`/api/thumbnail/${mainShortcode}`} alt={board.name} seed={seed} size="lg" />
        ) : (
          <div
            style={{ transform: `rotate(${seededRotation(seed, 5)}deg)` }}
            className="border-line bg-surface-2 font-hand text-ink-muted flex h-48 w-36 items-center justify-center rounded-sm border border-dashed text-center text-xs"
          >
            empty board
          </div>
        )}
        <PushPin color={`var(--color-${seededTapeColor(seed)})`} />
        <WashiTape color={tapeColor} rotation={seededRotation(seed + 5, 10)} />
      </Link>

      {/* Title — a magazine-cutout chip pasted across the photo's top-left corner */}
      <div
        className="absolute max-w-[82%]"
        style={{ top: `${-10 - seededOffset(seed + 5, 6)}px`, left: `${-6 + seededOffset(seed + 6, 10)}px`, zIndex: 20 }}
      >
        <CutoutChip seed={seed + 7} size="md" rotationRange={6} className="line-clamp-2">
          {`${board.icon ?? "🗂️"} ${board.name}`}
        </CutoutChip>
      </div>

      {/* Post count — a typewritten strip overlapping the photo's bottom edge.
          Anchored with `top` (not `bottom`) deliberately — an abspos box
          positioned only via `bottom`/`right` inside a `break-inside-avoid`
          CSS-columns item hits a real Chromium bug where its box gets
          fragmented across the column boundary, ballooning its
          getBoundingClientRect to the union of both columns. `top` avoids
          the auto-bottom resolution path that triggers it. */}
      <div
        className="absolute"
        style={{ top: `${246 + seededOffset(seed + 9, 10)}px`, left: `${6 + seededOffset(seed + 10, 12)}px`, zIndex: 20 }}
      >
        <TypewriterTag rotation={seededRotation(seed + 9, 6)}>
          {board.post_ids.length} post{board.post_ids.length === 1 ? "" : "s"}
        </TypewriterTag>
      </div>

      {board.subcollections.length > 0 && (
        <div className="absolute" style={{ top: "4px", right: "-14px", zIndex: 21 }}>
          <StickerLabel color={tapeColor} rotation={-3}>
            {board.subcollections.length} sub-board{board.subcollections.length === 1 ? "" : "s"}
          </StickerLabel>
        </div>
      )}

      {overflowCount > 0 && (
        <div className="absolute" style={{ top: `${246 + seededOffset(seed + 13, 8)}px`, right: "-8px", zIndex: 22 }}>
          <StickerLabel color={tapeColor} rotation={4}>
            +{overflowCount} more
          </StickerLabel>
        </div>
      )}

      <div className="absolute opacity-0 transition-opacity group-hover:opacity-100" style={{ top: "0px", right: "-2px", zIndex: 30 }}>
        <button
          type="button"
          onClick={() => setConfirming(true)}
          className="text-coral-ink text-xs font-bold hover:opacity-70 transition-opacity"
        >
          🗑
        </button>
      </div>

      {error && (
        <p className="text-danger font-hand absolute text-xs" style={{ top: "270px", left: "6px", zIndex: 20 }}>
          {error}
        </p>
      )}

      {confirming && (
        <ConfirmDialog
          title={`Delete "${board.name}"?`}
          message={`This deletes the board and all ${board.subcollections.length} sub-collection${board.subcollections.length === 1 ? "" : "s"} in it. Posts themselves aren't affected. Can't be undone.`}
          confirmLabel={deleting ? "Deleting…" : "Delete"}
          danger
          busy={deleting}
          onConfirm={handleDelete}
          onCancel={() => setConfirming(false)}
        />
      )}
    </div>
  );
}
