# ARCHITECTURE.md
## AutoReconcile AI — Technical Deep-Dive

This document covers the reasoning behind the pipeline design, with a focus
on three things a Razorpay reviewer will look for in an "AI Finance
Controller" submission: where determinism ends and LLM judgment begins, how
hallucination is actively prevented (not just hoped against), and what a
production hardening pass would look like for a system that's allowed to
move money.

---

## 1. Deterministic Guardrails vs. LLM Fuzzy Matching

A recurring failure mode in "AI does finance" demos is routing every
decision through an LLM prompt, including the parts that don't need
judgment at all — an amount either matches within tolerance or it doesn't;
an account number either equals another account number or it doesn't. Every
extra token spent asking an LLM to eyeball two numbers is both slower and,
worse, a place where the system's behavior stops being reproducible.

AutoReconcile AI splits the pipeline explicitly:

| Decision | Mechanism | Why |
|---|---|---|
| Does invoice total match Razorpay settlement amount? | Deterministic (`abs(diff)/total > 2%`) | Purely numeric; must be reproducible & auditable |
| Do invoice bank account/IFSC match Razorpay beneficiary record? | Deterministic (exact string equality) | Security-critical — no fuzziness allowed here at all |
| Is this settlement pattern explainable by an undisclosed TDS deduction? | Deterministic (checks against known TDS rates: 1%, 2%, 5%, 10%) | A closed, enumerable rule set; still no LLM needed |
| Does "CloudNine Hosting Pvt Ltd" on the invoice match "CloudNine Hosting Pvt. Ltd." in the Razorpay log? | Fuzzy (`rapidfuzz.fuzz.token_sort_ratio`) | Genuinely benefits from tolerant string matching; low stakes if imprecise (it only nudges confidence, never gates a bank-detail check) |
| Confidence score (0.0–1.0) | Deterministic formula: `base(extraction_confidence, name_similarity) − Σ(severity penalties)` | Every point of the score is traceable to a specific rule that fired — critical for an audit trail |
| Plain-English summary for a human reviewer | LLM (optional, advisory-only) | This is the one place free-form language generation adds value, and it's explicitly never allowed to change `confidence_score` or `status` |

**The rule of thumb applied throughout:** if a check can be expressed as a
closed-form rule, it is — an LLM is reserved for tasks that are inherently
about *reading unstructured text*, not for arithmetic or equality checks on
structured data that's already been extracted.

---

## 2. Hallucination Prevention

Hallucination risk in this pipeline is concentrated almost entirely in the
extraction stage (turning a PDF into structured JSON) — everything
downstream operates on already-structured data, so the anti-hallucination
work is front-loaded there.

### 2.1 Strict schema enforcement
`parser.py` never returns free text. Whether extraction runs via the
deterministic OCR path or the optional GPT-4o Vision path, the output is
always coerced into the `ExtractedInvoice` Pydantic model
(`backend/models.py`). Any field the model can't populate is `null` rather
than a fabricated guess — a missing GSTIN shows up as `null`, not as an
invented-looking string that happens to be 15 characters.

### 2.2 Source-text verification (the core guardrail)
When the LLM path is used, `_verify_against_source()` re-scans the raw
extracted document text and checks that every numeric field the model
claims (subtotal, GST, total payable) actually appears, formatted, in the
source. A number the model "extracted" that doesn't appear anywhere in the
document text is a strong hallucination signal — each unverifiable number
directly lowers `extraction_confidence`, which flows straight into the
downstream reconciliation confidence score. In other words: **a
hallucinated total doesn't just produce wrong data, it produces
data the system already distrusts before it ever reaches a payout
decision.**

### 2.3 Fail-closed on extraction errors
If the LLM call errors, times out, or returns non-JSON content,
`extract_invoice()` catches the exception and falls back to the
deterministic OCR extractor rather than propagating a partial or corrupted
result. The system degrades to "more conservative," never to "silently
wrong."

### 2.4 No LLM in the money-moving path
As covered in §1, the LLM (when configured) touches document reading and
advisory summaries only. `matcher.py` and `razorpay_service.py` — the two
modules that decide *whether* and *how much* to pay — never call an LLM.
This means a hallucination, even a bad one, is structurally incapable of
directly causing a wrong payout amount; it can only ever lower a confidence
score and force a human review.

---

## 3. Security Best Practices for Financial Operations

These are the practices actually implemented in this proof of concept, plus
notes on what a production hardening pass would add on top.

### Implemented in this repo

- **Confidence-gated autonomy.** `razorpay_service.create_payout()` raises
  `PermissionError` and refuses to fire if `confidence_score <=
  0.95` — this check lives in the payout service itself, not just in the
  caller, so no code path can bypass it by mistake.
- **Idempotency keys.** Every payout attempt is keyed by
  `sha256(invoice_number:amount)`. A retried or duplicated call for the same
  invoice/amount pair is rejected outright rather than firing a second
  transfer.
- **Immutable audit log.** Every payout attempt — executed, blocked for low
  confidence, or suppressed as a duplicate — is appended to
  `payout_audit_log.jsonl`. Nothing is ever overwritten or deleted from this
  log within the application; it's designed to be shipped to a proper
  append-only store (e.g. a WORM S3 bucket or an audit database) in
  production.
- **Explicit account/IFSC equality checks.** Bank-detail verification never
  uses fuzzy matching — a single-character difference in an account number
  or IFSC code is always treated as a hard mismatch (`BANK_DETAILS_MISMATCH`,
  `high` severity), which is exactly the class of anomaly most associated
  with vendor-impersonation fraud (an attacker changing "their" bank
  details before an invoice is paid).
- **Human-in-the-loop by default.** The default posture is "route to a
  human" — auto-payout is the exception carved out for a narrow,
  high-confidence band, not the default path.
- **Mock-mode-by-default payments.** The Razorpay Payouts integration only
  goes live if both `RAZORPAY_KEY_ID` and `RAZORPAY_KEY_SECRET` are set;
  otherwise it runs in a fully simulated mode. This means the proof of
  concept can be run, forked, and demoed by anyone without risk of an
  accidental real transfer.

### Recommended hardening for a production deployment

- **Secrets management.** Move `OPENAI_API_KEY` / `RAZORPAY_KEY_SECRET` out
  of `.env` files and into a managed secret store (AWS Secrets Manager,
  GCP Secret Manager, HashiCorp Vault) with rotation policies.
- **Least-privilege Razorpay API keys.** Use a RazorpayX key scoped only to
  the Payouts endpoints this service needs, not full account access.
  Enforce payout-amount ceilings and beneficiary allow-lists at the
  Razorpay account level as a second, independent layer of defense beyond
  this application's own confidence gate.
- **Persistent, append-only audit storage.** Replace the local JSONL file
  with a write-once datastore (or at minimum a database table with no
  `UPDATE`/`DELETE` grants for the application role) and ship logs to a
  SIEM.
- **Authentication & RBAC on the review UI.** The Exception Review Queue's
  "Approve & pay" action currently has no auth layer in this demo — a
  production build needs role-based access control so only authorized
  finance staff can approve payouts, plus a maker-checker (dual approval)
  flow for payouts above a configurable amount.
- **PII/PCI-adjacent data handling.** Bank account numbers and GSTINs
  should be encrypted at rest, masked in logs and UI by default (show last
  4 digits), and excluded from any data sent to a third-party LLM provider
  unless a signed BAA/DPA is in place with that provider.
- **Rate limiting & webhook verification.** If wired to real Razorpay
  webhooks for settlement confirmation, verify webhook signatures
  (`X-Razorpay-Signature`) on every inbound event and rate-limit the public
  API surface.
- **CORS lockdown.** `main.py` currently allows `*` origins for local demo
  convenience (`app.add_middleware(CORSMiddleware, allow_origins=["*"])`) —
  this must be restricted to the deployed frontend's exact origin in
  production.

---

## 4. Confidence Scoring Formula (Reference)

```
base  = 0.5 × extraction_confidence + 0.5 × vendor_name_similarity
penalty = Σ over anomalies of:
            low    → 0.05
            medium → 0.15
            high   → 0.35
confidence_score = clamp(base − penalty, 0.0, 1.0)

status:
  confidence_score > 0.95            → auto_paid / matched
  else, any HIGH-severity anomaly    → exception  (Exception Review Queue)
  else                               → flagged    (quick human review)
```

This formula is intentionally simple and entirely inspectable — every
component of a given invoice's score can be explained to a finance reviewer
in one sentence, which matters far more for a system that moves money than
squeezing out marginal accuracy from a more opaque model.
