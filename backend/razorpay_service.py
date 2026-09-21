"""
razorpay_service.py - Autonomous Payout Layer
================================================
Wraps the Razorpay Payouts API (https://razorpay.com/docs/api/x/payouts/).

In this proof-of-concept `RAZORPAY_KEY_ID` / `RAZORPAY_KEY_SECRET` are expected to be empty (see
.env.example), so `create_payout()` runs in MOCK MODE: it simulates the request/response shape of the
real API (fees, tax, a fabricated UTR) without a network call. Swap in real credentials and implement
`_call_live_razorpay_api` to go live.

Safety guarantees enforced HERE, in the payout layer itself (so no caller can skip them):

1. Confidence gate  - an autonomous payout (no human) is refused unless confidence > 0.95. The ONLY way
   past the gate is an explicit human approval, which must carry the approver's identity
   (``approved_by``); it is recorded in the audit log. The confidence value is never taken from a client.
2. Idempotency      - the key is SHA-256 over (vendor id, invoice number, amount, currency) and is claimed
   in a durable ledger with an atomic INSERT (see payout_store.py): retries, double clicks, duplicate
   uploads and server restarts cannot produce a second payout, and a FAILED attempt can be retried.
3. Audit trail      - every outcome (executed / blocked / duplicate / failed) is appended to a
   hash-chained, append-only log (see audit.py).
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import string
import time
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from audit import AuditLog
from models import PayoutRequest, PayoutResponse
from payout_store import PayoutLedger

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

MOCK_MODE = not (os.getenv("RAZORPAY_KEY_ID") and os.getenv("RAZORPAY_KEY_SECRET"))
AUTO_PAYOUT_CONFIDENCE = float(os.getenv("AUTO_PAYOUT_CONFIDENCE", "0.95"))
MOCK_LATENCY_SECONDS = float(os.getenv("MOCK_LATENCY_SECONDS", "0.15"))

AUDIT_LOG_PATH = os.getenv("AUDIT_LOG_PATH", os.path.join(BASE_DIR, "data", "payout_audit_log.jsonl"))
PAYOUT_DB_PATH = os.getenv("PAYOUT_DB_PATH", os.path.join(BASE_DIR, "data", "payouts.db"))

audit_log = AuditLog(AUDIT_LOG_PATH)
ledger = PayoutLedger(PAYOUT_DB_PATH)


class DuplicatePayoutError(RuntimeError):
    """The same payout (same vendor + invoice + amount + currency) was already made or is in flight."""

    def __init__(self, message: str, status: str, payout_id: Optional[str] = None) -> None:
        super().__init__(message)
        self.status = status
        self.payout_id = payout_id


def configure(audit_path: Optional[str] = None, db_path: Optional[str] = None) -> None:
    """Re-point the audit log / ledger (used by tests)."""
    global audit_log, ledger
    if audit_path:
        audit_log = AuditLog(audit_path)
    if db_path:
        ledger = PayoutLedger(db_path)


def _amount_str(amount: float) -> str:
    return str(Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def idempotency_key(vendor_id: Optional[str], invoice_number: str, amount: float, currency: str = "INR") -> str:
    """Deterministic key: the same business payout always maps to the same key.

    The vendor is part of the key because invoice numbers are only unique *per vendor* - two vendors can
    both send "INV-100" for the same amount and both must be paid. Fields are joined in a canonical
    JSON form (sorted keys, normalised amount/case/whitespace) so formatting differences cannot change the hash.
    """
    canonical = json.dumps(
        {
            "vendor": (vendor_id or "").strip().upper(),
            "invoice": invoice_number.strip().upper(),
            "amount": _amount_str(amount),
            "currency": currency.strip().upper(),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _fake_utr() -> str:
    return "UTR" + "".join(random.choices(string.digits, k=12))


def create_payout(
    request: PayoutRequest,
    confidence_score: float,
    *,
    approved_by: Optional[str] = None,
) -> PayoutResponse:
    """
    Execute a (mock) RazorpayX payout.

    * Autonomous path (``approved_by`` is None): requires ``confidence_score > AUTO_PAYOUT_CONFIDENCE``,
      otherwise raises ``PermissionError`` (callers route the item to human review).
    * Human-approved path: pass the reviewer's identity in ``approved_by``; it is written to the audit log.

    Raises ``DuplicatePayoutError`` if this payout was already made / is in flight.
    """
    approver = (approved_by or "").strip() or None
    key = idempotency_key(request.vendor_id, request.invoice_number, request.amount, request.currency)

    if approver is None and confidence_score <= AUTO_PAYOUT_CONFIDENCE:
        audit_log.append({
            "event": "PAYOUT_BLOCKED_LOW_CONFIDENCE",
            "invoice_number": request.invoice_number,
            "confidence_score": confidence_score,
            "idempotency_key": key,
        })
        raise PermissionError(
            f"Refusing autonomous payout: confidence {confidence_score} <= {AUTO_PAYOUT_CONFIDENCE} threshold. "
            f"Route to human review."
        )

    claim = ledger.claim(key, request.invoice_number, _amount_str(request.amount))
    if not claim.acquired:
        audit_log.append({
            "event": "PAYOUT_IDEMPOTENT_SKIP",
            "invoice_number": request.invoice_number,
            "idempotency_key": key,
            "existing_status": claim.status,
            "existing_payout_id": claim.payout_id,
        })
        raise DuplicatePayoutError(
            f"Duplicate payout suppressed by idempotency key (existing payout status: {claim.status}).",
            claim.status,
            claim.payout_id,
        )

    try:
        if MOCK_MODE:
            time.sleep(MOCK_LATENCY_SECONDS)                 # simulate network latency for demo realism
            fees = round(request.amount * 0.001, 2)          # ~0.1% mock fee
            tax = round(fees * 0.18, 2)                      # 18% GST on fees
            response = PayoutResponse(
                payout_id=f"pout_MOCK{random.randint(100000, 999999)}",
                status="processed",
                utr=_fake_utr(),
                mode=request.mode,
                amount=request.amount,
                fees=fees,
                tax=tax,
                mock=True,
            )
        else:
            # Pass `key` to the gateway as its own idempotency header so a retried HTTP call is safe end to end.
            response = _call_live_razorpay_api(request, key)
    except Exception as exc:
        ledger.fail(key, repr(exc))                          # release the key so the payout can be retried
        audit_log.append({
            "event": "PAYOUT_FAILED",
            "invoice_number": request.invoice_number,
            "idempotency_key": key,
            "error": repr(exc)[:300],
        })
        raise

    ledger.complete(key, response.payout_id, response.utr)
    audit_log.append({
        "event": "PAYOUT_EXECUTED",
        "invoice_number": request.invoice_number,
        "payout_id": response.payout_id,
        "amount": response.amount,
        "confidence_score": confidence_score,
        "approved_by": approver,                             # None => autonomous (confidence-gated)
        "idempotency_key": key,
        "mock": response.mock,
    })
    return response


def _call_live_razorpay_api(request: PayoutRequest, idempotency_key_value: str) -> PayoutResponse:  # pragma: no cover
    """
    Real RazorpayX integration stub - wire up with the official `razorpay` SDK once live credentials and a
    funded RazorpayX account/contact/fund-account exist:

        client = razorpay.Client(auth=(key_id, key_secret))
        client.payout.create({...}, headers={"X-Payout-Idempotency": idempotency_key_value})
    """
    raise NotImplementedError(
        "Live Razorpay credentials detected but the live integration is not wired up in this proof-of-concept. "
        "Leave RAZORPAY_KEY_ID/SECRET empty to keep running in MOCK_MODE."
    )
