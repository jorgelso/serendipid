import WashiTape from "./WashiTape";
import CutoutChip from "./CutoutChip";
import { seededRotation } from "@/lib/collage";

const DEFAULT_WORDS = ["Study", "guides"];

export default function ScrapbookMasthead({
  subtitle,
  words = DEFAULT_WORDS,
}: {
  subtitle: string;
  words?: string[];
}) {
  return (
    <div className="relative flex flex-wrap items-start gap-1 pb-2">
      <div className="relative z-20 flex flex-wrap gap-1">
        {words.map((w, i) => (
          <CutoutChip key={w} seed={i + 11} size="lg">
            {w}
          </CutoutChip>
        ))}
      </div>

      <div
        style={{ transform: `rotate(${seededRotation(3, 4)}deg)`, marginTop: "10px", marginLeft: "-8px" }}
        className="bg-surface border-line relative z-10 max-w-sm rounded-[2px] border px-4 py-3 shadow-[0_8px_16px_-8px_rgba(0,0,0,0.4)]"
      >
        <WashiTape color="yellow" rotation={-7} />
        <p className="font-hand text-ink text-base leading-snug">{subtitle}</p>
      </div>
    </div>
  );
}
