import { FileInput, ScanEye, GitCompareArrows, ShieldCheck, Zap, Users } from "lucide-react";

const STAGES = [
  {
    icon: FileInput,
    title: "1. Ingestion",
    desc: "PDF/image invoices land in the pipeline via drag-and-drop upload or a watched folder.",
  },
  {
    icon: ScanEye,
    title: "2. Vision-OCR extraction",
    desc: "GPT-4o Vision (or deterministic OCR fallback) extracts GSTIN, line items, amounts, dates and bank details into a strict JSON schema.",
  },
  {
    icon: GitCompareArrows,
    title: "3. Hybrid matching",
    desc: "Deterministic rules match invoice numbers, amounts and account numbers against Razorpay logs and bank statements. Fuzzy matching (rapidfuzz) reconciles vendor name variants.",
  },
  {
    icon: ShieldCheck,
    title: "4. Anomaly detection & scoring",
    desc: "Price mismatches, missing TDS, duplicates, and bank detail changes each carry a fixed confidence penalty, producing an auditable 0.0–1.0 score.",
  },
  {
    icon: Zap,
    title: "5. Autonomous payout",
    desc: "Confidence > 0.95 triggers a mock Razorpay Payouts API call automatically, gated by an idempotency key.",
  },
  {
    icon: Users,
    title: "6. Human-in-the-loop",
    desc: "Everything else lands in the Exception Review Queue for one-click manual approval — never silently retried.",
  },
];

export default function ArchitecturePage() {
  return (
    <div className="space-y-8">
      <div>
        <h2 className="font-display font-semibold text-[22px] text-paper">Architecture &amp; pipeline flow</h2>
        <p className="text-[13px] text-paper-dim mt-1 max-w-2xl">
          What actually happens between a PDF landing in the inbox and money leaving the account —
          worth having open if someone asks "wait, how does it decide?"
        </p>
      </div>

      <div className="relative">
        <div className="hidden md:block absolute left-[27px] top-6 bottom-6 w-px bg-ink-line" />
        <div className="space-y-4">
          {STAGES.map(({ icon: Icon, title, desc }) => (
            <div key={title} className="flex gap-4 items-start">
              <div className="relative z-10 w-14 h-14 shrink-0 rounded-xl bg-ink-raised border border-ink-line flex items-center justify-center">
                <Icon size={20} className="text-gold" strokeWidth={1.8} />
              </div>
              <div className="pt-1.5">
                <h3 className="font-display font-semibold text-[14.5px] text-paper">{title}</h3>
                <p className="text-[12.5px] text-paper-dim mt-0.5 max-w-xl leading-relaxed">{desc}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="rounded-xl border border-ink-line bg-ink-raised p-5">
          <h3 className="font-display font-semibold text-[14px] text-paper mb-2">Deterministic guardrails vs. LLM reasoning</h3>
          <p className="text-[12.5px] text-paper-dim leading-relaxed">
            Amount tolerance checks, account/IFSC equality, and confidence scoring are pure Python —
            reproducible and auditable. An LLM is only consulted to draft plain-English summaries for
            human reviewers; it never changes a computed confidence score or status directly.
          </p>
        </div>
        <div className="rounded-xl border border-ink-line bg-ink-raised p-5">
          <h3 className="font-display font-semibold text-[14px] text-paper mb-2">Hallucination prevention</h3>
          <p className="text-[12.5px] text-paper-dim leading-relaxed">
            Every numeric field an LLM extraction claims is re-verified against the raw source text
            before being trusted. Unverifiable numbers cap the extraction confidence, which flows
            through to the final reconciliation score.
          </p>
        </div>
        <div className="rounded-xl border border-ink-line bg-ink-raised p-5">
          <h3 className="font-display font-semibold text-[14px] text-paper mb-2">Payout safety</h3>
          <p className="text-[12.5px] text-paper-dim leading-relaxed">
            Autonomous payouts require confidence &gt; 0.95, are keyed by an idempotency hash to
            prevent double-firing on retry, and every attempt — successful, blocked, or duplicate — is
            appended to an immutable audit log.
          </p>
        </div>
        <div className="rounded-xl border border-ink-line bg-ink-raised p-5">
          <h3 className="font-display font-semibold text-[14px] text-paper mb-2">Full technical deep-dive</h3>
          <p className="text-[12.5px] text-paper-dim leading-relaxed">
            See <span className="font-ledger text-gold">docs/ARCHITECTURE.md</span> in the repository
            for the complete rulebook, threat model, and security posture for handling financial data.
          </p>
        </div>
      </div>
    </div>
  );
}
