import type { ReactNode } from "react";

export type TicketKind = "mag" | "foil" | "hand" | "type" | "script" | "quote";
export type TicketStock = "strip" | "note" | "notebook";

const STOCK_SRC: Record<TicketStock, string> = {
  strip: "/collage/torn-strip.png",
  note: "/collage/torn-note.png",
  notebook: "/collage/notebook.png",
};

interface PaperTicketProps {
  kind: TicketKind;
  children: ReactNode;
  left: number;
  top: number;
  width: number;
  /** Required for "mag"/"foil" (the paper is mask-clipped to an exact box);
   *  ignored for "hand"/"type"/"script" (the stock photo sets its own height). */
  height?: number;
  rotation?: number;
  z?: number;
  fontSize: number;
  /** Ink color — ignored for "foil", which always uses its metallic gradient. */
  color?: string;
  /** Flat "ink" color the paper itself is mask-clipped to, for "mag" only ("foil" is always near-black). */
  maskColor?: string;
  stock?: TicketStock;
  className?: string;
}

// Text treated as a cut physical scrap, not a UI badge — every variant is
// backed by a real photographed torn-paper stock (STOCK_SRC), never a flat
// CSS rectangle:
//  - "hand"/"type"/"script"/"quote": the stock photo itself IS the chip (its
//    own torn silhouette + grain), with ink-colored text laid on top. "quote"
//    is real sentence-level content pulled from the guide's own markdown
//    (StudyGuideCorkboard's extractQuotes) — set in the app's normal body
//    face, sentence case, so it reads as a printed clipping of an actual
//    line, the way a real collage's found-text cards do.
//  - "mag": a flat ink color mask-clipped to the stock photo's torn alpha
//    shape, with the same photo laid back over it at low opacity/multiply
//    so the paper's own grain still shows through the color.
//  - "foil": the same masked-black card as "mag", but the label text itself
//    is filled with a metallic gradient instead of a flat ink color — the
//    "PUNK ROCK" chrome-cutout-letters treatment.
export default function PaperTicket({
  kind,
  children,
  left,
  top,
  width,
  height,
  rotation = 0,
  z = 1,
  fontSize,
  color = "#221a12",
  maskColor = "#14100b",
  stock = "strip",
  className = "",
}: PaperTicketProps) {
  const src = STOCK_SRC[stock];

  if (kind === "hand" || kind === "type" || kind === "script" || kind === "quote") {
    const fontFamily =
      kind === "type" ? "ui-monospace, 'SFMono-Regular', Menlo, monospace" : kind === "quote" ? "var(--font-body)" : "var(--font-hand)";
    return (
      <div className={`absolute ${className}`} style={{ left, top, width, zIndex: z }}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={src}
          alt=""
          className="block w-full"
          style={{ transform: `rotate(${rotation}deg)`, filter: "drop-shadow(0 9px 16px rgba(0,0,0,.5))" }}
        />
        <span
          className="absolute inset-0 flex items-center justify-center px-[10%] py-[8%] text-center leading-tight font-bold"
          style={{
            fontFamily,
            fontSize,
            color,
            transform: `rotate(${rotation}deg)`,
            textTransform: kind === "type" ? "uppercase" : "none",
            letterSpacing: kind === "type" ? "0.02em" : undefined,
          }}
        >
          {children}
        </span>
      </div>
    );
  }

  // mag / foil
  const isFoil = kind === "foil";
  return (
    <div
      className={`absolute ${className}`}
      style={{ left, top, width, height, transform: `rotate(${rotation}deg)`, zIndex: z, filter: "drop-shadow(0 12px 20px rgba(0,0,0,.55))" }}
    >
      <div
        className="absolute inset-0"
        style={{
          backgroundColor: isFoil ? "#0d0a07" : maskColor,
          WebkitMaskImage: `url(${src})`,
          maskImage: `url(${src})`,
          WebkitMaskSize: "100% 100%",
          maskSize: "100% 100%",
          WebkitMaskRepeat: "no-repeat",
          maskRepeat: "no-repeat",
        }}
      />
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={src}
        alt=""
        className="absolute inset-0 h-full w-full"
        style={{ objectFit: "fill", mixBlendMode: isFoil ? "screen" : "multiply", opacity: isFoil ? 0.2 : 0.5 }}
      />
      <span
        className="absolute inset-0 flex items-center justify-center px-[10%] py-[8%] text-center leading-[0.85] font-bold uppercase"
        style={
          isFoil
            ? {
                fontFamily: "var(--font-mag)",
                fontSize,
                letterSpacing: "0.02em",
                background: "linear-gradient(180deg,#f6f6f6 0%,#aeaeae 30%,#f0f0f0 48%,#767676 66%,#e2e2e2 100%)",
                WebkitBackgroundClip: "text",
                backgroundClip: "text",
                color: "transparent",
                WebkitTextStroke: "1.4px #000",
              }
            : { fontFamily: "var(--font-mag)", fontSize, letterSpacing: "0.02em", color }
        }
      >
        {children}
      </span>
    </div>
  );
}
