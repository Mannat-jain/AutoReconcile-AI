"""Test fixtures. Env vars are set BEFORE the app is imported so nothing touches the real data files."""
import os
import tempfile

_TMP = tempfile.mkdtemp(prefix="autoreconcile-tests-")
os.environ["AUDIT_LOG_PATH"] = os.path.join(_TMP, "bootstrap-audit.jsonl")
os.environ["PAYOUT_DB_PATH"] = os.path.join(_TMP, "bootstrap-payouts.db")
os.environ["MOCK_LATENCY_SECONDS"] = "0"
os.environ.pop("RAZORPAY_KEY_ID", None)
os.environ.pop("RAZORPAY_KEY_SECRET", None)

import pytest
from fastapi.testclient import TestClient

import main
import razorpay_service


@pytest.fixture(autouse=True)
def isolated_state(tmp_path):
    """Every test gets a fresh audit log, payout ledger and reconciliation cache."""
    razorpay_service.configure(
        audit_path=str(tmp_path / "audit.jsonl"),
        db_path=str(tmp_path / "payouts.db"),
    )
    main._reconciliation_cache = None
    yield


@pytest.fixture
def client():
    return TestClient(main.app)


@pytest.fixture
def uploads_dir(tmp_path, monkeypatch):
    d = tmp_path / "uploads"
    d.mkdir()
    monkeypatch.setattr(main, "UPLOAD_DIR", str(d))
    return d
