# AutoReconcile AI — 5-Minute Pitch Script


## 0:00 – 0:35 — The problem (talking head or voiceover over a blank browser)

> "Every finance team I've talked to at a growing startup has the same
> Tuesday: someone opens a folder of vendor invoices, pulls up the Razorpay
> settlement log in one tab, the bank statement in another, and manually
> checks that the numbers agree. It's tedious, it's easy to get wrong, and
> the one time it *does* go wrong — a vendor's bank account gets changed
> without anyone noticing — that's not a typo, that's a fraud incident.
>
> So I built AutoReconcile AI: an autonomous invoice-to-payout
> reconciliation engine. It reads the invoice, cross-checks it against
> Razorpay and the bank, and only pays automatically when it's genuinely
> confident. Let me show you."

---

## 0:35 – 1:35 — Executive Dashboard

> "This is the Executive Dashboard, and I designed the top line
> deliberately not to be another KPI-card wall — it's one sentence: how
> much money moved, across how many invoices, and how many needed a second
> look. Right now: [read the actual number on screen] moved through the
> books across six invoices, and three of them got flagged before a single
> rupee went out the door."


> "One invoice cleared with zero human input — that's the confidence-gated
> autonomy working exactly as intended. And this time-saved number isn't
> made up — it's twelve minutes of manual matching per invoice we didn't
> have to do."


> "This bar chart is the one I'd actually pull up in an audit: every
> invoice, its confidence score, and a hard line at ninety-five percent.
> Below that line, a human looks at it. Above it, the system acts on its
> own."

---

## 1:35 – 2:50 — Ingestion & Extraction


> "This is the ingestion pipeline. On the left, the actual invoice PDF —
> Bright Ads Media, a marketing invoice. On the right, structured JSON
> extracted from it in real time: GSTIN, line items, bank account, IFSC,
> the works."


> "Under the hood this either runs the extracted text through GPT-4o with a
> strict JSON schema, or — if there's no API key configured, like in this
> demo — falls back to a deterministic OCR and regex extractor. Either
> path, every number that comes out gets re-verified against the raw
> source text before it's trusted. If a number the model claims doesn't
> actually appear in the document, that's a hallucination signal, and it
> tanks the confidence score right here, before it ever reaches a payout
> decision."

---

## 2:50 – 4:05 — Reconciliation & the Exception Queue


> "This is the three-way match: invoice, Razorpay settlement log, bank
> statement. Three exceptions here, and each one is a genuinely different
> failure mode — this isn't one generic 'mismatch' bucket."


> "Velocity Logistics: the invoice lists one bank account, but Razorpay's
> beneficiary record has a *different* account number entirely. That's the
> single riskiest pattern in vendor fraud — someone quietly changing where
> the money goes — and the system refuses, structurally, to auto-pay this.
> Confidence sits at sixty-five percent. It's sitting in my queue."


> "And here's a duplicate invoice submission — same invoice number filed
> twice. Notice the tag: the system doesn't just silently merge these, it
> tells you explicitly which copy is which, so nobody accidentally pays
> twice."


> "When I do want to override — because I've actually checked it and it's
> fine — one click fires a real call into the Razorpay Payouts API
> integration point. Right now that's running in mock mode so this demo
> never touches real money, but the code path is identical to production."


> "And this is the part I actually care about most: every single payout
> attempt — approved, blocked, or duplicate-suppressed — gets written to
> an append-only audit log. Nothing here is a black box."

---

## 4:05 – 4:45 — Architecture


> "Zooming out: ingest, extract, match, score, autonomous payout, human
> review. The rule I followed building this — anything that's pure
> arithmetic, like 'does this amount match within two percent,' is
> deterministic Python. No LLM in that path at all. The LLM only ever
> touches the parts that are genuinely about reading messy documents. That
> split is what makes a ninety-five-percent confidence threshold something
> I'm actually willing to trust with a payout button."

---

## 4:45 – 5:00 — Close


> "This is a proof of concept today, but every piece here — the extraction
> schema, the matching rules, the confidence gate — is built to drop
> straight onto live RazorpayX credentials with one environment variable
> change. That's AutoReconcile AI."

