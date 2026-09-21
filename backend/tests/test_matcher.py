import csv
import os

import matcher
from matcher import reconcile_invoice
from models import ExtractedInvoice

RP_HEADER = ["payout_id", "invoice_ref", "beneficiary_name", "account_no", "ifsc", "amount", "currency", "status", "utr", "created_at"]
BANK_HEADER = ["txn_id", "value_date", "narration", "debit_amount", "credit_amount", "closing_balance", "utr_ref"]


def _csv(path, header, rows):
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh); w.writerow(header); w.writerows(rows)
    return str(path)


def _invoice(total=1000.0, **kw):
    data = dict(source_file="x.pdf", invoice_number="INV-9", vendor_name="Acme Pvt Ltd", total_payable=total,
                account_number="111", ifsc="X", extraction_confidence=1.0)
    data.update(kw)
    return ExtractedInvoice(**data)


def _run(tmp_path, rp_rows, bank_rows=(), **inv):
    rp = _csv(tmp_path / "rp.csv", RP_HEADER, rp_rows)
    bank = _csv(tmp_path / "bank.csv", BANK_HEADER, bank_rows)
    return reconcile_invoice(_invoice(**inv), rp, bank)


def test_settled_payout_with_bank_debit_is_matched_not_auto_paid(tmp_path):
    r = _run(tmp_path,
             [["p1", "INV-9", "Acme Pvt Ltd", "111", "X", "1000.00", "INR", "processed", "UTR1", "t"]],
             [["t1", "d", "n", "1000.00", "", "0", "UTR1"]])
    assert r.status == "matched" and r.confidence_score > 0.95       # already paid -> never pay again


def test_queued_payout_without_bank_line_is_auto_paid(tmp_path):
    r = _run(tmp_path, [["p1", "INV-9", "Acme Pvt Ltd", "111", "X", "1000.00", "INR", "queued", "", "t"]])
    assert r.status == "auto_paid" and r.confidence_score > 0.95


def test_settled_payout_without_bank_line_is_penalised(tmp_path):
    r = _run(tmp_path, [["p1", "INV-9", "Acme Pvt Ltd", "111", "X", "1000.00", "INR", "processed", "UTR1", "t"]])
    assert "NO_BANK_CONFIRMATION" in [a.code for a in r.anomalies]
    assert r.status != "auto_paid"


def test_amount_difference_above_tolerance_is_flagged(tmp_path):
    r = _run(tmp_path, [["p1", "INV-9", "Acme Pvt Ltd", "111", "X", "1020.00", "INR", "queued", "", "t"]])   # 2% off
    assert "AMOUNT_MISMATCH" in [a.code for a in r.anomalies]
    assert r.status != "auto_paid"


def test_tolerance_is_configurable(tmp_path, monkeypatch):
    from decimal import Decimal
    monkeypatch.setattr(matcher, "AMOUNT_TOLERANCE", Decimal("0.05"))
    r = _run(tmp_path, [["p1", "INV-9", "Acme Pvt Ltd", "111", "X", "1020.00", "INR", "queued", "", "t"]])
    assert "AMOUNT_MISMATCH" not in [a.code for a in r.anomalies]


def test_decimal_comparison_is_not_fooled_by_float_noise(tmp_path):
    # 0.1 + 0.2 != 0.3 in binary floating point; the matcher must still treat them as equal amounts.
    r = _run(tmp_path, [["p1", "INV-9", "Acme Pvt Ltd", "111", "X", "0.30", "INR", "queued", "", "t"]], total=0.1 + 0.2)
    assert "AMOUNT_MISMATCH" not in [a.code for a in r.anomalies]


def test_duplicate_payout_records_force_review(tmp_path):
    row = ["p1", "INV-9", "Acme Pvt Ltd", "111", "X", "1000.00", "INR", "processed", "UTR1", "t"]
    r = _run(tmp_path, [row, ["p2"] + row[1:]], [["t1", "d", "n", "1000.00", "", "0", "UTR1"]])
    assert "DUPLICATE_PAYOUT_RECORD" in [a.code for a in r.anomalies]
    assert r.status == "exception"


def test_missing_razorpay_record_is_an_exception(tmp_path):
    r = _run(tmp_path, [])
    assert r.status == "exception" and "NO_RAZORPAY_RECORD" in [a.code for a in r.anomalies]
