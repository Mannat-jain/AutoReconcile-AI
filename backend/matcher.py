"""
matcher.py — Structured Ledger & Bank Matching + Anomaly Detection
=====================================================================
Performs a 3-way match between:
  1. Extracted Invoice (from parser.py)
  2. Razorpay Payout/Settlement Log (CSV)
  3. Bank Statement (CSV)

Matching strategy is intentionally a HYBRID of deterministic rules and
fuzzy scoring rather than "ask an LLM to decide everything":

  - Deterministic guardrails (exact/near-exact key matching: invoice
    number, amounts within tolerance, account number/IFSC equality)
    are cheap, auditable, and 100% reproducible — they do the heavy
    lifting.
  - Fuzzy matching (`rapidfuzz`) is used ONLY for vendor/beneficiary
    NAME matching, since the same entity is rendered differently across
    systems ("CloudNine Hosting Pvt Ltd" vs "CloudNine Hosting Pvt. Ltd.").
  - An LLM reasoning pass is reserved for cases with genuine ambiguity
    (see `llm_reason_over_exception` — only invoked for borderline
    confidence bands, never for the initial pass) to keep the pipeline
    fast, cheap, and deterministic wherever possible.

See docs/ARCHITECTURE.md for the full guardrail/anomaly rulebook.
"""
from __future__ import annotations

import os
import csv
from dataclasses import dataclass, field
from typing import Optional

from rapidfuzz import fuzz

from models import ExtractedInvoice, ReconciliationResult, AnomalyFlag

AMOUNT_TOLERANCE = 0.02          # 2% tolerance before flagging a price mismatch
NAME_FUZZY_THRESHOLD = 80        # rapidfuzz token_sort_ratio threshold
AUTO_PAYOUT_CONFIDENCE = 0.95    # >0.95 triggers autonomous payout


def load_csv(path: str) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _find_razorpay_records(invoice_number: str, rp_rows: list[dict]) -> list[dict]:
    return [r for r in rp_rows if r.get("invoice_ref") == invoice_number]


def _find_bank_record(utr: Optional[str], bank_rows: list[dict]) -> Optional[dict]:
    if not utr:
        return None
    for r in bank_rows:
        if r.get("utr_ref") == utr:
            return r
    return None


def _name_similarity(a: Optional[str], b: Optional[str]) -> float:
    if not a or not b:
        return 0.0
    return fuzz.token_sort_ratio(a.lower(), b.lower()) / 100.0


def reconcile_invoice(
    invoice: ExtractedInvoice,
    razorpay_log_path: str,
    bank_statement_path: str,
) -> ReconciliationResult:
    rp_rows = load_csv(razorpay_log_path)
    bank_rows = load_csv(bank_statement_path)

    anomalies: list[AnomalyFlag] = []
    invoice_no = invoice.invoice_number or "UNKNOWN"

    matches = _find_razorpay_records(invoice_no, rp_rows)

    if not matches:
        anomalies.append(AnomalyFlag(
            code="NO_RAZORPAY_RECORD",
            severity="high",
            message=f"No Razorpay payout/settlement record found for invoice {invoice_no}.",
        ))
        return ReconciliationResult(
            record_id=invoice.source_file,
            source_file=invoice.source_file,
            invoice_number=invoice_no,
            vendor_name=invoice.vendor_name,
            invoice_total=invoice.total_payable,
            razorpay_amount=None,
            bank_amount=None,
            invoice_account_no=invoice.account_number,
            razorpay_account_no=None,
            confidence_score=0.15,
            status="exception",
            anomalies=anomalies,
            recommended_action="Route to Exception Review Queue — no matching Razorpay record.",
        )

    # --- Duplicate detection: more than one settlement record for the same invoice ---
    if len(matches) > 1:
        anomalies.append(AnomalyFlag(
            code="DUPLICATE_PAYOUT_RECORD",
            severity="high",
            message=(
                f"{len(matches)} Razorpay payout entries reference invoice {invoice_no} "
                f"(payout IDs: {', '.join(m['payout_id'] for m in matches)}). "
                f"Possible duplicate submission/log entry."
            ),
        ))

    primary = matches[0]
    razorpay_amount = float(primary["amount"])
    bank_record = _find_bank_record(primary.get("utr"), bank_rows)
    bank_amount = float(bank_record["debit_amount"]) if bank_record and bank_record.get("debit_amount") else None

    # --- Name similarity (fuzzy) ---
    name_score = _name_similarity(invoice.vendor_name, primary.get("beneficiary_name"))
    if name_score < NAME_FUZZY_THRESHOLD / 100.0:
        anomalies.append(AnomalyFlag(
            code="VENDOR_NAME_MISMATCH",
            severity="medium",
            message=(
                f"Vendor name on invoice ('{invoice.vendor_name}') only "
                f"{name_score*100:.0f}% similar to Razorpay beneficiary "
                f"('{primary.get('beneficiary_name')}')."
            ),
        ))

    # --- Bank account / IFSC mismatch (deterministic, exact match required) ---
    account_match = (invoice.account_number == primary.get("account_no"))
    ifsc_match = (invoice.ifsc == primary.get("ifsc"))
    if not account_match or not ifsc_match:
        anomalies.append(AnomalyFlag(
            code="BANK_DETAILS_MISMATCH",
            severity="high",
            message=(
                f"Invoice bank details (A/C {invoice.account_number}, IFSC {invoice.ifsc}) "
                f"do not match Razorpay beneficiary on record "
                f"(A/C {primary.get('account_no')}, IFSC {primary.get('ifsc')}). "
                f"Possible fraud risk or outdated vendor banking info."
            ),
        ))

    # --- Amount comparison: invoice vs Razorpay log ---
    invoice_total = invoice.total_payable or 0.0
    amount_diff_ratio = (
        abs(invoice_total - razorpay_amount) / invoice_total if invoice_total else 1.0
    )

    if amount_diff_ratio > AMOUNT_TOLERANCE:
        # Special-case: could be an undisclosed TDS deduction rather than a
        # genuine price mismatch. Detect the pattern: razorpay_amount is
        # ~ (invoice_total * (1 - common TDS rates)).
        tds_explained = False
        for tds_rate in (0.10, 0.02, 0.01, 0.05):
            expected_net = invoice_total * (1 - tds_rate)
            if abs(expected_net - razorpay_amount) / expected_net < AMOUNT_TOLERANCE:
                anomalies.append(AnomalyFlag(
                    code="MISSING_TDS_ON_INVOICE",
                    severity="medium",
                    message=(
                        f"Invoice does not show a TDS deduction, but the settled amount "
                        f"(₹{razorpay_amount:,.2f}) matches invoice total minus "
                        f"{int(tds_rate*100)}% TDS (expected ₹{expected_net:,.2f}). "
                        f"Vendor invoice should be reissued reflecting TDS u/s 194J/194C."
                    ),
                ))
                tds_explained = True
                break
        if not tds_explained:
            anomalies.append(AnomalyFlag(
                code="AMOUNT_MISMATCH",
                severity="high",
                message=(
                    f"Invoice total (₹{invoice_total:,.2f}) differs from Razorpay "
                    f"settlement amount (₹{razorpay_amount:,.2f}) by "
                    f"{amount_diff_ratio*100:.1f}%, exceeding the {AMOUNT_TOLERANCE*100:.0f}% tolerance."
                ),
            ))

    # --- Amount comparison: Razorpay log vs actual Bank debit ---
    if bank_amount is not None and abs(bank_amount - razorpay_amount) > 0.01:
        anomalies.append(AnomalyFlag(
            code="BANK_RAZORPAY_AMOUNT_MISMATCH",
            severity="high",
            message=(
                f"Bank statement shows ₹{bank_amount:,.2f} debited but Razorpay log "
                f"records ₹{razorpay_amount:,.2f} for this payout."
            ),
        ))
    elif bank_amount is None:
        anomalies.append(AnomalyFlag(
            code="NO_BANK_CONFIRMATION",
            severity="medium",
            message="No corresponding debit found in the bank statement for this payout's UTR.",
        ))

    # --- Confidence scoring ---
    confidence = _compute_confidence(anomalies, name_score, invoice.extraction_confidence)

    if confidence > AUTO_PAYOUT_CONFIDENCE and primary.get("status") != "processed":
        status = "auto_paid"
        action = "Auto-payout triggered via Razorpay Payouts API (confidence > 0.95)."
    elif confidence > AUTO_PAYOUT_CONFIDENCE:
        status = "matched"
        action = "Clean 3-way match. Already settled — no action required."
    elif any(a.severity == "high" for a in anomalies):
        status = "exception"
        action = "Routed to Exception Review Queue for manual approval."
    else:
        status = "flagged"
        action = "Flagged for quick human review (medium-confidence anomaly)."

    return ReconciliationResult(
        record_id=invoice.source_file,
        source_file=invoice.source_file,
        invoice_number=invoice_no,
        vendor_name=invoice.vendor_name,
        invoice_total=invoice.total_payable,
        razorpay_amount=razorpay_amount,
        bank_amount=bank_amount,
        invoice_account_no=invoice.account_number,
        razorpay_account_no=primary.get("account_no"),
        confidence_score=confidence,
        status=status,
        anomalies=anomalies,
        payout_id=primary.get("payout_id"),
        utr=primary.get("utr"),
        recommended_action=action,
    )


def _compute_confidence(anomalies: list[AnomalyFlag], name_score: float, extraction_confidence: float) -> float:
    """
    Deterministic, auditable confidence scoring (NOT an LLM black box —
    see ARCHITECTURE.md "Deterministic Guardrails vs LLM Fuzzy Matching").
    Starts at a base derived from extraction quality + name similarity,
    then subtracts fixed penalties per anomaly severity.
    """
    base = 0.5 * extraction_confidence + 0.5 * name_score
    penalty = 0.0
    for a in anomalies:
        penalty += {"low": 0.05, "medium": 0.15, "high": 0.35}[a.severity]
    score = max(0.0, min(1.0, base - penalty))
    return round(score, 3)


def llm_reason_over_exception(result: ReconciliationResult) -> str:
    """
    Optional secondary pass: for borderline exceptions, an LLM can be asked
    to draft a plain-English recommendation for the human reviewer,
    summarizing the anomalies. This is advisory text only — it never
    changes the deterministic confidence_score or status computed above.
    Stubbed here to keep the offline demo dependency-free.
    """
    lines = [f"- [{a.severity.upper()}] {a.message}" for a in result.anomalies]
    return (
        f"Review needed for {result.invoice_number} ({result.vendor_name}): \n"
        + "\n".join(lines)
    )
