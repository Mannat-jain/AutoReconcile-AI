import { ReconciliationStatus } from "@/lib/api";

const CONFIG: Record<ReconciliationStatus, { label: string; dot: string; text: string; bg: string }> = {
  matched: { label: "Matched", dot: "bg-good", text: "text-good", bg: "bg-good/10" },
  auto_paid: { label: "Auto-paid", dot: "bg-good", text: "text-good", bg: "bg-good/10" },
  flagged: { label: "Flagged", dot: "bg-warn", text: "text-warn", bg: "bg-warn/10" },
  exception: { label: "Exception", dot: "bg-bad", text: "text-bad", bg: "bg-bad/10" },
};

export default function StatusPill({ status }: { status: ReconciliationStatus }) {
  const c = CONFIG[status];
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11.5px] font-medium ${c.text} ${c.bg}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${c.dot}`} />
      {c.label}
    </span>
  );
}
