"""
main.py — AutoReconcile AI Backend (FastAPI)
================================================
Exposes the API consumed by the Next.js frontend. Run with:

    uvicorn main:app --reload --port 8000

Endpoints:
  GET  /api/health
  GET  /api/sample-invoices                 -> list bundled demo invoices
  POST /api/extract                          -> upload + extract a single invoice
  GET  /api/reconcile/run                    -> run full 3-way reconciliation over all sample invoices
  POST /api/payout/trigger                   -> manually trigger a mock payout for an exception item
  GET  /api/dashboard/metrics                -> aggregate KPIs for the Executive Dashboard
  GET  /api/audit-log                        -> raw payout audit log (JSONL) for the API Logs modal
"""
from __future__ import annotations

import os
import json
import shutil
from typing import List

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from models import PayoutRequest, ReconciliationResult, AnomalyFlag
from parser import extract_invoice
from matcher import reconcile_invoice
import razorpay_service

BASE_DIR = os.path.dirname(__file__)
SAMPLE_DATA_DIR = os.path.join(BASE_DIR, "..", "sample_data")
INVOICES_DIR = os.path.join(SAMPLE_DATA_DIR, "invoices")
RAZORPAY_LOG = os.path.join(SAMPLE_DATA_DIR, "razorpay_payouts_log.csv")
BANK_STATEMENT = os.path.join(SAMPLE_DATA_DIR, "bank_statement.csv")
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = FastAPI(title="AutoReconcile AI API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # demo-only; restrict in production (see ARCHITECTURE.md)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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


@app.post("/api/extract")
async def extract(file: UploadFile = File(...)):
    dest = os.path.join(UPLOAD_DIR, file.filename)
    with open(dest, "wb") as buf:
        shutil.copyfileobj(file.file, buf)
    try:
        result = extract_invoice(dest)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Extraction failed: {e}")
    return result.model_dump()


@app.get("/api/extract/sample/{filename}")
def extract_sample(filename: str):
    path = os.path.join(INVOICES_DIR, filename)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Sample invoice not found")
    result = extract_invoice(path)
    return result.model_dump()


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

        # Autonomous payout attempt for very high confidence, not-yet-processed items
        if result.status not in ("exception",) and result.confidence_score > razorpay_service.AUTO_PAYOUT_CONFIDENCE:
            try:
                payout_req = PayoutRequest(
                    invoice_number=result.invoice_number,
                    beneficiary_name=result.vendor_name or "Unknown Vendor",
                    account_number=result.razorpay_account_no or "",
                    ifsc="",
                    amount=result.razorpay_amount or 0.0,
                )
                razorpay_service.create_payout(payout_req, result.confidence_score)
            except (PermissionError, RuntimeError):
                pass  # already logged in payout_audit_log.jsonl
    return results


@app.get("/api/reconcile/run")
def run_reconciliation(refresh: bool = False):
    global _reconciliation_cache
    if _reconciliation_cache is None or refresh:
        _reconciliation_cache = _run_full_reconciliation()
    return [r.model_dump() for r in _reconciliation_cache]


@app.post("/api/payout/trigger")
def trigger_payout(record_id: str, override_confidence: float = 1.0):
    global _reconciliation_cache
    if _reconciliation_cache is None:
        _reconciliation_cache = _run_full_reconciliation()

    target = next((r for r in _reconciliation_cache if r.record_id == record_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="Reconciliation record not found")

    payout_req = PayoutRequest(
        invoice_number=target.invoice_number,
        beneficiary_name=target.vendor_name or "Unknown Vendor",
        account_number=target.invoice_account_no or "",
        ifsc="",
        amount=target.invoice_total or target.razorpay_amount or 0.0,
    )
    try:
        # Manual human-approved override: bypass the autonomous confidence
        # gate ONLY because a human explicitly clicked "Approve & Pay".
        response = razorpay_service.create_payout(payout_req, override_confidence)
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))

    target.status = "matched"
    target.payout_id = response.payout_id
    target.utr = response.utr
    target.recommended_action = "Manually approved and paid by reviewer."
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
    path = razorpay_service.AUDIT_LOG_PATH
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]
