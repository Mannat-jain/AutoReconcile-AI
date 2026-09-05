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
- (Optional) an OpenAI API key, if you want to exercise the live Vision-LLM
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
for how that stays faithful to a real Vision-LLM pipeline).

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
already populated from the 5 bundled sample invoices.

### 2.4 Regenerating the sample invoices (optional)

The 6 demo PDFs in `sample_data/invoices/` are pre-generated and committed,
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
 ┌──────────────────┐   Vision-LLM (GPT-4o) if OPENAI_API_KEY set,
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
 ┌──────────────────┐   Idempotency-keyed, append-only audit log
 │ razorpay_service.py│  (payout_audit_log.jsonl). Refuses to fire below
 │ (Autonomous payout)│  the confidence gate — no silent retries.
 └──────────────────┘
```

**Failure handling principles baked into the pipeline:**

- **Never crash on a bad document.** If Vision-LLM extraction fails or
  returns malformed JSON, `parser.py` degrades gracefully to the
  deterministic OCR extractor rather than dropping the invoice.
- **Never guess when unsure.** Anything that isn't a clean, high-confidence
  3-way match is routed to a human — the system has no code path that pays
  a low-confidence invoice automatically.
- **Never pay twice.** Every payout attempt is keyed by an idempotency hash
  of `(invoice_number, amount)`; duplicate attempts are refused, not retried.
- **Never lose the paper trail.** Every payout attempt — successful, blocked,
  or duplicate-suppressed — is appended to an immutable JSONL audit log,
  viewable live from the "API logs" button in the app.

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
│   ├── generate_invoices.py     (regenerates the 6 demo PDFs)
│   ├── invoices/                (5 vendors, 6 files incl. 1 duplicate)
│   ├── razorpay_payouts_log.csv
│   └── bank_statement.csv
├── backend/
│   ├── main.py                  (FastAPI app / routes)
│   ├── models.py                (Pydantic schemas)
│   ├── parser.py                (ingestion & extraction)
│   ├── matcher.py                (3-way matching & anomaly detection)
│   ├── razorpay_service.py      (mock Payouts API client)
│   └── requirements.txt
├── frontend/                    (Next.js 16 / React / Tailwind)
│   └── src/app/{page,ingestion,reconciliation,architecture}
└── docs/
    └── ARCHITECTURE.md          (deep technical dive)
    └── PITCH_SCRIPT.md          (5-minute demo video script)
```

## 6. Known Limitations of this Proof of Concept

- Extraction is tuned to the layout of the bundled sample invoices; a
  production system would need a more general Vision-LLM prompt (already
  stubbed in `parser.py::llm_vision_extract`) plus a broader eval set.
- `razorpay_service.py` runs in mock mode by default; live RazorpayX wiring
  is stubbed but intentionally not implemented against real credentials.
- Reconciliation state lives in-process (an in-memory cache in `main.py`)
  rather than a database — sufficient for a demo, not for production
  concurrency.
