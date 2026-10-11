"""What a failover would serve, compared with the primary (brain.md rule 94). Read-only.

    python tools/standby_parity.py

For each configured standby (SUPABASE_DATABASE_URL, DATABASE_URL_FALLBACK) against DATABASE_URL:

  * active assets the standby lacks, by (industry slug, symbol) -- a name that would vanish on failover;
  * for the assets both hold, the ones whose newest news reading the standby does not have -- coverage that
    would read as "no row" there;
  * how far each decision input lags: prices, setups, factors, analogs, decisions, news readings.

The site publishes no call from a standby read (lib/assetClass.ts), because setups, factors and analogs
are not mirrored; this report says how far behind they are, so the bound is measured rather than assumed.
Exit 0 when every active asset is held and the news readings match, 1 when not, 2 when a database cannot
be read. Credentials are never printed.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except Exception:  # noqa: BLE001
    pass

INPUTS = (
    ("PriceSnapshot", "date"),
    ("AssetSetup", "periodEnd"),
    ("AssetFactor", "periodEnd"),
    ("AssetAnalog", "periodEnd"),
    ("DecisionLog", "periodEnd"),
    ("HumanSignal", "periodEnd"),
)


def parity(primary_active: set[tuple[str, str]], standby_assets: set[tuple[str, str]],
           primary_read: set[tuple[str, str]], standby_read: set[tuple[str, str]]) -> dict:
    """The gaps, as data: active assets the standby lacks, and held assets whose newest reading it lacks."""
    held = primary_active & standby_assets
    return {
        "missing_assets": sorted(primary_active - standby_assets),
        "missing_readings": sorted((primary_read & held) - standby_read),
        "held": len(held),
        "active": len(primary_active),
    }


def redact(text: str) -> str:
    return re.sub(r"postgres(?:ql)?://[^\s\"']+", "postgresql://<redacted>", text)


def read(url: str) -> tuple[set, set, set, dict]:
    import psycopg

    with psycopg.connect(url, connect_timeout=30) as c, c.cursor() as cur:
        try:
            cur.execute('SELECT i.slug, a.symbol, COALESCE(a.active, true) FROM "Asset" a JOIN "Industry" i ON i.id = a."industryId"')
            rows = cur.fetchall()
        except Exception:  # noqa: BLE001 - a standby before the pool migration has no `active`
            c.rollback()
            cur.execute('SELECT i.slug, a.symbol, true FROM "Asset" a JOIN "Industry" i ON i.id = a."industryId"')
            rows = cur.fetchall()
        assets = {(s, y) for s, y, _ in rows}
        active = {(s, y) for s, y, act in rows if act}
        cur.execute(
            'SELECT i.slug, a.symbol FROM "HumanSignal" h JOIN "Asset" a ON a.id = h."assetId" '
            'JOIN "Industry" i ON i.id = a."industryId" '
            'WHERE h."periodEnd" = (SELECT max("periodEnd") FROM "HumanSignal" WHERE "assetId" IS NOT NULL)'
        )
        readings = set(cur.fetchall())
        # One statement for every input's newest day.
        cur.execute("SELECT " + ", ".join(f'(SELECT max("{col}")::date::text FROM "{table}")' for table, col in INPUTS))
        newest = dict(zip((t for t, _ in INPUTS), cur.fetchone()))
    return assets, active, readings, newest


def main() -> int:
    primary = (os.environ.get("DATABASE_URL") or "").strip()
    standbys = [(n, (os.environ.get(n) or "").strip()) for n in ("SUPABASE_DATABASE_URL", "DATABASE_URL_FALLBACK")]
    standbys = [(n, u) for n, u in standbys if u and u != primary]
    if not primary or not standbys:
        print("standby parity: DATABASE_URL and at least one standby are needed")
        return 2
    try:
        _, p_active, p_read, p_newest = read(primary)
    except Exception as e:  # noqa: BLE001
        print(f"standby parity: the primary could not be read ({redact(str(e).splitlines()[0])})")
        return 2
    worst = 0
    for name, url in standbys:
        try:
            s_assets, _, s_read, s_newest = read(url)
        except Exception as e:  # noqa: BLE001
            print(f"\n== {name}: could not be read ({redact(str(e).splitlines()[0])})")
            worst = max(worst, 2)
            continue
        gap = parity(p_active, s_assets, p_read, s_read)
        print(f"\n== {name}")
        print(f"  active assets held: {gap['held']} of {gap['active']}")
        if gap["missing_assets"]:
            print(f"  MISSING {len(gap['missing_assets'])}: {gap['missing_assets'][:12]}")
        print(f"  newest news readings missing for held assets: {len(gap['missing_readings'])} {gap['missing_readings'][:8]}")
        for table, _ in INPUTS:
            print(f"  {table:14} primary {p_newest.get(table)}  standby {s_newest.get(table)}")
        if gap["missing_assets"] or gap["missing_readings"]:
            worst = max(worst, 1)
    print("\nstandby parity: " + ("every active asset and reading held" if worst == 0 else "gaps above"))
    return worst


if __name__ == "__main__":
    sys.exit(main())
