import threading

import pytest

import razorpay_service as rs
from models import PayoutRequest
from payout_store import PayoutLedger


def make_request(**overrides) -> PayoutRequest:
    data = dict(invoice_number="INV-100", vendor_id="27AAPFA5678K1Z2", beneficiary_name="Vendor",
                account_number="123", ifsc="", amount=1000.0)
    data.update(overrides)
    return PayoutRequest(**data)


# ---------------------------------------------------------------- idempotency key
def test_key_is_deterministic():
    assert rs.idempotency_key("V1", "INV-1", 100.0) == rs.idempotency_key("V1", "INV-1", 100.0)


def test_key_ignores_formatting_differences():
    a = rs.idempotency_key(" gstin1 ", "inv-1 ", 100)
    b = rs.idempotency_key("GSTIN1", "INV-1", 100.00)
    assert a == b


def test_same_invoice_number_and_amount_from_different_vendors_do_not_collide():
    # Regression: the old key was sha256(invoice_number:amount) so vendor B's payout was suppressed.
    assert rs.idempotency_key("VENDOR-A", "INV-100", 5000.0) != rs.idempotency_key("VENDOR-B", "INV-100", 5000.0)


def test_key_changes_when_amount_or_currency_changes():
    base = rs.idempotency_key("V", "INV-1", 100.0)
    assert base != rs.idempotency_key("V", "INV-1", 100.01)
    assert base != rs.idempotency_key("V", "INV-1", 100.0, "USD")


# ---------------------------------------------------------------- confidence gate
def test_low_confidence_autonomous_payout_is_refused_and_audited():
    with pytest.raises(PermissionError):
        rs.create_payout(make_request(), 0.95)          # gate is strictly greater-than
    events = [e["event"] for e in rs.audit_log.read_all()]
    assert events == ["PAYOUT_BLOCKED_LOW_CONFIDENCE"]
    assert rs.ledger.count() == 0                       # nothing was claimed


def test_high_confidence_autonomous_payout_executes():
    resp = rs.create_payout(make_request(), 0.96)
    assert resp.status == "processed" and resp.mock
    last = rs.audit_log.read_all()[-1]
    assert last["event"] == "PAYOUT_EXECUTED" and last["approved_by"] is None


def test_human_approval_can_pass_the_gate_and_is_attributed():
    rs.create_payout(make_request(), 0.3, approved_by="asha@finance")
    last = rs.audit_log.read_all()[-1]
    assert last["approved_by"] == "asha@finance"


def test_blank_approver_does_not_bypass_the_gate():
    with pytest.raises(PermissionError):
        rs.create_payout(make_request(), 0.3, approved_by="   ")


# ---------------------------------------------------------------- duplicate suppression
def test_second_identical_payout_is_suppressed():
    first = rs.create_payout(make_request(), 0.99)
    with pytest.raises(rs.DuplicatePayoutError) as exc:
        rs.create_payout(make_request(), 0.99)
    assert exc.value.status == "PAID" and exc.value.payout_id == first.payout_id
    assert [e["event"] for e in rs.audit_log.read_all()] == ["PAYOUT_EXECUTED", "PAYOUT_IDEMPOTENT_SKIP"]


def test_different_vendor_same_invoice_and_amount_is_still_paid():
    rs.create_payout(make_request(vendor_id="A"), 0.99)
    rs.create_payout(make_request(vendor_id="B"), 0.99)      # must NOT be suppressed
    assert rs.ledger.count("PAID") == 2


def test_failed_payout_can_be_retried(monkeypatch):
    monkeypatch.setattr(rs, "MOCK_MODE", False)              # live path raises NotImplementedError
    with pytest.raises(NotImplementedError):
        rs.create_payout(make_request(), 0.99)
    assert rs.ledger.count("FAILED") == 1

    monkeypatch.setattr(rs, "MOCK_MODE", True)               # gateway is back
    resp = rs.create_payout(make_request(), 0.99)            # old code: blocked forever by the burned key
    assert resp.status == "processed"
    assert rs.ledger.count("PAID") == 1 and rs.ledger.count("FAILED") == 0


def test_concurrent_identical_payouts_pay_exactly_once():
    results, errors = [], []
    barrier = threading.Barrier(16)

    def worker():
        barrier.wait()
        try:
            results.append(rs.create_payout(make_request(), 0.99))
        except rs.DuplicatePayoutError as e:
            errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(16)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert len(results) == 1 and len(errors) == 15
    assert rs.ledger.count("PAID") == 1
    executed = [e for e in rs.audit_log.read_all() if e["event"] == "PAYOUT_EXECUTED"]
    assert len(executed) == 1


# ---------------------------------------------------------------- durability
def test_ledger_survives_a_restart(tmp_path):
    db = str(tmp_path / "restart.db")
    ledger = PayoutLedger(db)
    assert ledger.claim("k1", "INV-1", "10.00").acquired
    ledger.complete("k1", "pout_1", "UTR1")

    reopened = PayoutLedger(db)                              # simulates a server restart
    claim = reopened.claim("k1", "INV-1", "10.00")
    assert not claim.acquired and claim.status == "PAID" and claim.payout_id == "pout_1"


def test_pending_rows_are_not_blindly_retried(tmp_path):
    ledger = PayoutLedger(str(tmp_path / "p.db"))
    assert ledger.claim("k", "INV-1", "10.00").acquired
    again = ledger.claim("k", "INV-1", "10.00")              # crashed mid-flight: needs reconciliation
    assert not again.acquired and again.status == "PENDING"
