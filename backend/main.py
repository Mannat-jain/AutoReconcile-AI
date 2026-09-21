"""
main.py - AutoReconcile AI Backend (FastAPI)
================================================
Exposes the API consumed by the Next.js frontend. Run with:

    uvicorn main:app --reload --port 8000

Endpoints:
  GET  /api/health
  GET  /api/sample-invoices                 -> list bundled demo invoices
  POST /api/extract                          -> upload (PDF only, <= 5 MB) + extract a single invoice
  GET  /api/reconcile/run                    -> run full 3-way reconciliation over all sample invoices
  POST /api/payout/trigger                   -> human approval of ONE payout (body: record_id, approved_by[, note])
  GET  /api/dashboard/metrics                -> aggregate KPIs for the Executive Dashboard
  GET  /api/audit-log                        -> payout audit log (hash-chained JSONL)
  GET  /api/audit-log/verify                 -> verify the audit log's hash chain (tamper check)
"""
from __future__ import annotations

import os
import re
import uuid
import json
from typing import List

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from models import PayoutRequest, ReconciliationResult, AnomalyFlag, ApprovalRequest
from parser import extract_invoice
from matcher import reconcile_invoice
import razorpay_service
from razorpay_service import DuplicatePayoutError

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SAMPLE_DATA_DIR = os.path.join(BASE_DIR, "..", "sample_data")
INVOICES_DIR = os.path.join(SAMPLE_DATA_DIR, "invoices")
RAZORPAY_LOG = os.path.join(SAMPLE_DATA_DIR, "razorpay_payouts_log.csv")
BANK_STATEMENT = os.path.join(SAMPLE_DATA_DIR, "bank_statement.csv")
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
# Anomalies that are classic fraud / double-payment signals: a human may still approve, but must justify it.
CRITICAL_ANOMALY_CODES = {"BANK_DETAILS_MISMATCH", "DUPLICATE_INVOICE_SUBMISSION", "DUPLICATE_PAYOUT_RECORD"}

app = FastAPI(title="AutoReconcile AI API", version="1.1.0")

ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,      # explicit origins only; set ALLOWED_ORIGINS for your deployed frontend
    allow_credentials=False,            # no cookies are used, so credentials are not needed
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

app.mount("/static/invoices", StaticFiles(directory=INVOICES_DIR), name="invoices")

_reconciliation_cache: List[ReconciliationResult] | None = None


@app.get("/api/health")
def health():
    return {"status": "ok", "mock_mode": razorpay_service.MOCK_MODE}


@app.get("/api/sample-invoices")
def list_sample_invoices():
    files = sorted(f for f in os.listdir(INVOICES_DIR) if f.lower().endswith(".pdf"))
    return [{"filename": f, "url": f"/static/invoices/{f}"} for f in files]


_UNSAFE_CHARS = re.compile(r"[^A-Za-z0-9._-]")


def _safe_upload_path(original_name: str | None) -> str:
    """Never trust a client-supplied filename: strip any directory part, whitelist characters and prefix a
    random id. (Using ``file.filename`` directly allowed ``../../x.pdf`` to write outside uploads/.)"""
    base = os.path.basename((original_name or "upload.pdf").replace("\\", "/"))
    safe = _UNSAFE_CHARS.sub("_", base)[:80].lstrip(".") or "upload.pdf"
    if not safe.lower().endswith(".pdf"):
        raise HTTPException(status_code=415, detail="Only .pdf files are accepted")
    return os.path.join(UPLOAD_DIR, f"{uuid.uuid4().hex[:8]}_{safe}")


@app.post("/api/extract")
async def extract(file: UploadFile = File(...)):
    dest = _safe_upload_path(file.filename)
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 5 MB)")
    if not data.startswith(b"%PDF-"):
        raise HTTPException(status_code=415, detail="File content is not a PDF")
    with open(dest, "wb") as buf:
        buf.write(data)
    try:
        result = extract_invoice(dest)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Extraction failed: {e}")
    return result.model_dump()


@app.get("/api/extract/sample/{filename}")
def extract_sample(filename: str):
    if os.path.basename(filename) != filename or not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Invalid file name")
    path = os.path.join(INVOICES_DIR, filename)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="Sample invoice not found")
    result = extract_invoice(path)
    return result.model_dump()


def _payout_request(target: ReconciliationResult, amount: float) -> PayoutRequest:
    return PayoutRequest(
        invoice_number=target.invoice_number,
        vendor_id=target.vendor_gstin or target.vendor_name,   # part of the idempotency key
        beneficiary_name=target.vendor_name or "Unknown Vendor",
        account_number=target.invoice_account_no or "",
        ifsc="",
        amount=amount,
    )


def _run_full_reconciliation() -> List[ReconciliationResult]:
    results: List[ReconciliationResult] = []
    seen_invoice_numbers = set()
    files = sorted(f for f in os.listdir(INVOICES_DIR) if f.lower().endswith(".pdf"))
    for fname in files:
        path = os.path.join(INVOICES_DIR, fname)
        extracted = extract_invoice(path)
        inv_no = extracted.invoice_number
        # We still reconcile every physical file (including the duplicate
        # submission) so the duplicate anomaly surfaces in the audit log,
        # but avoid double-counting dashboard metrics for the same invoice #.
        result = reconcile_invoice(extracted, RAZORPAY_LOG, BANK_STATEMENT)
        if inv_no in seen_invoice_numbers:
            result.anomalies.append(
                AnomalyFlag(
                    code="DUPLICATE_INVOICE_SUBMISSION",
                    severity="high",
                    message=f"Invoice {inv_no} was submitted more than once (file: {fname}).",
                )
            )
            result.status = "exception"
            result.recommended_action = "Routed to Exception Review Queue — duplicate invoice submission."
        else:
            seen_invoice_numbers.add(inv_no)
        results.append(result)

        # Autonomous payout ONLY for items the matcher marked "auto_paid": confidence > threshold AND the
        # payout is not yet settled. (Previously this also fired for already-settled "matched" invoices, i.e.
        # it re-paid invoices that had already been paid.)
        if result.status == "auto_paid":
            try:
                response = razorpay_service.create_payout(
                    _payout_request(result, result.razorpay_amount or 0.0), result.confidence_score
                )
                result.payout_id, result.utr = response.payout_id, response.utr
            except DuplicatePayoutError:
                result.recommended_action = "Payout already executed earlier (idempotent - no second payment)."
            except PermissionError:
                pass  # blocked by the confidence gate; already recorded in the audit log
    return results


@app.get("/api/reconcile/run")
def run_reconciliation(refresh: bool = False):
    global _reconciliation_cache
    if _reconciliation_cache is None or refresh:
        _reconciliation_cache = _run_full_reconciliation()
    return [r.model_dump() for r in _reconciliation_cache]


@app.post("/api/payout/trigger")
def trigger_payout(body: ApprovalRequest):
    """A human reviewer explicitly approves ONE payout.

    The confidence gate is enforced inside the payout layer and is not client-controllable: this endpoint
    can only get past it by identifying the approver (recorded in the audit log). Items that were already
    settled or auto-paid cannot be paid again, and high-risk anomalies require a written justification.
    """
    global _reconciliation_cache
    if _reconciliation_cache is None:
        _reconciliation_cache = _run_full_reconciliation()

    target = next((r for r in _reconciliation_cache if r.record_id == body.record_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="Reconciliation record not found")

    approver = body.approved_by.strip()
    if not approver:
        raise HTTPException(status_code=422, detail="approved_by must identify the reviewer")
    if target.status in ("matched", "auto_paid"):
        raise HTTPException(status_code=409, detail="Nothing to approve: this invoice is already settled/paid.")

    critical = sorted({a.code for a in target.anomalies} & CRITICAL_ANOMALY_CODES)
    if critical and len((body.note or "").strip()) < 10:
        raise HTTPException(
            status_code=422,
            detail=f"High-risk anomalies present ({', '.join(critical)}): a justification note (>= 10 characters) is required.",
        )

    razorpay_service.audit_log.append({
        "event": "HUMAN_APPROVAL",
        "record_id": target.record_id,
        "invoice_number": target.invoice_number,
        "approved_by": approver,
        "note": (body.note or "").strip() or None,
        "confidence_score": target.confidence_score,
        "anomalies": [a.code for a in target.anomalies],
    })
    try:
        response = razorpay_service.create_payout(
            _payout_request(target, target.invoice_total or target.razorpay_amount or 0.0),
            target.confidence_score,
            approved_by=approver,
        )
    except DuplicatePayoutError as e:
        raise HTTPException(status_code=409, detail=str(e))

    target.status = "matched"
    target.payout_id = response.payout_id
    target.utr = response.utr
    target.recommended_action = f"Manually approved and paid by {approver}."
    return response.model_dump()


@app.get("/api/dashboard/metrics")
def dashboard_metrics():
    global _reconciliation_cache
    if _reconciliation_cache is None:
        _reconciliation_cache = _run_full_reconciliation()

    results = _reconciliation_cache
    total_amount = sum(r.invoice_total or 0 for r in results)
    matched = [r for r in results if r.status in ("matched", "auto_paid")]
    flagged = [r for r in results if r.status == "flagged"]
    exceptions = [r for r in results if r.status == "exception"]
    auto_paid = [r for r in results if r.status == "auto_paid"]

    discrepancy_rate = round(
        (len(flagged) + len(exceptions)) / len(results) * 100, 1
    ) if results else 0.0

    # Time-saved heuristic: 12 minutes of manual reconciliation avoided per
    # item that didn't need a full manual review (matched or auto-paid).
    minutes_saved = (len(matched) + len(auto_paid)) * 12

    return {
        "total_invoices": len(results),
        "total_reconciled_amount": round(total_amount, 2),
        "matched_count": len(matched),
        "flagged_count": len(flagged),
        "exception_count": len(exceptions),
        "auto_paid_count": len(auto_paid),
        "discrepancy_rate_pct": discrepancy_rate,
        "time_saved_minutes": minutes_saved,
        "avg_confidence": round(sum(r.confidence_score for r in results) / len(results), 3) if results else 0,
        "status_breakdown": [
            {"status": "matched", "count": len(matched)},
            {"status": "flagged", "count": len(flagged)},
            {"status": "exception", "count": len(exceptions)},
            {"status": "auto_paid", "count": len(auto_paid)},
        ],
    }


@app.get("/api/audit-log")
def audit_log():
    return razorpay_service.audit_log.read_all()


@app.get("/api/audit-log/verify")
def verify_audit_log():
    result = razorpay_service.audit_log.verify()
    return {"valid": result.valid, "entries": result.entries, "broken_at": result.broken_at, "reason": result.reason}
