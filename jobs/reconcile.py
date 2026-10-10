"""Copy the standby's newer rows back to the primary after an outage, before the primary is written.

    python jobs/reconcile.py

Why. When the primary is unreachable the lanes write the standby (jobs/nbt.py `db`), so during a quota
pause the newest prices, calls and outcomes exist only there. When the primary answers again it is
behind, and two things would go wrong if nothing copied them back: the site, which reads the primary
first, would serve the older figures; and the nightly mirror (primary to standby) would copy the
primary's older values over the standby's newer ones -- a DecisionLog outcome measured during the outage,
for instance, overwritten with the null it had before.

What. If the standby is ahead -- a newer price day, or a decision written after the primary's newest --
the five tables jobs/mirror.py keeps (prices, the call log, signals, theses, vetoes) are copied standby to
primary over the mirror's own windows, by natural key, never deleting. Derived tables (setups, factors,
rankings) are not copied: the next decision run rebuilds them from the prices.

Run by jobs/schemacheck.py at the start of every lane, and by cron-mirror.yml before its own copy. Cheap
when there is nothing to do: two small queries on each side. Never fails a lane: if either side cannot
be read it says so and exits 0, because the lane's own connection is what decides whether it can run.
"""

from __future__ import annotations

import os
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from nbt import is_unreachable, standby_url  # noqa: E402

TABLES_BACK = "PriceSnapshot,DecisionLog,SignalLog,AssetThesis,MacroGate"
DECISION_WINDOW_DAYS = 40  # the mirror's own window: DecisionLog outcomes mature for a month
PRICE_SLACK_DAYS = 3


def ahead(primary: dict, standby: dict) -> bool:
    """Whether the standby holds writes the primary does not. Pure: each side's two maxima are inputs.

    A newer price day, or a decision written later than the primary's newest. Normally the standby can only
    trail -- the nightly mirror copies the primary's `computedAt` as it is -- so either sign means writes
    landed on the standby."""
    sp, pp = standby.get("price"), primary.get("price")
    if sp is not None and (pp is None or sp > pp):
        return True
    sd, pd = standby.get("decided"), primary.get("decided")
    return sd is not None and (pd is None or sd > pd)


def maxima(conn) -> dict:
    with conn.cursor() as cur:
        cur.execute('SELECT max(date) AS price FROM "PriceSnapshot"')
        price = cur.fetchone()["price"]
        cur.execute('SELECT max("computedAt") AS decided FROM "DecisionLog"')
        decided = cur.fetchone()["decided"]
    return {"price": price, "decided": decided}


def main() -> int:
    import psycopg
    from psycopg.rows import dict_row

    primary_url = (os.environ.get("DATABASE_URL") or "").strip()
    standby = standby_url(primary_url) if primary_url else None
    if not standby:
        print("  reconcile: no standby configured (or WRITE_FAILOVER=off); nothing to copy back")
        return 0
    name, standby_url_ = standby
    try:
        with psycopg.connect(primary_url, row_factory=dict_row, connect_timeout=20) as p:
            mp = maxima(p)
    except Exception as e:  # noqa: BLE001
        why = "unreachable" if is_unreachable(e) else type(e).__name__
        print(f"  reconcile: the primary is {why}; lanes write {name} until it answers, and this copies back then")
        return 0
    try:
        with psycopg.connect(standby_url_, row_factory=dict_row, connect_timeout=20) as s:
            ms = maxima(s)
    except Exception as e:  # noqa: BLE001
        print(f"  reconcile: {name} could not be read ({type(e).__name__}); nothing to copy back")
        return 0
    if not ahead(mp, ms):
        print(f"  reconcile: the primary is current against {name}; nothing to copy back")
        return 0
    newest_primary_price = mp["price"] or date.today() - timedelta(days=30)
    price_since = (newest_primary_price - timedelta(days=PRICE_SLACK_DAYS)).isoformat()
    decision_since = (date.today() - timedelta(days=DECISION_WINDOW_DAYS)).isoformat()
    print(
        f"::warning title=Copying the standby back::{name} is ahead of the primary (prices to {ms['price']} vs "
        f"{mp['price']}; decisions written to {ms['decided']} vs {mp['decided']}): rows written during the "
        f"outage are being copied back before this lane writes the primary."
    )
    import mirror

    ok = mirror.main(["--from-env", name, "--to-env", "DATABASE_URL", "--tables", "PriceSnapshot", "--since", price_since]) == 0
    ok = mirror.main(["--from-env", name, "--to-env", "DATABASE_URL", "--tables", TABLES_BACK.split(",", 1)[1], "--since", decision_since]) == 0 and ok
    print(f"  reconcile: copy back {'complete' if ok else 'INCOMPLETE -- the next lane will try again'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
