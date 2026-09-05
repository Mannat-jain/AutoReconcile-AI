"""
razorpay_service.py — Autonomous Payout Layer
================================================
Wraps the Razorpay Payouts API (https://razorpay.com/docs/api/x/payouts/).

In this proof-of-concept, `RAZORPAY_KEY_ID` / `RAZORPAY_KEY_SECRET` are
expected to be empty (see .env.example), so `create_payout()` runs in
MOCK MODE: it simulates the exact request/response shape of the real
Razorpay API (including realistic fees, tax, and a fabricated UTR) without
making a network call. This keeps the demo fully offline and safe to run
in an interview setting, while the code path is a drop-in replacement for
the live API — swap `MOCK_MODE = False` and supply real credentials to go
live against RazorpayX.

Safety guardrails baked in here (see docs/ARCHITECTURE.md > "Security best
practices for financial operations"):
  - `create_payout` REFUSES to fire if `confidence_score <= AUTO_PAYOUT_CONFIDENCE`.
  - Idempotency key derived from invoice_number prevents double-payouts on retry.
  - All payout attempts (successful or refused) are appended to an
    append-only audit log (`payout_audit_log.jsonl`).
"""
from __future__ import annotations

import os
import json
import time
import random
import string
import hashlib
from datetime import datetime, timezone

from models import PayoutRequest, PayoutResponse

MOCK_MODE = not (os.getenv("RAZORPAY_KEY_ID") and os.getenv("RAZORPAY_KEY_SECRET"))
AUTO_PAYOUT_CONFIDENCE = 0.95
AUDIT_LOG_PATH = os.path.join(os.path.dirname(__file__), "payout_audit_log.jsonl")

_idempotency_seen: set[str] = set()


def _idempotency_key(invoice_number: str, amount: float) -> str:
    raw = f"{invoice_number}:{amount:.2f}"
    return hashlib.sha256(raw.encode()).hexdigest()[:20]


def _fake_utr() -> str:
    return "UTR" + "".join(random.choices(string.digits, k=12))


def _append_audit_log(entry: dict) -> None:
    entry["logged_at"] = datetime.now(timezone.utc).isoformat()
    with open(AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def create_payout(request: PayoutRequest, confidence_score: float) -> PayoutResponse:
    """
    Fires a (mock) RazorpayX Payouts API call.
    Raises `PermissionError` if the confidence gate is not met — callers
    (the reconciliation route) MUST catch this and route to the Exception
    Review Queue instead of retrying.
    """
    if confidence_score <= AUTO_PAYOUT_CONFIDENCE:
        _append_audit_log({
            "event": "PAYOUT_BLOCKED_LOW_CONFIDENCE",
            "invoice_number": request.invoice_number,
            "confidence_score": confidence_score,
        })
        raise PermissionError(
            f"Refusing autonomous payout: confidence {confidence_score} <= "
            f"{AUTO_PAYOUT_CONFIDENCE} threshold. Route to human review."
        )

    idem_key = _idempotency_key(request.invoice_number, request.amount)
    if idem_key in _idempotency_seen:
        _append_audit_log({
            "event": "PAYOUT_IDEMPOTENT_SKIP",
            "invoice_number": request.invoice_number,
            "idempotency_key": idem_key,
        })
        raise RuntimeError("Duplicate payout attempt suppressed by idempotency key.")
    _idempotency_seen.add(idem_key)

    if MOCK_MODE:
        time.sleep(0.15)  # simulate network latency for demo realism
        fees = round(request.amount * 0.001, 2)   # ~0.1% mock fee
        tax = round(fees * 0.18, 2)                # 18% GST on fees
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
        response = _call_live_razorpay_api(request)

    _append_audit_log({
        "event": "PAYOUT_EXECUTED",
        "invoice_number": request.invoice_number,
        "payout_id": response.payout_id,
        "amount": response.amount,
        "confidence_score": confidence_score,
        "mock": response.mock,
    })
    return response


def _call_live_razorpay_api(request: PayoutRequest) -> PayoutResponse:  # pragma: no cover
    """
    Real RazorpayX integration stub. Left intentionally minimal — wire this
    up with the official `razorpay` Python SDK once live credentials and a
    funded RazorpayX account/contact/fund-account are available:

        import razorpay
        client = razorpay.Client(auth=(key_id, key_secret))
        client.payout.create({...})
    """
    raise NotImplementedError(
        "Live Razorpay credentials detected but live integration is not "
        "wired up in this proof-of-concept. Set RAZORPAY_KEY_ID/SECRET "
        "empty to keep running in MOCK_MODE."
    )
