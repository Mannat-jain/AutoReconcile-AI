import { LucideIcon } from "lucide-react";

export default function MetricCard({
  label,
  value,
  sublabel,
  icon: Icon,
  accent = "gold",
}: {
  label: string;
  value: string;
  sublabel?: string;
  icon: LucideIcon;
  accent?: "gold" | "good" | "warn" | "bad" | "info";
}) {
  const accentClass = {
    gold: "text-gold bg-gold/10",
    good: "text-good bg-good/10",
    warn: "text-warn bg-warn/10",
    bad: "text-bad bg-bad/10",
    info: "text-info bg-info/10",
  }[accent];

  return (
    <div className="rounded-xl border border-ink-line bg-ink-raised p-5 flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <span className="text-[12.5px] text-paper-dim">{label}</span>
        <div className={`w-7 h-7 rounded-md flex items-center justify-center ${accentClass}`}>
          <Icon size={14} strokeWidth={2} />
        </div>
      </div>
      <div>
        <p className="font-ledger text-[26px] leading-none text-paper tabular">{value}</p>
        {sublabel && <p className="text-[11.5px] text-paper-dim mt-1.5">{sublabel}</p>}
      </div>
    </div>
  );
}
