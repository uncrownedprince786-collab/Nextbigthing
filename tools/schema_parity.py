"""Compare the structure of two databases, column by column. Read-only.

"Both ran the same migrations" is a claim about a table of migration names, not about the schema. A
migration that was edited after one project applied it, a manual change on one side, or a default
that differs would all leave the two reading as identical in `_prisma_migrations` and different in
fact -- and a standby whose columns do not match is one the mirror silently under-copies, since it
copies only the columns both sides have.

Compares, for every table in `public`: the set of tables, each column's type, nullability and
default, and each index and constraint by name and definition. Prints every difference and exits
non-zero if there is one. Never prints a credential: the two URLs are read from the environment.

Run: python tools/schema_parity.py [A_ENV_NAME] [B_ENV_NAME]     (default DATABASE_URL, SUPABASE_DATABASE_URL)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "jobs"))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except Exception:  # noqa: BLE001
    pass

COLUMNS = """
    SELECT table_name, column_name, data_type, udt_name, is_nullable, column_default
      FROM information_schema.columns
     WHERE table_schema = 'public' AND table_name <> '_prisma_migrations'
"""
INDEXES = """
    SELECT tablename AS table_name, indexname, indexdef FROM pg_indexes
     WHERE schemaname = 'public' AND tablename <> '_prisma_migrations'
"""
CONSTRAINTS = """
    SELECT c.relname AS table_name, k.conname, k.contype::text AS kind, pg_get_constraintdef(k.oid) AS def
      FROM pg_constraint k JOIN pg_class c ON c.oid = k.conrelid
     WHERE c.relnamespace = 'public'::regnamespace AND c.relname <> '_prisma_migrations'
       -- NOT NULL as a named constraint (`n`) exists from PostgreSQL 18 only. Nullability is compared
       -- per column above, so listing it here would report the server version and not the schema.
       AND k.contype <> 'n'
"""


def normalise_default(d: str | None) -> str | None:
    """Defaults compare equal across servers that print the same expression slightly differently."""
    if d is None:
        return None
    return " ".join(d.replace("::text", "").replace("::character varying", "").split())


def snapshot(url: str) -> dict:
    import psycopg
    from psycopg.rows import dict_row

    with psycopg.connect(url, row_factory=dict_row, connect_timeout=30) as c, c.cursor() as cur:
        cur.execute(COLUMNS)
        cols = {
            (r["table_name"], r["column_name"]): (r["data_type"], r["udt_name"], r["is_nullable"], normalise_default(r["column_default"]))
            for r in cur.fetchall()
        }
        cur.execute(INDEXES)
        idx = {(r["table_name"], r["indexname"]): r["indexdef"] for r in cur.fetchall()}
        cur.execute(CONSTRAINTS)
        con = {(r["table_name"], r["conname"]): (r["kind"], r["def"]) for r in cur.fetchall()}
    return {"columns": cols, "indexes": idx, "constraints": con}


def diff(a: dict, b: dict, label_a: str, label_b: str) -> list[str]:
    out: list[str] = []
    for kind in ("columns", "indexes", "constraints"):
        ka, kb = set(a[kind]), set(b[kind])
        for k in sorted(ka - kb):
            out.append(f"{kind}: {'.'.join(k)} exists only in {label_a}")
        for k in sorted(kb - ka):
            out.append(f"{kind}: {'.'.join(k)} exists only in {label_b}")
        for k in sorted(ka & kb):
            if a[kind][k] != b[kind][k]:
                out.append(f"{kind}: {'.'.join(k)} differs: {label_a}={a[kind][k]!r} {label_b}={b[kind][k]!r}")
    return out


def main(argv: list[str]) -> int:
    name_a = argv[0] if argv else "DATABASE_URL"
    name_b = argv[1] if len(argv) > 1 else "SUPABASE_DATABASE_URL"
    ua, ub = os.environ.get(name_a), os.environ.get(name_b)
    if not ua or not ub:
        print(f"need both {name_a} and {name_b} in the environment")
        return 2
    a, b = snapshot(ua), snapshot(ub)
    tables_a = {t for t, _ in a["columns"]}
    tables_b = {t for t, _ in b["columns"]}
    print(f"{name_a}: {len(tables_a)} tables, {len(a['columns'])} columns, {len(a['indexes'])} indexes, {len(a['constraints'])} constraints")
    print(f"{name_b}: {len(tables_b)} tables, {len(b['columns'])} columns, {len(b['indexes'])} indexes, {len(b['constraints'])} constraints")
    problems = diff(a, b, name_a, name_b)
    if not problems:
        print("\nidentical structure")
        return 0
    print(f"\n{len(problems)} difference(s):")
    for p in problems[:60]:
        print("  " + p)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
