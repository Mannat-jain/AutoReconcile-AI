"use client";

import { useEffect, useState } from "react";
import { ShieldAlert, Zap, Clock3 } from "lucide-react";
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip, BarChart, Bar, XAxis, YAxis, CartesianGrid } from "recharts";
import { api, DashboardMetrics, ReconciliationResult, formatINR } from "@/lib/api";
import StatusPill from "@/components/StatusPill";
import StampSeal from "@/components/StampSeal";

const STATUS_COLORS: Record<string, string> = {
  matched: "#4ADE9E",
  auto_paid: "#6FA8F5",
  flagged: "#F2B84B",
  exception: "#F0715C",
};

export default function DashboardPage() {
  const [metrics, setMetrics] = useState<DashboardMetrics | null>(null);
  const [results, setResults] = useState<ReconciliationResult[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.dashboardMetrics(), api.reconcileRun()])
      .then(([m, r]) => {
        setMetrics(m);
        setResults(r);
      })
      .catch((e) => setError(String(e)));
  }, []);

  if (error) return <BackendOfflineNotice error={error} />;
  if (!metrics) return <p className="text-paper-dim text-sm">Pulling this cycle's numbers…</p>;

  const pieData = metrics.status_breakdown
    .filter((s) => s.count > 0)
    .map((s) => ({ name: s.status, value: s.count }));

  const barData = results.map((r) => ({
    name: r.invoice_number,
    confidence: Math.round(r.confidence_score * 100),
  }));

  const needsReview = metrics.flagged_count + metrics.exception_count;

  return (
    <div className="space-y-8">
      {/* ── Hero: a sentence a controller would actually say, not a headline ── */}
      <div className="rounded-xl border border-ink-line bg-ink-raised overflow-hidden">
        <div className="flex flex-col md:flex-row items-stretch">
          <div className="flex-1 p-6 md:p-7">
            <p className="text-[12px] text-paper-dim mb-2">This cycle's reconciliation run</p>
            <p className="font-display font-semibold text-paper text-[22px] md:text-[25px] leading-snug max-w-xl">
              <span className="font-ledger tabular text-gold">{formatINR(metrics.total_reconciled_amount)}</span> moved
              through the books across {metrics.total_invoices} vendor invoices —{" "}
              {needsReview > 0 ? (
                <>
                  <span className="text-paper">{needsReview}</span> of them needed a second look before anything got paid.
                </>
              ) : (
                <>every single one cleared on its own.</>
              )}
            </p>
            <div className="flex flex-wrap gap-x-8 gap-y-3 mt-6">
              <MiniStat icon={ShieldAlert} tone="warn" value={`${metrics.discrepancy_rate_pct}%`} label="flagged for review" />
              <MiniStat icon={Zap} tone="good" value={String(metrics.auto_paid_count)} label="paid with zero human input" />
              <MiniStat icon={Clock3} tone="info" value={`${metrics.time_saved_minutes} min`} label="of manual matching skipped" />
            </div>
          </div>
          <div className="hidden md:flex items-center justify-center px-8 border-l border-ink-line bg-ink/40">
            <StampSeal
              label={metrics.auto_paid_count > 0 ? "AUTO-CLEARED" : "REVIEWED"}
              sublabel={new Date().toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" })}
            />
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-4">
        <div className="lg:col-span-2 rounded-xl border border-ink-line bg-ink-raised p-5">
          <h3 className="font-display font-semibold text-[14px] text-paper mb-1">Where things landed</h3>
          <p className="text-[11.5px] text-paper-dim mb-3">{metrics.total_invoices} invoices, sorted by outcome</p>
          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={pieData} dataKey="value" nameKey="name" innerRadius={50} outerRadius={80} paddingAngle={3}>
                  {pieData.map((entry, i) => (
                    <Cell key={i} fill={STATUS_COLORS[entry.name] || "#8A93AC"} stroke="none" />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{ background: "#10162A", border: "1px solid #1E2740", borderRadius: 8, fontSize: 12 }}
                  labelStyle={{ color: "#E7EAF2" }}
                />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <div className="flex flex-wrap gap-x-4 gap-y-1.5 mt-2">
            {pieData.map((entry) => (
              <div key={entry.name} className="flex items-center gap-1.5 text-[11.5px] text-paper-dim">
                <span className="w-2 h-2 rounded-full" style={{ background: STATUS_COLORS[entry.name] }} />
                {entry.name.replace("_", " ")} · {entry.value}
              </div>
            ))}
          </div>
        </div>

        <div className="lg:col-span-3 rounded-xl border border-ink-line bg-ink-raised p-5">
          <h3 className="font-display font-semibold text-[14px] text-paper mb-1">How sure we are, invoice by invoice</h3>
          <p className="text-[11.5px] text-paper-dim mb-3">Anything under the 95% line waits for a human</p>
          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={barData} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
                <CartesianGrid stroke="#1E2740" vertical={false} />
                <XAxis dataKey="name" tick={{ fill: "#8A93AC", fontSize: 10.5 }} axisLine={{ stroke: "#1E2740" }} tickLine={false} />
                <YAxis tick={{ fill: "#8A93AC", fontSize: 10.5 }} axisLine={false} tickLine={false} domain={[0, 100]} />
                <Tooltip
                  cursor={{ fill: "rgba(232,185,74,0.06)" }}
                  contentStyle={{ background: "#10162A", border: "1px solid #1E2740", borderRadius: 8, fontSize: 12 }}
                  labelStyle={{ color: "#E7EAF2" }}
                  formatter={(v) => [`${v}%`, "Confidence"]}
                />
                <Bar dataKey="confidence" radius={[4, 4, 0, 0]}>
                  {barData.map((entry, i) => (
                    <Cell key={i} fill={entry.confidence > 95 ? "#4ADE9E" : entry.confidence >= 75 ? "#F2B84B" : "#F0715C"} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      <div className="rounded-xl border border-ink-line bg-ink-raised overflow-hidden">
        <div className="px-5 py-4 border-b border-ink-line flex items-center justify-between">
          <h3 className="font-display font-semibold text-[14px] text-paper">This cycle at a glance</h3>
          <a href="/reconciliation" className="text-[12px] text-gold hover:underline">
            Open the full audit log →
          </a>
        </div>
        <table className="w-full text-[12.5px]">
          <thead>
            <tr className="text-left text-paper-dim border-b border-ink-line">
              <th className="font-normal px-5 py-2.5">Invoice</th>
              <th className="font-normal px-5 py-2.5">Vendor</th>
              <th className="font-normal px-5 py-2.5 text-right">Amount</th>
              <th className="font-normal px-5 py-2.5">Status</th>
            </tr>
          </thead>
          <tbody>
            {results.map((r) => (
              <tr key={r.record_id} className="border-b border-ink-line last:border-0">
                <td className="px-5 py-3 font-ledger text-paper">{r.invoice_number}</td>
                <td className="px-5 py-3 text-paper-dim">{r.vendor_name}</td>
                <td className="px-5 py-3 text-right font-ledger tabular text-paper">{formatINR(r.invoice_total)}</td>
                <td className="px-5 py-3">
                  <StatusPill status={r.status} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function MiniStat({
  icon: Icon,
  value,
  label,
  tone,
}: {
  icon: React.ElementType;
  value: string;
  label: string;
  tone: "warn" | "good" | "info";
}) {
  const color = { warn: "text-warn", good: "text-good", info: "text-info" }[tone];
  return (
    <div className="flex items-center gap-2.5">
      <Icon size={15} className={color} strokeWidth={2} />
      <div>
        <span className="font-ledger tabular text-paper text-[14px]">{value}</span>
        <span className="text-[11.5px] text-paper-dim ml-1.5">{label}</span>
      </div>
    </div>
  );
}

function BackendOfflineNotice({ error }: { error: string }) {
  return (
    <div className="rounded-xl border border-bad/30 bg-bad/5 p-6 max-w-xl">
      <h3 className="font-display font-semibold text-paper mb-1">Can&apos;t reach the backend</h3>
      <p className="text-[13px] text-paper-dim mb-3">
        The frontend couldn&apos;t reach the FastAPI backend. Make sure it&apos;s running:
      </p>
      <pre className="bg-ink border border-ink-line rounded-md p-3 text-[12px] font-ledger text-paper-dim overflow-x-auto">
        cd backend{"\n"}uvicorn main:app --reload --port 8000
      </pre>
      <p className="text-[11px] text-paper-dim mt-3 font-ledger">{error}</p>
    </div>
  );
}
