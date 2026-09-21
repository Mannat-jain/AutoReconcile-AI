"""
models.py
Pydantic schemas shared across the AutoReconcile AI backend.
These enforce structured JSON output at every stage of the pipeline —
from LLM/OCR extraction through to reconciliation results — so that
downstream consumers (matcher, payout service, frontend) can rely on a
strict, typed contract instead of parsing free-form text.
"""
from __future__ import annotations
from typing import List, Optional, Literal
from pydantic import BaseModel, Field


class LineItem(BaseModel):
    description: str
    quantity: float
    unit_price: float
    amount: float


class ExtractedInvoice(BaseModel):
    """Structured output of the LLM / OCR extraction stage."""
    source_file: str
    vendor_name: Optional[str] = None
    gstin: Optional[str] = None
    invoice_number: Optional[str] = None
    invoice_date: Optional[str] = None
    due_date: Optional[str] = None
    bill_to: Optional[str] = None
    bank_name: Optional[str] = None
    account_number: Optional[str] = None
    ifsc: Optional[str] = None
    line_items: List[LineItem] = Field(default_factory=list)
    subtotal: Optional[float] = None
    gst_amount: Optional[float] = None
    tds_amount: Optional[float] = None
    total_payable: Optional[float] = None
    extraction_confidence: float = 0.0
    raw_text_snippet: Optional[str] = None


class AnomalyFlag(BaseModel):
    code: str
    severity: Literal["low", "medium", "high"]
    message: str


class ReconciliationResult(BaseModel):
    record_id: str            # unique per physical file — invoice_number alone
                               # is NOT guaranteed unique (that's the point of
                               # the duplicate-submission scenario), so every
                               # row the frontend renders keys off this instead.
    source_file: str
    invoice_number: str
    vendor_name: Optional[str]
    vendor_gstin: Optional[str] = None     # vendor identity used in the payout idempotency key
    invoice_total: Optional[float]
    razorpay_amount: Optional[float]
    bank_amount: Optional[float]
    invoice_account_no: Optional[str]
    razorpay_account_no: Optional[str]
    confidence_score: float
    status: Literal["matched", "flagged", "exception", "auto_paid"]
    anomalies: List[AnomalyFlag] = Field(default_factory=list)
    payout_id: Optional[str] = None
    utr: Optional[str] = None
    recommended_action: str


class PayoutRequest(BaseModel):
    invoice_number: str
    vendor_id: Optional[str] = None       # GSTIN (preferred) or vendor name - part of the idempotency key
    currency: str = "INR"
    beneficiary_name: str
    account_number: str
    ifsc: str
    amount: float
    mode: Literal["IMPS", "NEFT", "RTGS", "UPI"] = "IMPS"
    purpose: str = "vendor payment"


class PayoutResponse(BaseModel):
    payout_id: str
    status: Literal["queued", "processing", "processed", "failed"]
    utr: Optional[str] = None
    mode: str
    amount: float
    fees: float
    tax: float
    mock: bool = True


class ApprovalRequest(BaseModel):
    """Body of POST /api/payout/trigger - a human reviewer explicitly approving one payout."""
    record_id: str
    approved_by: str = Field(min_length=1, max_length=100)
    note: Optional[str] = Field(default=None, max_length=500)
