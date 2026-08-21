import WashiTape from "./WashiTape";
import { seededRotation, seededTapeColor, type TapeColor } from "@/lib/collage";

const WORDS = ["Study", "guides"];

// Each word of the title is its own rotated die-cut chip (alternating
// accent color) instead of one flat <h1> — a cheap, safe stand-in for the
// "cut-out magazine lettering" look in the reference boards, built from
// this app's existing token palette rather than sourced imagery.
function TitleWord({ word, seed }: { word: string; seed: number }) {
  const color: TapeColor = seededTapeColor(seed);
  return (
    <span
      style={{
        transform: `rotate(${seededRotation(seed, 4)}deg)`,
        backgroundColor: `var(--color-${color}-soft)`,
        color: `var(--color-${color}-ink)`,
      }}
      className="font-display inline-block rounded-[4px] px-3 py-1 text-4xl font-bold shadow-[0_4px_8px_rgba(0,0,0,0.3)] sm:text-5xl"
    >
      {word}
    </span>
  );
}

export default function ScrapbookMasthead({ subtitle }: { subtitle: string }) {
  return (
    <div className="relative flex flex-wrap items-start gap-4 pb-4">
      <div className="flex flex-wrap gap-3">
        {WORDS.map((w, i) => (
          <TitleWord key={w} word={w} seed={i + 11} />
        ))}
      </div>

      <div
        style={{ transform: `rotate(${seededRotation(3, 3)}deg)` }}
        className="bg-surface border-line relative mt-1 max-w-sm rounded-[2px] border px-4 py-3 shadow-[0_8px_16px_-8px_rgba(0,0,0,0.4)]"
      >
        <WashiTape color="yellow" rotation={-7} />
        <p className="font-hand text-ink text-base leading-snug">{subtitle}</p>
      </div>
    </div>
  );
}
