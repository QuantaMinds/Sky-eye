"""Run api/infra/bigquery_schema.sql idempotently against the LeadLens project.

Idempotency rules:
- All CREATE SCHEMA / CREATE TABLE statements use IF NOT EXISTS.
- All CREATE VIEW statements use CREATE OR REPLACE.
- INSERT statements at the end of the DDL seed reference data. Re-running the
  raw INSERT would duplicate rows, so we run INSERTs only when the target
  table is empty (detected by parsing the table name out of the statement).

Usage:
    python scripts/setup_bigquery.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from google.cloud import bigquery

_PROJECT = "sky-eye-496604"
_LOCATION = "us-west1"
_DDL_PATH = Path(__file__).resolve().parents[1] / "api" / "infra" / "bigquery_schema.sql"

_INSERT_TABLE_RE = re.compile(
    r"\bINSERT\s+INTO\s+`([^`]+)`", re.IGNORECASE
)


def _split_statements(sql: str) -> list[str]:
    """String-aware splitter on top-level `;`. Honors single/double quotes
    and -- line comments so semicolons inside string literals or comments
    do NOT split a statement. Block comments /* */ are not used in our DDL.
    """
    out: list[str] = []
    buf: list[str] = []
    i, n = 0, len(sql)
    in_single = in_double = in_line_comment = False
    while i < n:
        ch = sql[i]
        if in_line_comment:
            buf.append(ch)
            if ch == "\n":
                in_line_comment = False
        elif in_single:
            buf.append(ch)
            if ch == "'":
                in_single = False
        elif in_double:
            buf.append(ch)
            if ch == '"':
                in_double = False
        elif ch == "-" and i + 1 < n and sql[i + 1] == "-":
            in_line_comment = True
            buf.append(ch)
        elif ch == "'":
            in_single = True
            buf.append(ch)
        elif ch == '"':
            in_double = True
            buf.append(ch)
        elif ch == ";":
            stmt = "".join(buf).strip()
            if stmt:
                out.append(stmt)
            buf = []
        else:
            buf.append(ch)
        i += 1
    tail = "".join(buf).strip()
    if tail:
        out.append(tail)
    return out


def _is_seeded(client: bigquery.Client, table_ref: str) -> bool:
    """Return True if the target table already has rows (skip the INSERT)."""
    row = next(client.query(f"SELECT COUNT(*) AS n FROM `{table_ref}`").result())
    return row.n > 0


def _label(stmt: str) -> str:
    head = stmt.split("\n", 1)[0]
    return head[:80] + ("..." if len(head) > 80 else "")


def main() -> int:
    if not _DDL_PATH.exists():
        print(f"FATAL: {_DDL_PATH} not found", file=sys.stderr)
        return 1

    client = bigquery.Client(project=_PROJECT, location=_LOCATION)
    sql = _DDL_PATH.read_text(encoding="utf-8")
    statements = _split_statements(sql)
    print(f"Loaded {len(statements)} statements from {_DDL_PATH.name}\n")

    ran = skipped = 0
    for stmt in statements:
        match = _INSERT_TABLE_RE.search(stmt)
        if match:
            table_ref = match.group(1)
            try:
                if _is_seeded(client, table_ref):
                    print(f"  SKIP   INSERT (already seeded): {table_ref}")
                    skipped += 1
                    continue
            except Exception as exc:
                # Table not yet created in this run, or transient — let the INSERT try anyway.
                print(f"  WARN   could not pre-check {table_ref}: {exc}")
        is_view = re.search(
            r"\bCREATE\s+OR\s+REPLACE\s+VIEW\b", stmt, re.IGNORECASE
        )
        try:
            client.query(stmt).result()
            print(f"  OK     {_label(stmt)}")
            ran += 1
        except Exception as exc:
            if is_view:
                # Views may reference raw tables that haven't been migrated to
                # the full schema yet. Warn-not-fail so table creation still
                # completes — views can be rebuilt manually once data lands.
                print(f"  WARN   view skipped: {_label(stmt)}\n         {exc}")
                skipped += 1
                continue
            print(f"  FAIL   {_label(stmt)}\n         {exc}", file=sys.stderr)
            return 2

    print(f"\nDone. {ran} statements run, {skipped} skipped or warned.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
