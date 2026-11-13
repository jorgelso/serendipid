"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import NavDropdown from "./NavDropdown";
import SerendipidMark from "./icons/SerendipidMark";

const LINKS = [
  { href: "/eloquent", label: "Eloquent" },
  { href: "/chat", label: "Chat" },
  { href: "/space", label: "Space" },
  { href: "/boards", label: "Boards" },
  { href: "/study-guides", label: "Study guides" },
];

const GROUPS = [
  {
    label: "Discover",
    links: [
      { href: "/browse", label: "Browse" },
      { href: "/search", label: "Search" },
    ],
  },
  {
    label: "Analyze",
    links: [
      { href: "/insights", label: "Insights" },
      { href: "/ideas", label: "Ideas" },
      { href: "/versions", label: "Versions" },
    ],
  },
];

const ADMIN_LINK = { href: "/admin", label: "Admin" };

function isActive(pathname: string, href: string) {
  return href === "/" ? pathname === "/" : pathname.startsWith(href);
}

export default function NavBar() {
  const pathname = usePathname();
  const router = useRouter();
  if (pathname === "/login") return null;

  async function signOut() {
    await fetch("/api/auth/logout", { method: "POST" }).catch(() => {});
    router.replace("/login");
    router.refresh();
  }

  return (
    <header className="sticky top-0 z-30 border-b border-line bg-bg/90 backdrop-blur-md">
      <div className="mx-auto max-w-6xl px-5 py-3.5 flex items-center gap-6">
        <Link href="/" className="flex items-center gap-2 shrink-0">
          <SerendipidMark className="w-7 h-7" />
          <span className="font-display font-bold text-xl tracking-tight">Serendipid</span>
        </Link>
        <nav className="flex items-center gap-1">
          {GROUPS.map((group) => (
            <NavDropdown
              key={group.label}
              label={group.label}
              active={group.links.some((link) => isActive(pathname, link.href))}
              links={group.links.map((link) => ({ ...link, isActive: isActive(pathname, link.href) }))}
            />
          ))}
          {LINKS.map((link) => {
            const active = isActive(pathname, link.href);
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
        <div className="ml-auto flex items-center gap-2">
          <Link
            href={ADMIN_LINK.href}
            className={`px-4 py-2 rounded-full text-sm font-bold transition-colors ${
              isActive(pathname, ADMIN_LINK.href)
                ? "bg-ink text-bg"
                : "text-ink-muted hover:bg-surface-2 hover:text-ink"
            }`}
          >
            {ADMIN_LINK.label}
          </Link>
          <button
            type="button"
            onClick={signOut}
            className="px-4 py-2 rounded-full text-sm font-bold text-ink-muted hover:bg-surface-2 hover:text-ink transition-colors"
          >
            Sign out
          </button>
        </div>
      </div>
    </header>
  );
}
