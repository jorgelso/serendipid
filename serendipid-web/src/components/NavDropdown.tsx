"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

export default function NavDropdown({
  label,
  active,
  links,
}: {
  label: string;
  active: boolean;
  links: { href: string; label: string; isActive: boolean }[];
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function handlePointerDown(e: PointerEvent) {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [open]);

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className={`flex items-center gap-1 px-4 py-2 rounded-full text-sm font-bold transition-colors ${
          active ? "bg-ink text-bg" : "text-ink-muted hover:bg-surface-2 hover:text-ink"
        }`}
      >
        {label}
        <span aria-hidden className={`text-[10px] transition-transform ${open ? "rotate-180" : ""}`}>
          &#9662;
        </span>
      </button>
      {open && (
        <div className="absolute left-0 top-full mt-2 min-w-40 rounded-2xl border border-line bg-surface p-1.5 shadow-lg">
          {links.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              onClick={() => setOpen(false)}
              className={`block rounded-xl px-3 py-2 text-sm font-bold transition-colors ${
                link.isActive ? "bg-ink text-bg" : "text-ink-muted hover:bg-surface-2 hover:text-ink"
              }`}
            >
              {link.label}
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
