"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import RefreshButton from "./RefreshButton";

const LINKS = [
  { href: "/", label: "Home" },
  { href: "/browse", label: "Browse" },
  { href: "/search", label: "Search" },
  { href: "/chat", label: "Chat" },
  { href: "/insights", label: "Insights" },
  { href: "/space", label: "Space" },
];

export default function NavBar() {
  const pathname = usePathname();

  return (
    <header className="sticky top-0 z-30 border-b border-line bg-bg/90 backdrop-blur-md">
      <div className="mx-auto max-w-6xl px-5 py-3.5 flex items-center gap-6">
        <Link href="/" className="flex items-center gap-2 shrink-0">
          <span className="text-2xl">🧠</span>
          <span className="font-display font-bold text-xl tracking-tight">SuperBrain</span>
        </Link>
        <nav className="flex items-center gap-1">
          {LINKS.map((link) => {
            const active = link.href === "/" ? pathname === "/" : pathname.startsWith(link.href);
            return (
              <Link
                key={link.href}
                href={link.href}
                className={`px-4 py-2 rounded-full text-sm font-bold transition-colors ${
                  active
                    ? "bg-ink text-bg"
                    : "text-ink-muted hover:bg-surface-2 hover:text-ink"
                }`}
              >
                {link.label}
              </Link>
            );
          })}
        </nav>
        <div className="ml-auto">
          <RefreshButton />
        </div>
      </div>
    </header>
  );
}
