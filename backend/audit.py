"""
audit.py - append-only, tamper-evident audit log
===================================================
Every payout decision (executed, blocked, duplicate-suppressed, failed) is written as one JSON line.

*Append-only* is enforced in code (the file is only ever opened in append mode and there is no
update/delete path), and made *tamper-evident* with a hash chain: each entry stores the hash of the
previous entry, and its own hash covers ``prev_hash`` + its content. Editing, deleting or re-ordering
any past line breaks every hash after it, which ``verify()`` detects.

Limits (honest): a hash chain shows that history was altered, it cannot stop someone with write access
from rewriting the *whole* file. For real assurance also ship entries to write-once storage (S3 Object
Lock / a WORM bucket) or anchor the latest hash somewhere the writer cannot modify. Writes are
serialised with a lock, which is correct for a single server process; multiple processes would need a
file lock or a database table.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional

GENESIS = "0" * 64


def _canonical(entry: dict) -> str:
    return json.dumps(entry, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _hash(prev_hash: str, body: dict) -> str:
    return hashlib.sha256((prev_hash + _canonical(body)).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class VerifyResult:
    valid: bool
    entries: int
    broken_at: Optional[int] = None      # 1-based line number of the first bad entry
    reason: str = ""


class AuditLog:
    def __init__(self, path: str) -> None:
        self.path = path
        self._lock = threading.Lock()
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self._last_hash = self._load_last_hash()

    def _load_last_hash(self) -> str:
        last = GENESIS
        if os.path.exists(self.path):
            with open(self.path, encoding="utf-8") as fh:
                for line in fh:
                    if line.strip():
                        try:
                            last = json.loads(line).get("hash", last)
                        except json.JSONDecodeError:
                            break
        return last

    def append(self, entry: dict) -> dict:
        with self._lock:
            body = dict(entry)
            body["logged_at"] = datetime.now(timezone.utc).isoformat()
            body["prev_hash"] = self._last_hash
            record = dict(body, hash=_hash(self._last_hash, body))
            line = (json.dumps(record, ensure_ascii=False) + "\n").encode("utf-8")
            fd = os.open(self.path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o640)   # append-only
            try:
                os.write(fd, line)
                os.fsync(fd)                     # durable before we report success
            finally:
                os.close(fd)
            self._last_hash = record["hash"]
            return record

    def read_all(self) -> List[dict]:
        if not os.path.exists(self.path):
            return []
        with open(self.path, encoding="utf-8") as fh:
            return [json.loads(line) for line in fh if line.strip()]

    def verify(self) -> VerifyResult:
        prev = GENESIS
        count = 0
        if not os.path.exists(self.path):
            return VerifyResult(True, 0)
        with open(self.path, encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, start=1):
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    return VerifyResult(False, count, lineno, "line is not valid JSON")
                stored = record.pop("hash", None)
                if record.get("prev_hash") != prev:
                    return VerifyResult(False, count, lineno, "chain broken: prev_hash does not match previous entry")
                if stored != _hash(prev, record):
                    return VerifyResult(False, count, lineno, "entry content was modified")
                prev, count = stored, count + 1
        return VerifyResult(True, count)
