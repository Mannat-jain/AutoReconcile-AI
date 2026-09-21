"use client";

import React, { useEffect, useState } from "react";
import { ChevronDown, ChevronUp, Zap, AlertTriangle, RefreshCw } from "lucide-react";
import { api, ReconciliationResult, formatINR } from "@/lib/api";
import StatusPill from "@/components/StatusPill";

// Mirrors CRITICAL_ANOMALY_CODES in backend/main.py: approving these needs a written justification.
const CRITICAL_ANOMALIES = new Set(["BANK_DETAILS_MISMATCH", "DUPLICATE_INVOICE_SUBMISSION", "DUPLICATE_PAYOUT_RECORD"]);

const SEVERITY_COLOR: Record<string, string> = {
  low: "text-info",
  medium: "text-warn",
  high: "text-bad",
};

export default function ReconciliationPage() {
  const [results, setResults] = useState<ReconciliationResult[]>([]);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [payingOut, setPayingOut] = useState<string | null>(null);
  const [filter, setFilter] = useState<"all" | "exception" | "flagged" | "matched">("all");

  // Called from event handlers only (a click); the initial load lives in the effect below.
  const load = (refresh = false) => {
    setLoading(true);
    api
      .reconcileRun(refresh)
      .then(setResults)
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    let active = true;
    api
      .reconcileRun(false)
      .then((data) => active && setResults(data))
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, []);

  const approvePayout = async (r: ReconciliationResult) => {
    const approver = window.prompt("Reviewer name or email (recorded in the audit log):")?.trim();
    if (!approver) return;
    let note: string | undefined;
    if (r.anomalies.some((a) => CRITICAL_ANOMALIES.has(a.code))) {
      note = window.prompt("High-risk anomaly present. Justification for approving (min. 10 characters):")?.trim();
      if (!note) return;
    }
    const recordId = r.record_id;
    setPayingOut(recordId);
    try {
      await api.triggerPayout(recordId, approver, note);
      load(true);
    } catch (e) {
      alert(`Payout failed: ${e}`);
    } finally {
      setPayingOut(null);
    }
  };

  const filtered = results.filter((r) => {
    if (filter === "all") return true;
    if (filter === "matched") return r.status === "matched" || r.status === "auto_paid";
    return r.status === filter;
  });

  const counts = {
    all: results.length,
    exception: results.filter((r) => r.status === "exception").length,
    flagged: results.filter((r) => r.status === "flagged").length,
    matched: results.filter((r) => r.status === "matched" || r.status === "auto_paid").length,
  };

  // Invoice numbers that show up more than once in this cycle — this is the
  // duplicate-submission scenario, and it's the one place two rows in this
  // table legitimately share an invoice number, so we call it out rather
  // than let it look like a rendering glitch.
  const invoiceCounts = results.reduce<Record<string, number>>((acc, r) => {
    acc[r.invoice_number] = (acc[r.invoice_number] || 0) + 1;
    return acc;
  }, {});

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <h2 className="font-display font-semibold text-[22px] text-paper">Reconciliation &amp; audit log</h2>
          <p className="text-[13px] text-paper-dim mt-1">
            Every invoice, checked against Razorpay&apos;s settlement log and the bank statement — three sources, one answer.
          </p>
        </div>
        <button
          onClick={() => load(true)}
          className="flex items-center gap-1.5 text-[12.5px] text-paper-dim hover:text-paper border border-ink-line hover:border-gold/40 rounded-md px-3 py-1.5"
        >
          <RefreshCw size={13} className={loading ? "animate-spin" : ""} />
          Re-run reconciliation
        </button>
      </div>

      <div className="flex gap-2">
        {(["all", "exception", "flagged", "matched"] as const).map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`px-3 py-1.5 rounded-full text-[12px] border transition-colors ${
              filter === f
                ? "border-gold/50 bg-gold/10 text-gold"
                : "border-ink-line text-paper-dim hover:text-paper"
            }`}
          >
            {f === "all" ? "All" : f[0].toUpperCase() + f.slice(1)} · {counts[f]}
          </button>
        ))}
      </div>

      <div className="rounded-xl border border-ink-line bg-ink-raised overflow-hidden">
        <table className="w-full text-[12.5px]">
          <thead>
            <tr className="text-left text-paper-dim border-b border-ink-line">
              <th className="font-normal px-5 py-3 w-6"></th>
              <th className="font-normal px-3 py-3">Invoice</th>
              <th className="font-normal px-3 py-3">Vendor</th>
              <th className="font-normal px-3 py-3 text-right">Invoice amt</th>
              <th className="font-normal px-3 py-3 text-right">Razorpay log</th>
              <th className="font-normal px-3 py-3 text-right">Bank statement</th>
              <th className="font-normal px-3 py-3 text-right">Confidence</th>
              <th className="font-normal px-3 py-3">Status</th>
              <th className="font-normal px-5 py-3"></th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((r) => {
              const isOpen = expanded === r.record_id;
              const isDuplicateRow = invoiceCounts[r.invoice_number] > 1;
              return (
                <React.Fragment key={r.record_id}>
                  <tr
                    className="border-b border-ink-line last:border-0 hover:bg-white/[0.015] cursor-pointer"
                    onClick={() => setExpanded(isOpen ? null : r.record_id)}
                  >
                    <td className="px-5 py-3 text-paper-dim">
                      {isOpen ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                    </td>
                    <td className="px-3 py-3">
                      <span className="font-ledger text-paper">{r.invoice_number}</span>
                      {isDuplicateRow && (
                        <span className="block text-[10px] text-bad mt-0.5">
                          {r.source_file.toLowerCase().includes("duplicate") ? "resubmitted copy" : "original submission"}
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-3 text-paper-dim max-w-[160px] truncate">{r.vendor_name}</td>
                    <td className="px-3 py-3 text-right font-ledger tabular text-paper">{formatINR(r.invoice_total)}</td>
                    <td className="px-3 py-3 text-right font-ledger tabular text-paper-dim">{formatINR(r.razorpay_amount)}</td>
                    <td className="px-3 py-3 text-right font-ledger tabular text-paper-dim">{formatINR(r.bank_amount)}</td>
                    <td className="px-3 py-3 text-right font-ledger tabular">
                      <span className={r.confidence_score > 0.95 ? "text-good" : r.confidence_score >= 0.75 ? "text-warn" : "text-bad"}>
                        {(r.confidence_score * 100).toFixed(0)}%
                      </span>
                    </td>
                    <td className="px-3 py-3">
                      <StatusPill status={r.status} />
                    </td>
                    <td className="px-5 py-3 text-right">
                      {r.status === "exception" || r.status === "flagged" ? (
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            approvePayout(r);
                          }}
                          disabled={payingOut === r.record_id}
                          className="flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-gold/10 text-gold text-[11.5px] font-medium hover:bg-gold/20 disabled:opacity-50"
                        >
                          <Zap size={12} />
                          {payingOut === r.record_id ? "Processing…" : "Approve & pay"}
                        </button>
                      ) : (
                        <span className="text-[11px] text-paper-dim">
                          {r.payout_id ? "Settled" : "—"}
                        </span>
                      )}
                    </td>
                  </tr>
                  {isOpen && (
                    <tr className="bg-ink/60 border-b border-ink-line last:border-0">
                      <td colSpan={9} className="px-8 py-4">
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                          <div>
                            <SectionLabel>Bank details cross-check</SectionLabel>
                            <div className="text-[12px] space-y-1">
                              <div className="flex justify-between">
                                <span className="text-paper-dim">Invoice account</span>
                                <span className="font-ledger text-paper">{r.invoice_account_no || "—"}</span>
                              </div>
                              <div className="flex justify-between">
                                <span className="text-paper-dim">Razorpay beneficiary account</span>
                                <span className="font-ledger text-paper">{r.razorpay_account_no || "—"}</span>
                              </div>
                              <div className="flex justify-between">
                                <span className="text-paper-dim">Payout ID</span>
                                <span className="font-ledger text-paper">{r.payout_id || "—"}</span>
                              </div>
                              <div className="flex justify-between">
                                <span className="text-paper-dim">UTR</span>
                                <span className="font-ledger text-paper">{r.utr || "—"}</span>
                              </div>
                            </div>
                            <p className="text-[12px] text-paper-dim mt-3 pt-3 border-t border-ink-line">
                              <span className="text-paper">What we&apos;d do next: </span>
                              {r.recommended_action}
                            </p>
                          </div>
                          <div>
                            <SectionLabel>Anomalies ({r.anomalies.length})</SectionLabel>
                            {r.anomalies.length === 0 ? (
                              <p className="text-[12px] text-good">Clean 3-way match — nothing to flag here.</p>
                            ) : (
                              <div className="space-y-2.5">
                                {r.anomalies.map((a, i) => (
                                  <div key={i} className="flex gap-2 text-[12px]">
                                    <AlertTriangle size={13} className={`shrink-0 mt-0.5 ${SEVERITY_COLOR[a.severity]}`} />
                                    <div>
                                      <p className={`font-medium ${SEVERITY_COLOR[a.severity]}`}>
                                        {a.code.replace(/_/g, " ").toLowerCase()}
                                      </p>
                                      <p className="text-paper-dim">{a.message}</p>
                                    </div>
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        </div>
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              );
            })}
          </tbody>
        </table>
        {filtered.length === 0 && !loading && (
          <div className="p-8 text-center text-paper-dim text-[13px]">Nothing in this filter yet.</div>
        )}
      </div>
    </div>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <h4 className="flex items-center gap-2 text-[12px] text-paper-dim mb-2.5">
      <span className="w-2 h-px bg-gold/60" />
      {children}
    </h4>
  );
}
