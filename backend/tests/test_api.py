import io

import razorpay_service as rs


def _by_file(client, prefix):
    return next(r for r in client.get("/api/reconcile/run").json() if r["source_file"].startswith(prefix))


def _executed(invoice_number=None):
    rows = [e for e in rs.audit_log.read_all() if e["event"] == "PAYOUT_EXECUTED"]
    return [e for e in rows if invoice_number in (None, e["invoice_number"])]


# ------------------------------------------------------------ reconciliation + autonomous payout
def test_already_settled_invoice_is_never_paid_again(client):
    """Regression: INV-1001 was already settled but the old code executed a second payout for it."""
    assert _by_file(client, "INV-1001")["status"] == "matched"
    assert _executed("INV-1001") == []


def test_clean_pending_invoice_is_auto_paid_exactly_once(client):
    r = _by_file(client, "INV-1006")
    assert r["status"] == "auto_paid" and r["confidence_score"] > 0.95 and r["payout_id"].startswith("pout_MOCK")
    client.get("/api/reconcile/run?refresh=true")
    client.get("/api/reconcile/run?refresh=true")
    assert len(_executed("INV-1006")) == 1                       # idempotent across re-runs


def test_only_the_clean_pending_invoice_is_paid_autonomously(client):
    client.get("/api/reconcile/run")
    assert [e["invoice_number"] for e in _executed()] == ["INV-1006"]


def test_dashboard_counts_the_auto_paid_invoice(client):
    m = client.get("/api/dashboard/metrics").json()
    assert m["auto_paid_count"] == 1 and m["total_invoices"] == 7


def test_audit_chain_is_valid_after_activity(client):
    client.get("/api/reconcile/run")
    v = client.get("/api/audit-log/verify").json()
    assert v["valid"] and v["entries"] >= 1


# ------------------------------------------------------------ human approval endpoint
def _approve(client, record_id, **body):
    return client.post("/api/payout/trigger", json={"record_id": record_id, **body})


def test_confidence_cannot_be_supplied_by_the_client(client):
    """Regression: `override_confidence` (default 1.0) let anyone bypass the 0.95 gate."""
    client.get("/api/reconcile/run")
    rid = "INV-1002_Bright_Ads_Media.pdf"
    r = client.post(f"/api/payout/trigger?override_confidence=1.0", json={"record_id": rid})
    assert r.status_code == 422                                   # approver is mandatory
    assert _executed("INV-1002") == []


def test_approval_requires_an_identified_reviewer(client):
    client.get("/api/reconcile/run")
    assert _approve(client, "INV-1002_Bright_Ads_Media.pdf", approved_by="  ").status_code == 422


def test_unknown_record_is_404(client):
    assert _approve(client, "nope.pdf", approved_by="asha").status_code == 404


def test_settled_invoice_cannot_be_approved_for_payment(client):
    r = _approve(client, "INV-1001_CloudNine_Hosting.pdf", approved_by="asha")
    assert r.status_code == 409


def test_high_risk_anomaly_needs_a_written_justification(client):
    rid = "INV-1005_Velocity_Logistics.pdf"                      # BANK_DETAILS_MISMATCH
    assert _approve(client, rid, approved_by="asha").status_code == 422
    assert _approve(client, rid, approved_by="asha", note="ok").status_code == 422        # too short
    assert _executed("INV-1005") == []


def test_valid_human_approval_pays_once_and_is_attributed(client):
    rid = "INV-1003_Sharma_Consulting.pdf"                       # medium anomaly (TDS) -> flagged
    r = _approve(client, rid, approved_by="asha@finance", note="TDS confirmed with vendor")
    assert r.status_code == 200 and r.json()["status"] == "processed"
    approvals = [e for e in rs.audit_log.read_all() if e["event"] == "HUMAN_APPROVAL"]
    assert approvals and approvals[-1]["approved_by"] == "asha@finance"
    assert _executed("INV-1003")[0]["approved_by"] == "asha@finance"
    assert _approve(client, rid, approved_by="asha@finance").status_code == 409           # already paid


# ------------------------------------------------------------ upload hardening
def test_upload_filename_cannot_escape_the_upload_dir(client, uploads_dir, tmp_path):
    """Regression: `../PWNED.pdf` was written outside uploads/."""
    files = {"file": ("../../PWNED.pdf", io.BytesIO(b"%PDF-1.4 not a real invoice"), "application/pdf")}
    client.post("/api/extract", files=files)                      # extraction itself may fail (422) - irrelevant
    assert not (tmp_path / "PWNED.pdf").exists() and not (uploads_dir.parent.parent / "PWNED.pdf").exists()
    saved = list(uploads_dir.iterdir())
    assert len(saved) == 1 and saved[0].parent == uploads_dir
    assert ".." not in saved[0].name and "/" not in saved[0].name


def test_non_pdf_extension_is_rejected(client, uploads_dir):
    r = client.post("/api/extract", files={"file": ("evil.exe", io.BytesIO(b"%PDF-1.4"), "application/pdf")})
    assert r.status_code == 415 and list(uploads_dir.iterdir()) == []


def test_pdf_extension_with_non_pdf_content_is_rejected(client, uploads_dir):
    r = client.post("/api/extract", files={"file": ("a.pdf", io.BytesIO(b"MZ\x90 executable"), "application/pdf")})
    assert r.status_code == 415 and list(uploads_dir.iterdir()) == []


def test_oversized_upload_is_rejected(client, uploads_dir):
    big = b"%PDF-" + b"0" * (5 * 1024 * 1024 + 10)
    r = client.post("/api/extract", files={"file": ("big.pdf", io.BytesIO(big), "application/pdf")})
    assert r.status_code == 413 and list(uploads_dir.iterdir()) == []


def test_sample_extraction_rejects_path_tricks(client):
    assert client.get("/api/extract/sample/..%2F..%2Fetc%2Fpasswd").status_code in (400, 404)
    # HTTP clients normalise a bare ".." away, so also call the handler directly.
    import pytest
    from fastapi import HTTPException
    import main
    for bad in ("..", "../x.pdf", "a/b.pdf", "x.exe"):
        with pytest.raises(HTTPException) as exc:
            main.extract_sample(bad)
        assert exc.value.status_code == 400
    assert client.get("/api/extract/sample/INV-1001_CloudNine_Hosting.pdf").status_code == 200
