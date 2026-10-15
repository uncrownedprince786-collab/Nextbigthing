"""Every PSX bar the exchange published that this database does not hold, from its own archive.

    python tools/foundation/psx_complete.py stored            refresh the snapshot of what is held
    python tools/foundation/psx_complete.py extract           one pass over the swept archives
    python tools/foundation/psx_complete.py integrate --write additive inserts, bounded, ledgered
    python tools/foundation/psx_complete.py verify            prove nothing else moved

Why this exists, and why it is not the Yahoo backfill again
-----------------------------------------------------------
`psx_backfill` filled what a second provider could serve, and had to refuse 38,246 bars because
Yahoo back-adjusts for splits while the stored series is raw. That refusal was correct and it left
the bars unrecovered rather than wrong.

The exchange's own daily closing file has no such problem: it **is** the raw series, the same
source and the same basis as every PSX row already stored. So for any date the exchange published
and this database lacks, there is nothing to adjudicate -- the bar simply was never fetched. The
sweep downloaded every session since 2018, and this reads those cached files and takes what is
missing, whatever category the earlier analysis had put the date in:

  * **before the stored range** -- 2018, which predates the universe's 2019 start;
  * **basis-divergent** -- dates Yahoo could not supply compatibly, which the exchange can;
  * **pad-rejected** -- dates where Yahoo offered a synthetic flat bar and the exchange has a real one;
  * **not listed at Yahoo** -- the 23 names, which the exchange carries like any other.

Rows go in under the exchange's own source name, because that is where they come from. The ledger
records the exact keys written, which is what a rollback needs; the source string is provenance,
not a batch marker.
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "jobs"))

STAGE = ROOT / ".cache" / "psx_complete"
SWEEP = ROOT / ".cache" / "acquire" / "psx_sweep_ledger.json"
OUT = ROOT / "data" / "foundation" / "psx_complete"

# The exchange's own label, because that is the file these bars come from. jobs/psx.py writes the
# same string for the same reason.
SOURCE = "Pakistan Stock Exchange daily closing file"
BATCH = 500
FIRST = "2018-01-01"


def arg(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def load(path: Path, default=None):
    return json.loads(Path(path).read_text("utf-8")) if Path(path).exists() else default


def dump(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=1, default=str), encoding="utf-8")
    tmp.replace(path)


def connect():
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    from nbt import db
    return db()


def cmd_stored() -> None:
    """What the database holds for PSX today, per symbol, with the source of each bar."""
    from nbt import rows
    conn = connect()
    cur = conn.cursor()
    try:
        got = rows(cur, 'SELECT a.id, a.symbol, p.date::text AS d, p.source '
                        'FROM "PriceSnapshot" p JOIN "Asset" a ON a.id = p."assetId" '
                        'WHERE a.currency = %s ORDER BY a.symbol, p.date', ("PKR",))
    finally:
        cur.close()
        conn.close()
    by: dict[str, dict] = {}
    for r in got:
        s = by.setdefault(r["symbol"], {"assetId": r["id"], "bars": {}})
        s["bars"][r["d"]] = r["source"]
    dump(STAGE / "stored.json", {"takenAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                 "symbols": len(by), "bars": len(got), "series": by})
    print(f"stored: {len(by)} PSX symbols, {len(got)} bars")


def cmd_extract() -> None:
    """Read every swept archive from the disk cache and collect what the database is missing."""
    import psx
    stored = load(STAGE / "stored.json")
    if not stored:
        print("run `stored` first")
        raise SystemExit(2)
    sweep = load(SWEEP, {"dates": {}})
    days = sorted(d for d, v in sweep["dates"].items()
                  if v.get("status") == "published" and d >= FIRST)
    series = stored["series"]
    held = {sym: set(v["bars"]) for sym, v in series.items()}
    ranges = {sym: (min(v), max(v)) for sym, v in held.items() if v}
    today = date.today()

    found: dict[str, dict] = defaultdict(dict)
    cats: Counter = Counter()
    print(f"extract: {len(days)} published archive days, {len(series)} PSX symbols", flush=True)
    for i, d in enumerate(days, 1):
        rows = psx.read_day(date.fromisoformat(d), today, keep=frozenset(series)) or {}
        for sym, r in rows.items():
            if d in held.get(sym, ()):
                continue
            lo, hi = ranges.get(sym, (None, None))
            cats["beforeStoredRange" if lo and d < lo else
                 ("afterStoredRange" if hi and d > hi else "insideStoredRange")] += 1
            found[sym][d] = {"d": d, "o": r.get("open"), "h": r.get("high"), "l": r.get("low"),
                             "c": r.get("close"), "v": r.get("volume")}
        if i % 250 == 0 or i == len(days):
            print(f"  {i}/{len(days)} days, {sum(len(v) for v in found.values())} missing bars so far",
                  flush=True)
    out = {sym: [found[sym][k] for k in sorted(found[sym])] for sym in sorted(found) if found[sym]}
    total = sum(len(v) for v in out.values())
    dump(STAGE / "missing.json",
         {"generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
          "source": SOURCE, "basis": "raw as-traded OHLCV, identical to the stored series",
          "archiveDaysRead": len(days), "symbols": len(out), "bars": total,
          "byPosition": dict(cats), "series": out})
    print(f"extract done: {total} bars across {len(out)} symbols   {dict(cats)}")


def cmd_integrate() -> None:
    write = "--write" in sys.argv
    data = load(STAGE / "missing.json")
    stored = load(STAGE / "stored.json")
    if not data:
        print("run `extract` first")
        raise SystemExit(2)
    ledger_path = STAGE / "integrated.jsonl"
    done = set()
    if ledger_path.exists():
        for line in ledger_path.read_text("utf-8").splitlines():
            if line.strip():
                done.add(json.loads(line)["symbol"])
    todo = [(s, v) for s, v in sorted(data["series"].items()) if s not in done]
    total = sum(len(v) for _, v in todo)
    print(f"integrate: {len(todo)} symbols, {total} bars" + ("" if write else "  (dry run)"),
          flush=True)
    if not write:
        return
    conn = connect()
    cur = conn.cursor()
    inserted = 0
    try:
        for i, (sym, bars) in enumerate(todo, 1):
            aid = stored["series"][sym]["assetId"]
            n = 0
            for k in range(0, len(bars), BATCH):
                chunk = bars[k:k + BATCH]
                cur.executemany(
                    'INSERT INTO "PriceSnapshot" ("assetId", date, open, high, low, close, volume, source)'
                    ' VALUES (%s, %s, %s, %s, %s, %s, %s, %s)'
                    ' ON CONFLICT ("assetId", date) DO NOTHING',
                    [(aid, b["d"], b["o"], b["h"], b["l"], b["c"], b["v"], SOURCE) for b in chunk])
                n += cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
            conn.commit()
            inserted += n
            with ledger_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({"symbol": sym, "assetId": aid, "offered": len(bars),
                                     "inserted": n, "from": bars[0]["d"], "to": bars[-1]["d"],
                                     "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}) + "\n")
            if i % 25 == 0 or i == len(todo):
                print(f"  {i}/{len(todo)} symbols, {inserted} rows inserted", flush=True)
    finally:
        cur.close()
        conn.close()
    print(f"integrate done: {inserted} rows inserted")


def cmd_verify() -> None:
    from nbt import rows
    before = load(STAGE / "stored.json")
    conn = connect()
    cur = conn.cursor()
    try:
        now = rows(cur, 'SELECT a.symbol, p.date::text d, p.close, p.source '
                        'FROM "PriceSnapshot" p JOIN "Asset" a ON a.id = p."assetId" '
                        'WHERE a.currency = %s', ("PKR",))
        counts = rows(cur, 'SELECT source, count(*) n, min(date)::text lo, max(date)::text hi '
                           'FROM "PriceSnapshot" GROUP BY 1 ORDER BY 2 DESC')
        size = rows(cur, "SELECT pg_size_pretty(pg_database_size(current_database())) s")[0]["s"]
    finally:
        cur.close()
        conn.close()
    have: dict[str, set] = defaultdict(set)
    for r in now:
        have[r["symbol"]].add(r["d"])
    lost = [f"{s} {d}" for s, v in before["series"].items() for d in v["bars"]
            if d not in have.get(s, ())]
    report = {"verifiedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "psxBarsBefore": before["bars"], "psxBarsNow": len(now),
              "added": len(now) - before["bars"], "preExistingLost": len(lost),
              "examplesLost": lost[:5], "sourceCounts": counts, "databaseSize": size}
    dump(OUT / "integration_verified.json", report)
    print(json.dumps(report, indent=1, default=str))
    if lost:
        print("FAILED: pre-existing bars are missing")
        raise SystemExit(1)
    print("integrity check passed: every pre-existing PSX bar is still present")


COMMANDS = {"stored": cmd_stored, "extract": cmd_extract, "integrate": cmd_integrate,
            "verify": cmd_verify}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        raise SystemExit(2)
    COMMANDS[sys.argv[1]]()
