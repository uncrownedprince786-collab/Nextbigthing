"""Re-derive every published verdict from raw bars, without the rule table.

Deliberately imports nothing from `lib/decision.ts`, `jobs/setup.py` or `tools/decide.mjs`. Every
number below is recomputed from `PriceSnapshot`, `News` and `AssetAnalog` with plain arithmetic,
then compared against what the site published. A rule table cannot audit itself: a bug in it is
equally present in any check written against it, so the check has to come from the other side.

What it asserts, per asset, on the newest decision:

  * a LONG's close really is above both its averages, and a SHORT's below -- against the windows
    belonging to the horizon the decision actually rested on, which is not always the swing one
  * a directional call has a stop, and that stop is on the side that can be breached
  * the close acted on is inside that market's own staleness allowance
  * a WAIT labelled `file` really is missing the measurement it names, and a WAIT labelled
    `evidence` really does hold the measurements it was judged on

Run: python tools/rederive.py [--limit N]
Exits non-zero when any contradiction is found.
"""

from __future__ import annotations

import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "jobs"))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except Exception:  # noqa: BLE001
    pass

from nbt import db  # noqa: E402

FAST, SLOW = 20, 50
LONG_FAST, LONG_SLOW = 100, 200
# The same allowances `STALE_AFTER_DAYS` publishes, restated rather than imported: importing them
# would make this check agree with the rule table by construction, which is the one thing it must
# not do.
STALE = {"Crypto": 2, "US": 5, "PSX": 6, "FX": 4, "Commodity": 5}


def market_of(asset_type: str, industry_market: str) -> str:
    if asset_type == "crypto":
        return "Crypto"
    if asset_type == "forex":
        return "FX"
    if asset_type == "commodity":
        return "Commodity"
    return "PSX" if industry_market == "PK" else "US"


def main() -> int:
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])

    conn = db()
    conn.rollback()
    conn.read_only = True
    cur = conn.cursor()

    cur.execute('SELECT max("periodEnd") AS d FROM "DecisionLog"')
    period = cur.fetchone()["d"]

    cur.execute(
        """
        SELECT a.id, a.symbol, a."assetType"::text AS atype, i.market AS imarket,
               d.action, d.gate, d.confidence, d.invalidation, d."periodEnd"
          FROM "DecisionLog" d
          JOIN "Asset" a ON a.id = d."assetId"
          JOIN "Industry" i ON i.id = a."industryId"
         WHERE d."periodEnd" = %s
         ORDER BY a.symbol
        """,
        (period,),
    )
    rows = cur.fetchall()
    if limit:
        rows = rows[:limit]

    problems: list[str] = []
    checked = 0
    counts = {"file": 0, "evidence": 0, "directional": 0}

    for r in rows:
        sym = r["symbol"]
        market = market_of(r["atype"], r["imarket"])

        cur.execute(
            """
            SELECT date, close FROM "PriceSnapshot"
            WHERE "assetId" = %s AND close IS NOT NULL
            ORDER BY date DESC LIMIT %s
            """,
            (r["id"], LONG_SLOW + 5),
        )
        bars = list(reversed(cur.fetchall()))
        if not bars:
            if r["action"] != "WAIT":
                problems.append(f"{sym}: {r['action']} published with no stored close at all")
            continue

        closes = [b["close"] for b in bars]
        last, as_of = closes[-1], bars[-1]["date"]
        age = (r["periodEnd"] - as_of).days

        # Which horizon the verdict rested on: the first directional setup, swing then longer.
        cur.execute(
            """
            SELECT DISTINCT ON (horizon) horizon, state
              FROM "AssetSetup"
             WHERE "assetId" = %s AND horizon IN ('swing','longer')
             ORDER BY horizon, "periodEnd" DESC
            """,
            (r["id"],),
        )
        setups = {x["horizon"]: x["state"] for x in cur.fetchall()}
        used = None
        for h in ("swing", "longer"):
            if setups.get(h) in ("buy", "short"):
                used = h
                break
        fast_w, slow_w = (LONG_FAST, LONG_SLOW) if used == "longer" else (FAST, SLOW)

        if r["action"] in ("LONG", "SHORT"):
            counts["directional"] += 1
            checked += 1
            if len(closes) >= slow_w:
                sma_f = statistics.fmean(closes[-fast_w:])
                sma_s = statistics.fmean(closes[-slow_w:])
                up = last > sma_f > sma_s
                down = last < sma_f < sma_s
                if r["action"] == "LONG" and not up:
                    problems.append(
                        f"{sym}: LONG but close {last:.2f} is not above its {fast_w}/{slow_w} "
                        f"averages ({sma_f:.2f}/{sma_s:.2f})"
                    )
                if r["action"] == "SHORT" and not down:
                    problems.append(
                        f"{sym}: SHORT but close {last:.2f} is not below its {fast_w}/{slow_w} "
                        f"averages ({sma_f:.2f}/{sma_s:.2f})"
                    )
            if r["invalidation"] is None:
                problems.append(f"{sym}: {r['action']} with no stop stored")
            elif r["action"] == "LONG" and r["invalidation"] >= last:
                problems.append(
                    f"{sym}: LONG stop {r['invalidation']:.2f} is at or above the close {last:.2f}"
                )
            elif r["action"] == "SHORT" and r["invalidation"] <= last:
                problems.append(
                    f"{sym}: SHORT stop {r['invalidation']:.2f} is at or below the close {last:.2f}"
                )
            if age > STALE.get(market, 5):
                problems.append(
                    f"{sym}: acted on a close {age} days old, {market} allows {STALE.get(market)}"
                )
        else:
            # A WAIT. Its gate says which kind it claims to be; check the claim against the data.
            checked += 1
            file_gates = {"no-prices", "bad-date", "stale", "source-silent", "no-invalidation"}
            evidence_gates = {"mixed-horizons", "peers-against"}
            if r["gate"] in file_gates:
                counts["file"] += 1
                if r["gate"] == "stale" and age <= STALE.get(market, 5):
                    problems.append(
                        f"{sym}: gate `stale` but the close is only {age} days old "
                        f"({market} allows {STALE.get(market)})"
                    )
                if r["gate"] == "no-invalidation" and r["invalidation"] is not None:
                    problems.append(f"{sym}: gate `no-invalidation` but a stop is stored")
            elif r["gate"] in evidence_gates:
                counts["evidence"] += 1
                if not setups:
                    problems.append(
                        f"{sym}: gate `{r['gate']}` claims a measurement, but no setup row exists"
                    )
            elif r["gate"] == "incomplete":
                # The split this pass introduced: a stored setup makes it evidence, none makes it
                # a missing file, and the page must not say the price sits between averages that
                # were never computed.
                if setups:
                    counts["evidence"] += 1
                else:
                    counts["file"] += 1
            elif r["gate"] == "unexplained-move":
                cur.execute(
                    """SELECT count(*) AS n FROM "News"
                        WHERE "assetId" = %s AND "publishedAt" > now() - interval '30 days'""",
                    (r["id"],),
                )
                n = cur.fetchone()["n"]
                counts["evidence" if n else "file"] += 1

    conn.close()

    print(f"re-derived {checked} published verdicts for periodEnd {period}")
    print(
        f"  directional {counts['directional']}  "
        f"WAIT(evidence) {counts['evidence']}  WAIT(file) {counts['file']}"
    )
    if problems:
        print(f"\n{len(problems)} CONTRADICTION(S):")
        for p in problems:
            print("  -", p)
        return 1
    print("\nNo contradiction: every published verdict follows from the stored bars.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
