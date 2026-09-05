"use client";

import { useEffect, useState } from "react";
import { Terminal } from "lucide-react";
import { api } from "@/lib/api";
import ApiLogsModal from "./ApiLogsModal";

export default function TopBar() {
  const [online, setOnline] = useState<boolean | null>(null);
  const [mock, setMock] = useState<boolean>(true);
  const [logsOpen, setLogsOpen] = useState(false);

  useEffect(() => {
    let mounted = true;
    api
      .health()
      .then((h) => {
        if (!mounted) return;
        setOnline(true);
        setMock(h.mock_mode);
      })
      .catch(() => mounted && setOnline(false));
    return () => {
      mounted = false;
    };
  }, []);

  return (
    <>
      <header className="h-16 border-b border-ink-line flex items-center justify-between px-6 md:px-10 shrink-0">
        <div>
          <h1 className="font-display font-semibold text-[15px] text-paper">
            AutoReconcile AI
          </h1>
          <p className="text-[12px] text-paper-dim -mt-0.5">
            Autonomous invoice-to-payout reconciliation
          </p>
        </div>

        <div className="flex items-center gap-4">
          <button
            onClick={() => setLogsOpen(true)}
            className="flex items-center gap-1.5 text-[12.5px] text-paper-dim hover:text-paper border border-ink-line hover:border-gold/40 rounded-md px-3 py-1.5 transition-colors"
          >
            <Terminal size={13.5} />
            API logs
          </button>

          <div className="flex items-center gap-2 text-[12.5px]">
            <span
              className={`w-2 h-2 rounded-full ${
                online === null ? "bg-paper-dim" : online ? "bg-good" : "bg-bad"
              }`}
            />
            <span className="text-paper-dim">
              {online === null ? "Connecting…" : online ? (mock ? "Backend live · Mock payouts" : "Backend live") : "Backend offline"}
            </span>
          </div>
        </div>
      </header>
      <ApiLogsModal open={logsOpen} onClose={() => setLogsOpen(false)} />
    </>
  );
}
