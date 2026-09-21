"use client";

import { useEffect, useState } from "react";
import { X, RefreshCw } from "lucide-react";
import { api, AuditLogEntry } from "@/lib/api";

export default function ApiLogsModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [logs, setLogs] = useState<AuditLogEntry[]>([]);
  const [loading, setLoading] = useState(false);

  const load = () => {
    setLoading(true);
    api
      .auditLog()
      .then(setLogs)
      .catch(() => setLogs([]))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    if (!open) return;
    let active = true;
    api
      .auditLog()
      .then((data) => active && setLogs(data))
      .catch(() => active && setLogs([]));
    return () => {
      active = false;
    };
  }, [open]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-20 px-4">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div className="relative w-full max-w-2xl max-h-[70vh] flex flex-col bg-ink-raised border border-ink-line rounded-xl shadow-2xl">
        <div className="flex items-center justify-between px-5 py-4 border-b border-ink-line">
          <div>
            <h3 className="font-display font-semibold text-[14px] text-paper">Razorpay Payouts API — raw log</h3>
            <p className="text-[11.5px] text-paper-dim">payout_audit_log.jsonl · append-only, hash-chained, per payout decision</p>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={load} className="p-1.5 rounded-md text-paper-dim hover:text-gold hover:bg-white/5">
              <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
            </button>
            <button onClick={onClose} className="p-1.5 rounded-md text-paper-dim hover:text-paper hover:bg-white/5">
              <X size={16} />
            </button>
          </div>
        </div>
        <div className="flex-1 overflow-y-auto px-5 py-4 font-ledger text-[11.5px] leading-relaxed">
          {logs.length === 0 ? (
            <p className="text-paper-dim">
              No payout attempts logged yet. Run reconciliation or approve an exception to populate this log.
            </p>
          ) : (
            <div className="space-y-3">
              {logs.map((entry, i) => (
                <pre
                  key={i}
                  className="whitespace-pre-wrap break-all bg-ink border border-ink-line rounded-md p-3 text-paper-dim"
                >
                  {JSON.stringify(entry, null, 2)}
                </pre>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
