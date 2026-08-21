import type { Metadata } from "next";
import { Anton, Fredoka, Kalam, Nunito } from "next/font/google";
import "./globals.css";
import NavBar from "@/components/NavBar";

const fredoka = Fredoka({
  variable: "--font-fredoka",
  subsets: ["latin"],
  weight: ["500", "600", "700"],
});

const nunito = Nunito({
  variable: "--font-nunito",
  subsets: ["latin"],
});

// Handwritten/marker face, scoped to the study guides "corkboard" collage
// (src/app/study-guides) via the font-hand utility (globals.css) — not used
// anywhere else in the app, which keeps its normal Fredoka/Nunito voice.
const kalam = Kalam({
  variable: "--font-kalam",
  subsets: ["latin"],
  weight: ["400", "700"],
});

// Bold condensed "magazine cutout" headline face — scoped to the study
// guides collage the same way kalam is, for the mag/foil PaperTicket
// variants (src/components/PaperTicket.tsx).
const anton = Anton({
  variable: "--font-anton",
  subsets: ["latin"],
  weight: ["400"],
});

export const metadata: Metadata = {
  title: "Serendipid — your saved reels, worth scrolling again",
  description: "Everything you've saved on Instagram, turned into a feed worth scrolling.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${fredoka.variable} ${nunito.variable} ${kalam.variable} ${anton.variable} h-full antialiased`}>
      <body className="min-h-full flex flex-col bg-bg text-ink">
        <NavBar />
        <main className="flex-1">{children}</main>
      </body>
    </html>
  );
}
