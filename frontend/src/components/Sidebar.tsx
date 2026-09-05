"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { LayoutDashboard, ScanLine, ListChecks, Workflow, BookOpenCheck } from "lucide-react";

const NAV = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/ingestion", label: "Ingestion", icon: ScanLine },
  { href: "/reconciliation", label: "Reconciliation", icon: ListChecks },
  { href: "/architecture", label: "Architecture", icon: Workflow },
];

export default function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="hidden md:flex w-60 shrink-0 flex-col border-r border-ink-line bg-ink-raised/40">
      <div className="h-16 flex items-center gap-2.5 px-6 border-b border-ink-line">
        <div className="w-7 h-7 rounded-[6px] bg-gold flex items-center justify-center">
          <BookOpenCheck size={16} className="text-ink" strokeWidth={2.5} />
        </div>
        <span className="font-display font-semibold text-[15px] tracking-tight text-paper">
          AutoReconcile
        </span>
      </div>

      <nav className="flex-1 px-3 py-5 space-y-0.5">
        {NAV.map(({ href, label, icon: Icon }) => {
          const active = pathname === href;
          return (
            <Link
              key={href}
              href={href}
              className={`flex items-center gap-3 px-3 py-2.5 rounded-md text-[13.5px] transition-colors ${
                active
                  ? "bg-gold/10 text-gold font-medium"
                  : "text-paper-dim hover:text-paper hover:bg-white/[0.03]"
              }`}
            >
              <Icon size={16} strokeWidth={2} />
              {label}
            </Link>
          );
        })}
      </nav>

      <div className="p-4 mx-3 mb-4 rounded-lg border border-ink-line bg-ink/60">
        <p className="text-[11px] text-paper-dim leading-relaxed">
          Track 4 — AI Finance Controller
          <br />
          Razorpay AI Builder Internship 2026
        </p>
      </div>
    </aside>
  );
}
