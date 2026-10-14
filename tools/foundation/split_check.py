"""Unadjusted corporate actions: one-day moves that are a share split, not a price move.

    python tools/foundation/split_check.py [--out DIR] [--confirm N]

Found by the independent price verification: BECO's stored PSX series runs at about ten times
Yahoo's Karachi series until 2025-11-17, then steps down to meet it. Yahoo back-adjusted the whole
history for a one-for-ten action; the exchange's daily file did not, so the stored series carries a
-88.6% one-day "return" that no holder experienced, and every factor measured across that date for
that asset is wrong.

A split shows itself as a one-day ratio close to a simple fraction. That alone is not proof -- a
stock really can halve in a day -- so each candidate is scored on three things together:

* how close the ratio is to a simple split factor;
* whether the move reverses (a real crash tends to persist; a scale change never recovers);
* whether the asset's typical daily move makes a jump that size otherwise unthinkable.

`--confirm N` then checks the N strongest candidates against a second provider: if the other
provider's return on that date is small while the stored one is enormous, the stored series is
unadjusted and the other is adjusted. That is the confirmation, and candidates without it stay
candidates.

Nothing is written to any database. The output names the assets and dates whose factors cannot be
trusted, so a dataset can exclude them rather than quietly learn from them.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "jobs"))
OUT = ROOT / "data" / "foundation" / "price_verification"
BROWSER = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
           "Chrome/120.0 Safari/537.36")

# Ratios a corporate action produces, as close/prev. Below 1 is a split or a bonus issue; above 1
# is a reverse split. 1.5 and 0.667 are included because three-for-two is common.
FACTORS = [1 / 2, 1 / 3, 1 / 4, 1 / 5, 1 / 6, 1 / 8, 1 / 10, 1 / 20, 2 / 3, 3 / 2, 2, 3, 4, 5, 6, 8, 10, 20]
NEAR = 0.04          # within 4% of a clean factor
MIN_MOVE = 0.30      # only consider one-day moves beyond 30%


def arg(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def yahoo_return(symbol: str, d: date) -> float | None:
    """The other provider's own one-day return on `d`, or None when it does not serve it."""
    p1 = int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp()) - 86400 * 10
    p2 = p1 + 86400 * 20
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}"
           f"?period1={p1}&period2={p2}&interval=1d")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": BROWSER})
        with urllib.request.urlopen(req, timeout=40) as r:
            j = json.loads(r.read())
        res = j["chart"]["result"][0]
        bars = sorted((datetime.fromtimestamp(t, timezone.utc).date(), c)
                      for t, c in zip(res.get("timestamp") or [],
                                      res["indicators"]["quote"][0].get("close") or []) if c)
        for i in range(1, len(bars)):
            if bars[i][0] == d and bars[i - 1][1]:
                return bars[i][1] / bars[i - 1][1] - 1
    except Exception:  # noqa: BLE001
        return None
    return None


def main() -> None:
    from nbt import db
    confirm = int(arg("--confirm") or 0)
    out = Path(arg("--out") or OUT)
    conn = db()
    cur = conn.cursor()
    cur.execute('SELECT id, symbol, "assetType"::text AS "assetType", currency FROM "Asset"')
    assets = {r["id"]: dict(r) for r in cur.fetchall()}
    cur.execute('SELECT "assetId", date, close, source FROM "PriceSnapshot" WHERE close > 0 '
                'ORDER BY "assetId", date')
    series: dict[str, list] = defaultdict(list)
    for r in cur.fetchall():
        series[r["assetId"]].append((r["date"], float(r["close"]), r["source"]))
    conn.close()

    candidates = []
    for aid, bars in series.items():
        a = assets.get(aid)
        if not a or len(bars) < 30:
            continue
        rets = [(bars[i][0], bars[i][1] / bars[i - 1][1]) for i in range(1, len(bars))]
        moves = sorted(abs(r - 1) for _, r in rets)
        typical = moves[len(moves) // 2] or 1e-6
        for i, (d, ratio) in enumerate(rets, start=1):
            if abs(ratio - 1) < MIN_MOVE:
                continue
            best = min(FACTORS, key=lambda fct: abs(ratio / fct - 1))
            closeness = abs(ratio / best - 1)
            if closeness > NEAR:
                continue
            # Does it come back? Twenty sessions later, a scale change has not recovered.
            j = min(i + 20, len(bars) - 1)
            after = bars[j][1] / bars[i][1]
            recovered = abs(after - (1 / best)) < abs(after - 1)
            candidates.append({
                "symbol": a["symbol"], "assetType": a["assetType"], "date": d.isoformat(),
                "ratio": round(ratio, 4), "nearestFactor": round(best, 4),
                "closenessPct": round(closeness * 100, 2),
                "movePct": round((ratio - 1) * 100, 2),
                "timesTypicalMove": round(abs(ratio - 1) / typical, 1),
                "reversedWithin20Sessions": bool(recovered),
                "source": bars[i][2],
            })

    candidates.sort(key=lambda c: (-c["timesTypicalMove"], c["closenessPct"]))
    confirmed = unconfirmed = contradicted = 0
    for c in candidates[:confirm]:
        sym = c["symbol"] + (".KA" if c["source"].startswith("Pakistan") else "")
        other = yahoo_return(sym, date.fromisoformat(c["date"]))
        time.sleep(0.3)
        if other is None:
            c["secondProvider"] = "no data"
            unconfirmed += 1
        elif abs(other) < 0.15 and abs(c["ratio"] - 1) > 0.25:
            # The other provider saw an ordinary day where this one saw a collapse.
            c["secondProvider"] = {"return": round(other * 100, 2), "verdict": "unadjusted here"}
            confirmed += 1
        else:
            c["secondProvider"] = {"return": round(other * 100, 2), "verdict": "both saw the move"}
            contradicted += 1

    by_type: dict[str, int] = defaultdict(int)
    by_symbol: dict[str, int] = defaultdict(int)
    for c in candidates:
        by_type[c["assetType"] + ("/PSX" if c["source"].startswith("Pakistan") else "")] += 1
        by_symbol[c["symbol"]] += 1
    report = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "assetsScanned": len(series),
        "candidates": len(candidates),
        "assetsAffected": len(by_symbol),
        "byAssetType": dict(sorted(by_type.items())),
        "confirmation": {"checked": min(confirm, len(candidates)), "unadjustedHere": confirmed,
                         "bothProvidersSawIt": contradicted, "noSecondSource": unconfirmed},
        "rule": (f"a one-day move beyond {MIN_MOVE:.0%} whose ratio is within {NEAR:.0%} of a "
                 f"simple split factor; confirmed when a second provider's return that day is small"),
        "effect": ("A candidate's own one-day return is not a return, and every factor measured "
                   "across it -- returns, the robust z, analog matching -- is wrong for that asset "
                   "on that date and for any window containing it."),
        # Every candidate, not a sample: a dataset has to be able to exclude all of them.
        "candidatesList": candidates,
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "unadjusted_actions.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k not in ("top", "effect", "rule")}, indent=1))
    for c in candidates[:15]:
        f = c["nearestFactor"]
        shape = f"1:{round(1 / f)}" if f < 1 else f"{round(f)}:1"
        print(f"  {c['symbol']:8} {c['date']} {c['movePct']:8.1f}%  {shape:>5}  "
              f"{c['timesTypicalMove']:6.0f}x typical  {c.get('secondProvider', '')}")


if __name__ == "__main__":
    main()
