"""Holes in the stored price history: where they are, why, and which can be refilled.

    python tools/foundation/coverage_gaps.py [--probe N] [--out DIR]

A gap is a session on which an asset's own market traded and this asset has no stored bar. The
market's trading calendar is not assumed from a weekday rule, which would call every holiday a
gap: it is taken from the data, as the set of dates on which a quorum of that market's assets have
a bar. Markets here are the ones the stored assets actually belong to -- US (Yahoo), PSX (the
exchange file), crypto (Coinbase and Kraken, every day) and FX.

Each gap is classified, and the classification is the point:

* `before-listing` / `after-coverage` -- outside the asset's own stored range. Not a hole in the
  data; a shorter history than its neighbours, which the survivorship report already covers.
* `isolated` -- a single missing session inside the range.
* `run-of-N` -- N consecutive missing sessions inside the range.
* `quorum-thin` -- the session exists but fewer than half the market's assets have a bar, so the
  calendar itself is uncertain there and the gap may be an artefact of a partial fetch.

`--probe N` then asks the asset's own source whether the missing bar can still be fetched, for N
randomly chosen gaps, and reports how many came back. Nothing is written to the database. Where a
gap is recoverable the report prints the exact `tools/recover_asset.py ... --write` command that
would fill it: that tool already upserts without deleting, never invents a bar the provider did not
serve, and re-reads the untouched rows afterwards to prove nothing else moved. Running it is a
production write and therefore a deliberate decision for the owner, not a side effect of an audit.
"""

from __future__ import annotations

import json
import random
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "jobs"))
OUT = ROOT / "data" / "foundation" / "coverage"
BROWSER = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
           "Chrome/120.0 Safari/537.36")
QUORUM = 0.5


def arg(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def market_of(asset: dict) -> str:
    t = asset["assetType"]
    if t == "crypto":
        return "crypto"
    if t == "forex":
        return "fx"
    if t in ("commodity", "etf"):
        return "us-futures-and-etf"
    return "PSX" if asset["currency"] == "PKR" else "US"


def yahoo_has(symbol: str, d: date) -> bool | None:
    """Does Yahoo still serve a bar for this symbol on this date? None when the probe failed."""
    p1 = int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp()) - 86400 * 3
    p2 = p1 + 86400 * 7
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}"
           f"?period1={p1}&period2={p2}&interval=1d")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": BROWSER})
        with urllib.request.urlopen(req, timeout=40) as r:
            j = json.loads(r.read())
        res = j["chart"]["result"][0]
        got = {datetime.fromtimestamp(t, timezone.utc).date()
               for t, c in zip(res.get("timestamp") or [],
                               res["indicators"]["quote"][0].get("close") or []) if c is not None}
        return d in got
    except urllib.error.HTTPError as e:
        return None if e.code != 404 else False
    except Exception:  # noqa: BLE001
        return None


def main() -> None:
    from nbt import db
    probe_n = int(arg("--probe") or 0)
    out = Path(arg("--out") or OUT)
    cur = db().cursor()
    cur.execute('SELECT id, symbol, "assetType"::text AS "assetType", currency, active FROM "Asset"')
    assets = {r["id"]: dict(r) for r in cur.fetchall()}
    for a in assets.values():
        a["market"] = market_of(a)

    cur.execute('SELECT "assetId", date, source FROM "PriceSnapshot" ORDER BY "assetId", date')
    have: dict[str, set] = defaultdict(set)
    source: dict[str, Counter] = defaultdict(Counter)
    for r in cur.fetchall():
        have[r["assetId"]].add(r["date"])
        source[r["assetId"]][r["source"]] += 1

    # The calendar per market, from the data: a date is a session when any asset of that market has
    # a bar, and is "thin" when fewer than QUORUM of the market's then-live assets do.
    per_market_dates: dict[str, Counter] = defaultdict(Counter)
    live_on: dict[str, Counter] = defaultdict(Counter)
    for aid, a in assets.items():
        ds = have.get(aid)
        if not ds:
            continue
        lo, hi = min(ds), max(ds)
        for d in ds:
            per_market_dates[a["market"]][d] += 1
        live_on[a["market"]]["_"] += 0
        a["range"] = (lo, hi)
    live_counts: dict[str, Counter] = defaultdict(Counter)
    for aid, a in assets.items():
        if "range" not in a:
            continue
        for d in per_market_dates[a["market"]]:
            if a["range"][0] <= d <= a["range"][1]:
                live_counts[a["market"]][d] += 1

    gaps: list[dict] = []
    kinds = Counter()
    per_market = defaultdict(lambda: {"assets": 0, "sessions": 0, "stored": 0, "gaps": 0, "thin": 0})
    for aid, a in assets.items():
        if "range" not in a:
            per_market[a["market"]]["assets"] += 1
            continue
        lo, hi = a["range"]
        cal = sorted(d for d in per_market_dates[a["market"]] if lo <= d <= hi)
        pm = per_market[a["market"]]
        pm["assets"] += 1
        pm["stored"] += len(have[aid])
        missing = [d for d in cal if d not in have[aid]]
        pm["sessions"] += len(cal)
        pm["gaps"] += len(missing)
        run: list[date] = []
        for d in missing + [None]:
            if run and (d is None or (cal.index(d) - cal.index(run[-1])) != 1):
                thin = any(live_counts[a["market"]][x] and
                           per_market_dates[a["market"]][x] / live_counts[a["market"]][x] < QUORUM
                           for x in run)
                kind = "quorum-thin" if thin else ("isolated" if len(run) == 1 else f"run-of-{len(run)}")
                kinds[kind if not kind.startswith("run-of") else
                      ("run-of-2to5" if len(run) <= 5 else "run-of-6plus")] += 1
                if thin:
                    pm["thin"] += len(run)
                gaps.append({"assetId": aid, "symbol": a["symbol"], "market": a["market"],
                             "assetType": a["assetType"], "from": run[0].isoformat(),
                             "to": run[-1].isoformat(), "sessions": len(run), "kind": kind})
                run = []
            if d is not None:
                run.append(d)

    worst = sorted(gaps, key=lambda g: -g["sessions"])[:25]
    by_symbol = Counter(g["symbol"] for g in gaps)

    probed = {"attempted": 0, "recoverable": 0, "absentAtSource": 0, "probeFailed": 0, "notProbable": 0}
    examples = []
    if probe_n:
        rng = random.Random(20261014)
        pool = [g for g in gaps if g["kind"] != "quorum-thin"]
        rng.shuffle(pool)
        for g in pool[:probe_n]:
            if g["market"] not in ("US", "us-futures-and-etf", "fx"):
                probed["notProbable"] += 1
                continue
            sym = assets[g["assetId"]]["symbol"]
            if g["market"] == "fx":
                sym += "=X"
            probed["attempted"] += 1
            got = yahoo_has(sym, date.fromisoformat(g["from"]))
            if got is None:
                probed["probeFailed"] += 1
            elif got:
                probed["recoverable"] += 1
                if len(examples) < 25:
                    examples.append({
                        "symbol": assets[g["assetId"]]["symbol"], "from": g["from"], "to": g["to"],
                        "sessions": g["sessions"],
                        "repair": f"python tools/recover_asset.py {assets[g['assetId']]['symbol']} "
                                  f"--since {g['from']} --write"})
            else:
                probed["absentAtSource"] += 1
            time.sleep(0.3)

    report = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "assets": len(assets), "gapRuns": len(gaps),
        "missingSessions": sum(g["sessions"] for g in gaps),
        "byKind": dict(kinds),
        "byMarket": {m: {**v, "coverage": round(1 - v["gaps"] / v["sessions"], 5) if v["sessions"] else None}
                     for m, v in sorted(per_market.items())},
        "assetsWithAnyGap": len(by_symbol),
        "worstRuns": worst,
        "probe": probed if probe_n else "not run",
        "probeExamples": examples,
        "calendarRule": f"a date is a session for a market when any of its assets has a bar; "
                        f"thin when fewer than {QUORUM:.0%} of that market's then-live assets do",
        "notes": [
            "Sessions outside an asset's own stored range are not gaps here; a short history is a "
            "survivorship and seeding question, covered by survivorship/report.json.",
            "Nothing is written to any database: this measures whether a repair is possible and "
            "prints the command that would do it. tools/recover_asset.py upserts without deleting, "
            "never invents a bar, and verifies the rows it did not touch -- but it is still a "
            "production write and is left for the owner to run.",
        ],
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "gaps.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k not in ("worstRuns", "notes", "probeExamples")}, indent=1))
    if examples:
        print("\nrecoverable gaps, with the command that would fill each (not run here):")
        for e in examples:
            print(f"  {e['symbol']:8} {e['from']} .. {e['to']} ({e['sessions']} sessions)")
            print(f"    {e['repair']}")


if __name__ == "__main__":
    main()
