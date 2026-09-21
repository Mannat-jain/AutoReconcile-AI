export const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export type LineItem = {
  description: string;
  quantity: number;
  unit_price: number;
  amount: number;
};

export type ExtractedInvoice = {
  source_file: string;
  vendor_name: string | null;
  gstin: string | null;
  invoice_number: string | null;
  invoice_date: string | null;
  due_date: string | null;
  bill_to: string | null;
  bank_name: string | null;
  account_number: string | null;
  ifsc: string | null;
  line_items: LineItem[];
  subtotal: number | null;
  gst_amount: number | null;
  tds_amount: number | null;
  total_payable: number | null;
  extraction_confidence: number;
  raw_text_snippet: string | null;
};

export type AnomalyFlag = {
  code: string;
  severity: "low" | "medium" | "high";
  message: string;
};

export type ReconciliationStatus = "matched" | "flagged" | "exception" | "auto_paid";

export type ReconciliationResult = {
  record_id: string;
  source_file: string;
  invoice_number: string;
  vendor_name: string | null;
  invoice_total: number | null;
  razorpay_amount: number | null;
  bank_amount: number | null;
  invoice_account_no: string | null;
  razorpay_account_no: string | null;
  confidence_score: number;
  status: ReconciliationStatus;
  anomalies: AnomalyFlag[];
  payout_id: string | null;
  utr: string | null;
  recommended_action: string;
};

export type DashboardMetrics = {
  total_invoices: number;
  total_reconciled_amount: number;
  matched_count: number;
  flagged_count: number;
  exception_count: number;
  auto_paid_count: number;
  discrepancy_rate_pct: number;
  time_saved_minutes: number;
  avg_confidence: number;
  status_breakdown: { status: string; count: number }[];
};

export type SampleInvoice = { filename: string; url: string };

export type AuditLogEntry = Record<string, unknown>;

async function j<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`API error ${res.status}: ${text}`);
  }
  return res.json();
}

export const api = {
  health: () => fetch(`${API_BASE}/api/health`, { cache: "no-store" }).then((r) => j<{ status: string; mock_mode: boolean }>(r)),
  sampleInvoices: () => fetch(`${API_BASE}/api/sample-invoices`, { cache: "no-store" }).then((r) => j<SampleInvoice[]>(r)),
  extractSample: (filename: string) =>
    fetch(`${API_BASE}/api/extract/sample/${encodeURIComponent(filename)}`, { cache: "no-store" }).then((r) => j<ExtractedInvoice>(r)),
  extractUpload: (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return fetch(`${API_BASE}/api/extract`, { method: "POST", body: fd }).then((r) => j<ExtractedInvoice>(r));
  },
  reconcileRun: (refresh = false) =>
    fetch(`${API_BASE}/api/reconcile/run${refresh ? "?refresh=true" : ""}`, { cache: "no-store" }).then((r) => j<ReconciliationResult[]>(r)),
  dashboardMetrics: () => fetch(`${API_BASE}/api/dashboard/metrics`, { cache: "no-store" }).then((r) => j<DashboardMetrics>(r)),
  // A human approves ONE payout. The server enforces the confidence gate itself, so the client only
  // identifies the reviewer (recorded in the audit log) and, for high-risk anomalies, gives a reason.
  triggerPayout: (recordId: string, approvedBy: string, note?: string) =>
    fetch(`${API_BASE}/api/payout/trigger`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ record_id: recordId, approved_by: approvedBy, note }),
    }).then((r) => j<Record<string, unknown>>(r)),
  verifyAuditLog: () =>
    fetch(`${API_BASE}/api/audit-log/verify`, { cache: "no-store" }).then((r) =>
      j<{ valid: boolean; entries: number; broken_at: number | null; reason: string }>(r)
    ),
  auditLog: () => fetch(`${API_BASE}/api/audit-log`, { cache: "no-store" }).then((r) => j<AuditLogEntry[]>(r)),
};

export function formatINR(amount: number | null | undefined): string {
  if (amount === null || amount === undefined) return "—";
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 2,
  }).format(amount);
}
