"""
payout_store.py - durable payout ledger (the source of truth for idempotency)
================================================================================
The previous version remembered "already paid" keys in an in-memory ``set``: it was lost on every
restart, was not safe under concurrent requests (check-then-add race) and the key was recorded
*before* the payout succeeded, so one failure blocked all retries.

This ledger fixes all three:

* Durable      - rows live in SQLite (file), so a restart cannot cause a double payment.
* Atomic       - the idempotency key is the PRIMARY KEY; ``claim()`` is a single INSERT, so when two
                 requests race exactly one wins - there is no "check, then insert" window.
* Retry-safe   - a payout that FAILED can be claimed again; a PENDING or PAID one cannot.

Lifecycle:   (no row) --claim--> PENDING --complete--> PAID
                                   `--fail--> FAILED --claim--> PENDING ...

A row stuck in PENDING (process died between claim and completion) is deliberately NOT retried
automatically: the gateway may or may not have paid, so it needs reconciliation against the
gateway's records (or the gateway-side idempotency key) rather than a blind second attempt.
"""
from __future__ import annotations

import os
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

_SCHEMA = """
CREATE TABLE IF NOT EXISTS payouts (
    idempotency_key TEXT PRIMARY KEY,
    invoice_number  TEXT NOT NULL,
    amount          TEXT NOT NULL,
    status          TEXT NOT NULL CHECK (status IN ('PENDING', 'PAID', 'FAILED')),
    payout_id       TEXT,
    utr             TEXT,
    error           TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
)
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class Claim:
    acquired: bool                   # True -> caller owns the right to execute the payout
    status: str                      # status of the ledger row after the call
    payout_id: Optional[str] = None  # set when a previous attempt already PAID


class PayoutLedger:
    def __init__(self, path: str) -> None:
        self.path = path
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with closing(self._connect()) as conn:
            conn.execute(_SCHEMA)
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        # One short-lived connection per operation: safe across FastAPI's worker threads.
        return sqlite3.connect(self.path, timeout=10, isolation_level=None)

    def claim(self, key: str, invoice_number: str, amount: str) -> Claim:
        now = _now()
        with closing(self._connect()) as conn:
            try:
                conn.execute(
                    "INSERT INTO payouts (idempotency_key, invoice_number, amount, status, created_at, updated_at) "
                    "VALUES (?, ?, ?, 'PENDING', ?, ?)",
                    (key, invoice_number, amount, now, now),
                )
                return Claim(True, "PENDING")
            except sqlite3.IntegrityError:
                pass  # somebody already owns this key

            # A FAILED attempt may be retried: flip FAILED -> PENDING atomically (only one caller can win).
            cur = conn.execute(
                "UPDATE payouts SET status = 'PENDING', error = NULL, updated_at = ? "
                "WHERE idempotency_key = ? AND status = 'FAILED'",
                (now, key),
            )
            if cur.rowcount == 1:
                return Claim(True, "PENDING")
            row = conn.execute(
                "SELECT status, payout_id FROM payouts WHERE idempotency_key = ?", (key,)
            ).fetchone()
            return Claim(False, row[0], row[1])

    def complete(self, key: str, payout_id: str, utr: Optional[str]) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                "UPDATE payouts SET status = 'PAID', payout_id = ?, utr = ?, updated_at = ? "
                "WHERE idempotency_key = ? AND status = 'PENDING'",
                (payout_id, utr, _now(), key),
            )

    def fail(self, key: str, error: str) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                "UPDATE payouts SET status = 'FAILED', error = ?, updated_at = ? "
                "WHERE idempotency_key = ? AND status = 'PENDING'",
                (error[:500], _now(), key),
            )

    def get(self, key: str) -> Optional[dict]:
        with closing(self._connect()) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM payouts WHERE idempotency_key = ?", (key,)).fetchone()
            return dict(row) if row else None

    def count(self, status: Optional[str] = None) -> int:
        with closing(self._connect()) as conn:
            if status:
                return conn.execute("SELECT COUNT(*) FROM payouts WHERE status = ?", (status,)).fetchone()[0]
            return conn.execute("SELECT COUNT(*) FROM payouts").fetchone()[0]
