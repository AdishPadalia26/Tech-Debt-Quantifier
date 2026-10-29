"""Tests for GitHub token scrubbing (strip_secrets, scrub script, GET /scan)."""

import json
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fastapi.testclient import TestClient  # noqa: E402

from database.crud import strip_secrets  # noqa: E402
from scripts.scrub_tokens import main as scrub_main  # noqa: E402

TOKEN = "gho_SECRET_TOKEN_123"


def _state() -> dict:
    return {
        "github_url": "https://github.com/acme/widget",
        "repo_id": "acme/widget",
        "github_access_token": TOKEN,
        "openai_api_key": "sk-x",
        "raw_analysis": {"debt_score": 4.2, "github_access_token": TOKEN},
        "findings": [{"id": "f1"}],
    }


def test_strip_secrets_removes_token_keys() -> None:
    """Token / api-key keys are removed, top level and nested; input untouched."""
    state = _state()
    cleaned = strip_secrets(state)
    assert "github_access_token" not in cleaned
    assert "openai_api_key" not in cleaned
    assert "github_access_token" not in cleaned["raw_analysis"]
    assert cleaned["raw_analysis"]["debt_score"] == 4.2
    assert cleaned["github_url"] == state["github_url"]
    assert state["github_access_token"] == TOKEN  # original not mutated
    assert TOKEN not in json.dumps(cleaned)


def test_strip_secrets_non_dict_passthrough() -> None:
    """Non-dict input is returned unchanged."""
    assert strip_secrets(None) is None
    assert strip_secrets([1]) == [1]


def _make_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE scans (id TEXT PRIMARY KEY, raw_result TEXT)")
    conn.executemany(
        "INSERT INTO scans VALUES (?, ?)",
        [
            ("a", json.dumps(_state())),
            ("b", json.dumps({"github_url": "x", "debt_score": 1})),
            ("c", None),
        ],
    )
    conn.commit()
    conn.close()


def test_scrub_script_dry_run_and_apply(tmp_path: Path, capsys) -> None:
    """Dry run counts without writing; --apply backs up and removes the token."""
    db = tmp_path / "t.db"
    _make_db(db)

    assert scrub_main(["--db", str(db)]) == 0
    assert "rows with github_access_token: 1" in capsys.readouterr().out
    conn = sqlite3.connect(db)
    assert TOKEN in conn.execute("SELECT raw_result FROM scans WHERE id='a'").fetchone()[0]
    conn.close()
    assert not list(tmp_path.glob("t.db.bak-*"))

    assert scrub_main(["--db", str(db), "--apply"]) == 0
    out = capsys.readouterr().out
    assert "remaining: 0" in out
    backups = list(tmp_path.glob("t.db.bak-*"))
    assert len(backups) == 1

    conn = sqlite3.connect(db)
    raw = conn.execute("SELECT raw_result FROM scans WHERE id='a'").fetchone()[0]
    other = conn.execute("SELECT raw_result FROM scans WHERE id='b'").fetchone()[0]
    conn.close()
    assert TOKEN not in raw
    assert json.loads(raw)["repo_id"] == "acme/widget"
    assert json.loads(other)["debt_score"] == 1

    conn = sqlite3.connect(backups[0])
    assert TOKEN in conn.execute("SELECT raw_result FROM scans WHERE id='a'").fetchone()[0]
    conn.close()


class _FakeQuery:
    def __init__(self, scan: SimpleNamespace) -> None:
        self._scan = scan

    def filter(self, *args, **kwargs) -> "_FakeQuery":
        return self

    def first(self) -> SimpleNamespace:
        return self._scan


class _FakeSession:
    def __init__(self, scan: SimpleNamespace) -> None:
        self._scan = scan

    def query(self, *args) -> _FakeQuery:
        return _FakeQuery(self._scan)

    def close(self) -> None:
        pass


def test_get_scan_response_has_no_token(monkeypatch) -> None:
    """GET /scan/{id} never returns the token; raw_result is slim by default."""
    from main import app
    from api import deps
    from api.routes import scans as scans_route

    scan = SimpleNamespace(
        id="scan-1",
        total_cost_usd=100.0,
        debt_score=4.2,
        executive_summary="sum",
        priority_actions=[],
        roi_analysis={},
        raw_result=_state(),
        created_at=datetime(2026, 1, 1),
    )
    monkeypatch.setattr(scans_route, "DB_AVAILABLE", True)
    monkeypatch.setattr(scans_route, "SessionLocal", lambda: _FakeSession(scan))
    app.dependency_overrides[deps.get_current_user_optional] = lambda: None
    try:
        client = TestClient(app)
        resp = client.get("/scan/scan-1")
        assert resp.status_code == 200
        body = resp.json()
        assert TOKEN not in resp.text
        assert body["github_url"] == "https://github.com/acme/widget"
        assert body["repo_id"] == "acme/widget"
        assert body["raw_result"] == {
            "github_url": "https://github.com/acme/widget",
            "repo_id": "acme/widget",
        }

        resp = client.get("/scan/scan-1?include_raw=true")
        assert resp.status_code == 200
        assert TOKEN not in resp.text
        assert resp.json()["raw_result"]["raw_analysis"]["debt_score"] == 4.2
    finally:
        app.dependency_overrides.pop(deps.get_current_user_optional, None)
