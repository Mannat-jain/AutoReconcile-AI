# AutoReconcile AI
### Autonomous Invoice-to-Payout Reconciliation Engine
**Track 4: AI Finance Controller — Razorpay AI Builder Internship 2026**

---

## 1. Project Overview & Value Proposition

Every growing startup on Razorpay eventually hits the same wall: a finance team
manually opening vendor invoices, cross-checking them against Razorpay payout
logs and bank statements, hunting for the one line item that doesn't add up,
then wiring the payout by hand. It's slow, error-prone, and doesn't scale past
a handful of vendors a week.

**AutoReconcile AI** automates that entire loop:

1. **Reads** a vendor invoice (PDF/image) the way a human would — pulling out
   GSTIN, line items, amounts, due dates, and bank details.
2. **Cross-checks** it against Razorpay's settlement logs and the company's
   bank statement in a 3-way match.
3. **Scores** every invoice with a transparent, auditable confidence score
   (0.0–1.0) based on the anomalies it finds — price mismatches, missing TDS,
   duplicate submissions, changed bank details.
4. **Acts autonomously** on the invoices it's confident about (auto-triggers a
   Razorpay payout above a 0.95 confidence threshold) and **routes everything
   else to a human** for a one-click approval, instead of ever guessing.

### Why this matters for Razorpay

- **Sits directly on top of RazorpayX Payouts** — the reconciliation engine's
  entire reason to exist is to safely decide *when* to call the Payouts API,
  making it a natural extension of Razorpay's own product surface for
  business banking customers.
- **Turns "AI + fintech" from a slogan into a controllable system** — the
  demo deliberately shows *both* the AI doing useful autonomous work *and*
  the deterministic guardrails that keep it from ever silently paying the
  wrong vendor the wrong amount.
- **Immediately legible to a finance persona** — Executive Dashboard, audit
  log, and Exception Review Queue are the exact three screens a controller
  or FP&A lead already expects from tools like Ramp, Airbase, or Tipalti —
  just built AI-first and on Razorpay rails.

---

## 2. Quick Start Guide

### Prerequisites
- Python 3.10+
- Node.js 18.18+ and npm
- (Optional) an OpenAI API key, if you want to exercise the live LLM (GPT-4o)
  extraction path instead of the bundled offline OCR extractor.

### 2.1 Clone & configure

```bash
cd auto-reconcile-ai
cp .env.example backend/.env          # optional — works with all blanks
cp .env.example frontend/.env.local   # keep only NEXT_PUBLIC_API_BASE_URL
```

The project runs **entirely offline with zero API keys** — Razorpay payouts
run in a realistic mock mode, and invoice extraction falls back to a
deterministic OCR/regex parser (see [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
for how that stays faithful to a real LLM extraction pipeline).

### 2.2 Run the backend (FastAPI)

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate   # optional but recommended
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Backend is now live at `http://localhost:8000`. Sanity check:

```bash
curl http://localhost:8000/api/health
# {"status":"ok","mock_mode":true}
```

### 2.3 Run the frontend (Next.js)

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:3000**. You should land on the Executive Dashboard,
already populated from the 7 bundled sample invoices.

### 2.4 Regenerating the sample invoices (optional)

The first 6 demo PDFs in `sample_data/invoices/` are pre-generated and committed,
but you can regenerate them (e.g. after editing the anomaly scenarios) with:

```bash
cd sample_data
pip install reportlab
python3 generate_invoices.py
```

---

## 3. Architecture Workflow & Failure Handling Strategy

```
 Invoice (PDF/img)
        │
        ▼
 ┌──────────────────┐   LLM (GPT-4o, on pdfplumber text) if key set,
 │  parser.py        │   else deterministic OCR/regex fallback.
 │  (Ingestion)       │   Every numeric field is re-verified against
 └──────────────────┘   the raw source text before being trusted.
        │  ExtractedInvoice (strict JSON schema)
        ▼
 ┌──────────────────┐   Deterministic rules (amount tolerance, account/
 │  matcher.py        │   IFSC equality) do the heavy lifting; rapidfuzz
 │  (3-way matching)  │   handles vendor-name spelling variance; anomalies
 └──────────────────┘   are enumerated with fixed severity → confidence
        │  ReconciliationResult   penalties (fully auditable, not an LLM
        ▼                          black box).
   confidence > 0.95? ──No──► Exception Review Queue (human approves)
        │ Yes
        ▼
 ┌──────────────────┐   Durable idempotency ledger (SQLite, atomic INSERT)
 │ razorpay_service.py│  + hash-chained append-only audit log (JSONL).
 │ (Autonomous payout)│  Refuses to fire at/below the confidence gate unless
 └──────────────────┘   a NAMED human approves — no silent retries.
```

**Failure handling principles baked into the pipeline:**

- **Never crash on a bad document.** If LLM extraction fails or
  returns malformed JSON, `parser.py` degrades gracefully to the
  deterministic OCR extractor rather than dropping the invoice.
- **Never guess when unsure.** Anything that isn't a clean, high-confidence
  3-way match is routed to a human. The confidence gate lives inside the payout
  layer and the confidence value is never taken from a client: the only way
  past it is an explicit approval that names the reviewer (and, for high-risk
  anomalies such as a bank-details mismatch, a written justification).
- **Never pay twice.** Every payout is keyed by `sha256(vendor, invoice number,
  amount, currency)` and the key is claimed with one atomic `INSERT` into a durable
  SQLite ledger (`payout_store.py`). Retries, double clicks, concurrent requests and
  server restarts cannot create a second payout; a *failed* payout releases its key so
  it can be retried, and payouts that were already settled are never paid again.
- **Never lose the paper trail.** Every payout decision — executed, blocked,
  duplicate-suppressed, failed, human-approved — is appended to a JSONL audit log
  in which each entry carries the hash of the previous one (`audit.py`). Editing or
  deleting history breaks the chain, which `GET /api/audit-log/verify` detects.
  Viewable live from the "API logs" button in the app.

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the full deep-dive,
including the deterministic-vs-LLM rulebook and security posture.

---

## 4. 5-Minute Video Pitch Script

The full shot-by-shot script — what to click, what to say, and where to
speed up or slow down — lives in
[`docs/PITCH_SCRIPT.md`](docs/PITCH_SCRIPT.md). It walks through: the
problem framing, the Executive Dashboard, live invoice extraction, the
Exception Review Queue (including the bank-mismatch and duplicate-invoice
scenarios), the Architecture pipeline view, and a close.

---

## 5. Repository Structure

```
auto-reconcile-ai/
├── README.md                    ← you are here
├── .env.example
├── sample_data/
│   ├── generate_invoices.py     (regenerates the first 6 demo PDFs)
│   ├── invoices/                (6 vendors, 7 files incl. 1 duplicate;
│   │                             INV-1006 is the clean, queued invoice that auto-pays)
│   ├── razorpay_payouts_log.csv
│   └── bank_statement.csv
├── backend/
│   ├── main.py                  (FastAPI app / routes)
│   ├── models.py                (Pydantic schemas)
│   ├── parser.py                (ingestion & extraction)
│   ├── matcher.py                (3-way matching & anomaly detection)
│   ├── razorpay_service.py      (mock Payouts API client: gate + idempotency + audit)
│   ├── payout_store.py          (durable idempotency ledger, SQLite)
│   ├── audit.py                 (append-only, hash-chained audit log)
│   ├── tests/                   (43 pytest tests)
│   └── requirements.txt
├── frontend/                    (Next.js 16 / React / Tailwind)
│   └── src/app/{page,ingestion,reconciliation,architecture}
└── docs/
    └── ARCHITECTURE.md          (deep technical dive)
    └── PITCH_SCRIPT.md          (5-minute demo video script)
```

## 6. Known Limitations of this Proof of Concept

- Extraction is tuned to the layout of the bundled sample invoices; the optional
  GPT-4o path sends the *text* extracted by pdfplumber (it is not a true vision
  pipeline), so a production system would need image input, a more general prompt
  and a broader eval set.
- `razorpay_service.py` runs in mock mode by default; live RazorpayX wiring
  is stubbed but intentionally not implemented against real credentials.
- Reconciliation *results* live in an in-process cache (`main.py`); the payout ledger
  and audit log are durable, but a production system would keep everything in a real
  database.
- The audit log is tamper-**evident**, not tamper-**proof**: someone with write access
  could rewrite the whole file. Ship entries to write-once storage (see ARCHITECTURE.md).
- The review UI has no authentication; `approved_by` is self-declared. A real deployment
  needs SSO/RBAC and maker-checker approval for large payouts.
- Money is compared with `Decimal`, but the API models still carry `float` for JSON
  convenience; a production ledger should use integer minor units (paise).

## 7. Tests & CI

```bash
cd backend
pip install -r requirements-dev.txt
python -m pytest            # 43 tests
cd ../frontend && npm ci && npm run lint && npm run build
```

The suite pins the behaviours that matter for a system that moves money: an already-settled
invoice is never paid again; the confidence gate cannot be bypassed from the API; concurrent
identical payouts pay exactly once; a failed payout can be retried; the ledger survives a
restart; the audit chain detects edits and deletions; uploads cannot escape `uploads/`.
GitHub Actions runs both suites on every push (`.github/workflows/ci.yml`).

### Try the autonomous path
`INV-1006` (Apex Analytics) has a clean 3-way match and a *queued* payout, so confidence is
1.0 and the system releases the payout by itself (mock mode) - exactly once, even if you click
"Re-run reconciliation" repeatedly. Every other invoice is either already settled or needs a human.
