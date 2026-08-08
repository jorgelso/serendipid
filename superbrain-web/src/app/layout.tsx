import type { Metadata } from "next";
import { Fraunces, IBM_Plex_Mono, Work_Sans } from "next/font/google";
import Link from "next/link";
import "./globals.css";

const fraunces = Fraunces({
  variable: "--font-fraunces",
  subsets: ["latin"],
  axes: ["opsz", "SOFT", "WONK"],
});

const workSans = Work_Sans({
  variable: "--font-work-sans",
  subsets: ["latin"],
});

const ibmPlexMono = IBM_Plex_Mono({
  variable: "--font-ibm-plex-mono",
  subsets: ["latin"],
  weight: ["400", "500"],
});

export const metadata: Metadata = {
  title: "SuperBrain — your saved reels, catalogued",
  description: "A field guide to the reels you've saved, grouped by what they're actually about.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${fraunces.variable} ${workSans.variable} ${ibmPlexMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col bg-paper text-ink">
        <header className="border-b border-line">
          <div className="mx-auto max-w-4xl px-6 py-5 flex items-baseline justify-between gap-4">
            <Link href="/" className="group flex items-baseline gap-2">
              <span className="font-display text-xl tracking-tight">SuperBrain</span>
              <span className="font-label text-[11px] uppercase tracking-widest text-ink-muted group-hover:text-moss transition-colors">
                field guide
              </span>
            </Link>
          </div>
        </header>
        <main className="flex-1">{children}</main>
        <footer className="border-t border-line">
          <div className="mx-auto max-w-4xl px-6 py-6 text-xs text-ink-muted font-label">
            local &amp; private — nothing here leaves your machine
          </div>
        </footer>
      </body>
    </html>
  );
}
