import json

from audit import AuditLog, GENESIS


def _write(path, n=3):
    log = AuditLog(str(path))
    for i in range(n):
        log.append({"event": "E", "n": i})
    return log


def test_entries_are_hash_chained(tmp_path):
    log = _write(tmp_path / "a.jsonl")
    rows = log.read_all()
    assert rows[0]["prev_hash"] == GENESIS
    assert rows[1]["prev_hash"] == rows[0]["hash"]
    assert rows[2]["prev_hash"] == rows[1]["hash"]
    assert log.verify().valid and log.verify().entries == 3


def test_editing_an_entry_is_detected(tmp_path):
    path = tmp_path / "a.jsonl"
    log = _write(path)
    lines = path.read_text().splitlines()
    row = json.loads(lines[1]); row["n"] = 999
    lines[1] = json.dumps(row)
    path.write_text("\n".join(lines) + "\n")
    result = log.verify()
    assert not result.valid and result.broken_at == 2


def test_deleting_an_entry_is_detected(tmp_path):
    path = tmp_path / "a.jsonl"
    log = _write(path)
    lines = path.read_text().splitlines()
    path.write_text("\n".join([lines[0], lines[2]]) + "\n")   # drop the middle entry
    result = log.verify()
    assert not result.valid and result.broken_at == 2


def test_chain_continues_after_restart(tmp_path):
    path = tmp_path / "a.jsonl"
    _write(path, 2)
    reopened = AuditLog(str(path))
    reopened.append({"event": "AFTER_RESTART"})
    assert reopened.verify().valid and reopened.verify().entries == 3


def test_empty_log_is_valid(tmp_path):
    assert AuditLog(str(tmp_path / "none.jsonl")).verify().valid
