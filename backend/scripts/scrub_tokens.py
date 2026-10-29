"""Scrub persisted GitHub OAuth tokens from ``scans.raw_result``.

Usage (from backend/):
    python scripts/scrub_tokens.py                 # dry run against techdebt.db
    python scripts/scrub_tokens.py --db other.db   # dry run, custom DB
    python scripts/scrub_tokens.py --apply         # back up DB, then scrub

With ``--apply`` the DB file is first copied to ``<db>.bak-YYYYMMDD-HHMMSS``.
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

TOKEN_KEY = "github_access_token"
DEFAULT_DB = Path(__file__).resolve().parent.parent / "techdebt.db"


def remove_token_key(value: Any) -> bool:
    """Remove ``TOKEN_KEY`` from ``value`` and any nested dicts, in place.

    Args:
        value: Decoded JSON value.

    Returns:
        True if at least one key was removed.
    """
    removed = False
    if isinstance(value, dict):
        if TOKEN_KEY in value:
            del value[TOKEN_KEY]
            removed = True
        for child in value.values():
            if isinstance(child, dict):
                removed = remove_token_key(child) or removed
    return removed


def _decode(raw: Any) -> Any:
    """Decode a raw_result column value (JSON text or bytes) to Python."""
    if raw is None:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None
    return raw


def find_affected_rows(conn: sqlite3.Connection) -> list[tuple[Any, Any]]:
    """Return ``(id, decoded_raw_result)`` for rows that contain the token key.

    Args:
        conn: Open sqlite3 connection.

    Returns:
        List of affected rows with their decoded (already scrubbed) payloads.
    """
    rows = conn.execute(
        "SELECT id, raw_result FROM scans WHERE raw_result LIKE ?",
        (f'%"{TOKEN_KEY}"%',),
    ).fetchall()
    affected: list[tuple[Any, Any]] = []
    for row_id, raw in rows:
        decoded = _decode(raw)
        if remove_token_key(decoded):
            affected.append((row_id, decoded))
    return affected


def backup_db(db_path: Path) -> Path:
    """Copy the DB file to ``<db>.bak-YYYYMMDD-HHMMSS`` and return the path."""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = db_path.with_name(f"{db_path.name}.bak-{stamp}")
    shutil.copy2(db_path, backup_path)
    return backup_path


def scrub(db_path: Path, apply: bool = False) -> int:
    """Count (and optionally remove) GitHub tokens stored in scans.raw_result.

    Args:
        db_path: Path to the sqlite database.
        apply: When True, back up the DB then write scrubbed payloads.

    Returns:
        Number of affected rows.

    Raises:
        FileNotFoundError: When ``db_path`` does not exist.
    """
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    conn = sqlite3.connect(db_path)
    try:
        affected = find_affected_rows(conn)
        print(f"rows with {TOKEN_KEY}: {len(affected)}")
        if not apply or not affected:
            if not apply:
                print("dry run: no changes written (use --apply to scrub)")
            return len(affected)
    finally:
        conn.close()

    backup_path = backup_db(db_path)
    print(f"backup written: {backup_path}")

    conn = sqlite3.connect(db_path)
    try:
        conn.executemany(
            "UPDATE scans SET raw_result = ? WHERE id = ?",
            [(json.dumps(payload), row_id) for row_id, payload in affected],
        )
        conn.commit()
        remaining = len(find_affected_rows(conn))
    finally:
        conn.close()
    print(f"scrubbed {len(affected)} rows; remaining: {remaining}")
    return len(affected)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="sqlite DB path")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run", dest="apply", action="store_false", help="count only (default)"
    )
    mode.add_argument("--apply", dest="apply", action="store_true", help="write changes")
    parser.set_defaults(apply=False)
    args = parser.parse_args(argv)
    try:
        scrub(args.db, apply=args.apply)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
