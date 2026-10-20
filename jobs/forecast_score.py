"""Grade the short-horizon forecasts whose window has closed, and nothing else.

    python jobs/forecast_score.py
    python jobs/forecast_score.py --limit 500
    python jobs/forecast_score.py --dry-run

What it does
------------
Reads `BrainForecast` rows that have matured and have no `BrainForecastOutcome`, finds the venue's
close at or just after each one's `maturesAt`, and writes one outcome row per forecast.

What it refuses to do
---------------------
  * **It never grades an immature forecast.** The filter is `maturesAt <= now()` in SQL, so a
    five-minute call made forty seconds ago is invisible to this job. The whole value of a
    prospective record is that nothing in it was scored before the window it claimed had passed.
  * **It never edits a forecast.** Outcomes are their own table with a unique key on
    `forecastId`, so re-running grades nothing twice and changes no claim.
  * **It never invents the observation.** The price must come from a closed bar whose close time
    is at or after maturity; if the venue has no such bar yet -- an outage, a listing gone, a
    maturity in the last few seconds -- the forecast is left ungraded and counted as waiting. An
    ungraded forecast is visible on the site as exactly that.
  * **It takes the first bar at or after maturity, not the newest.** Grading a 15-minute call
    against the price three hours later would be scoring a different claim. `latenessMs` records
    how far past maturity the bar actually sits, so a late grading can be seen rather than assumed
    away.

Run: python jobs/forecast_score.py [--limit N] [--dry-run]
Reads: BrainForecast, BrainForecastOutcome, Asset; Binance public klines
Writes: BrainForecastOutcome
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "jobs"))
sys.path.insert(0, str(ROOT / "tools" / "foundation"))

from nbt import db, rows, step  # noqa: E402

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except Exception:  # noqa: BLE001
    pass

SCORER_VERSION = "crypto-forecast-scorer-1"
VENUE_MAP = ROOT / "data" / "foundation" / "dataset" / "crypto_venue_map.json"
UA = {"User-Agent": "nextbigthing/1.0 (forecast scoring)"}
#: How long past maturity a bar may sit and still be accepted as the observation. Beyond this the
#: forecast is left ungraded rather than scored against a price from a different market state --
#: three intervals of the series it was made on, which is the same tolerance the serving path
#: applies to its own inputs.
MAX_LATENESS = {"5m": timedelta(minutes=15), "4h": timedelta(hours=12)}
INTERVAL_MS = {"5m": 300_000, "4h": 14_400_000}


def venue_pairs() -> dict[str, dict]:
    """The venues each coin can be observed on, from the same map the site serves from.

    Both halves of the loop read one file. They did not at first: the site's chain already fell
    through to Kraken for the coins Binance has delisted, and this job knew only Binance, so a
    Monero forecast could be shown and recorded and then never graded -- a row that is in the
    record and can never leave it. A forecast the site is willing to make is one it must be able
    to score.
    """
    doc = json.loads(VENUE_MAP.read_text(encoding="utf-8"))
    return {
        a["slug"]: {"binance": a.get("binance"), "kraken": a.get("kraken")}
        for a in doc["assets"]
        if a.get("binance") or a.get("kraken")
    }


def klines(pair: str, interval: str, start_ms: int, limit: int = 12) -> list[list]:
    url = (f"https://api.binance.com/api/v3/klines?symbol={pair}&interval={interval}"
           f"&startTime={start_ms}&limit={limit}")
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=20) as r:
                got = json.loads(r.read())
            return got if isinstance(got, list) else []
        except urllib.error.HTTPError as e:
            if e.code in (418, 429) or e.code >= 500:
                time.sleep(2 ** attempt)
                continue
            return []
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            time.sleep(2 ** attempt)
    return []


def kraken_ohlc(pair: str, interval: str, since_s: int) -> list[list]:
    mins = 5 if interval == "5m" else 240
    url = f"https://api.kraken.com/0/public/OHLC?pair={pair}&interval={mins}&since={since_s}"
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=20) as r:
            body = json.loads(r.read())
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError):
        return []
    result = (body or {}).get("result") or {}
    key = next((k for k in result if k != "last"), None)
    rows_ = result.get(key) or [] if key else []
    step_ms = INTERVAL_MS[interval]
    # Normalised to the kline shape this job already reads: index 4 is the close and index 6 is
    # the bar's last millisecond.
    return [[int(r[0]) * 1000, 0, 0, 0, r[4], 0, int(r[0]) * 1000 + step_ms - 1] for r in rows_]


def observation(venues: dict, interval: str, matures: datetime) -> tuple[float, datetime, str] | None:
    """The close of the first bar whose window ends at or after maturity, and where it came from.

    Asked for from one interval *before* maturity, so the bar containing the maturity instant is
    in the page and the first qualifying one is the bar maturity falls in or ends -- not the next
    one along, which would score a window a bar longer than the forecast claimed.

    A bar's `close_ms` is its last millisecond, so the instant the bar ends is `close_ms + 1`. The
    distinction is worth the line: comparing against `close_ms` made an exactly-on-time grading
    report a lateness of minus one millisecond, which is not a thing that can happen.
    """
    step_ms = INTERVAL_MS[interval]
    start_ms = int(matures.timestamp() * 1000) - step_ms
    chain = []
    if venues.get("binance"):
        chain.append((f"Binance {venues['binance']}", lambda: klines(venues["binance"], interval, start_ms)))
    if venues.get("kraken"):
        chain.append((f"Kraken {venues['kraken']}", lambda: kraken_ohlc(venues["kraken"], interval, start_ms // 1000)))
    for source, get in chain:
        for k in get():
            ends = int(k[6]) + 1
            at = datetime.fromtimestamp(ends / 1000, timezone.utc)
            if at >= matures:
                return float(k[4]), at, source
    return None


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Grade matured short-horizon forecasts.")
    ap.add_argument("--limit", type=int, default=1000)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)

    pairs = venue_pairs()
    conn = db()
    cur = conn.cursor()
    graded = waiting = skipped = 0
    pending: list[tuple] = []
    try:
        step("matured forecasts awaiting a result")
        due = rows(cur, '''
            SELECT f.id, f.symbol, f."horizonKey", f.interval, f.direction,
                   f."referencePrice", f."maturesAt"
              FROM "BrainForecast" f
              LEFT JOIN "BrainForecastOutcome" o ON o."forecastId" = f.id
             WHERE o.id IS NULL AND f."maturesAt" <= now()
             ORDER BY f."maturesAt"
             LIMIT %s
        ''', (a.limit,))
        print(f"  {len(due)} matured and ungraded")

        for f in due:
            venues = pairs.get(f["symbol"])
            if not venues:
                skipped += 1
                print(f"  {f['symbol']}: no venue in the chain carries it, cannot be graded here")
                continue
            matures = f["maturesAt"]
            if matures.tzinfo is None:
                matures = matures.replace(tzinfo=timezone.utc)
            got = observation(venues, f["interval"], matures)
            if got is None:
                waiting += 1
                continue
            price, at, source = got
            lateness = at - matures
            if lateness > MAX_LATENESS[f["interval"]]:
                waiting += 1
                print(f"  {f['symbol']} {f['horizonKey']}: nearest bar is "
                      f"{lateness} past maturity, left ungraded")
                continue
            ref = float(f["referencePrice"])
            realised = (price / ref - 1.0) * 100.0
            # A move of exactly zero has no direction. It is recorded, marked with a note, and
            # counted as wrong rather than as a free win: the forecast said the price would go one
            # way and it did not.
            actual = "UP" if price > ref else "DOWN" if price < ref else "FLAT"
            correct = actual == f["direction"]
            note = None if actual != "FLAT" else (
                "the close matched the reference exactly, so no direction was realised; "
                "counted as not correct")
            if a.dry_run:
                print(f"  would grade {f['symbol']} {f['horizonKey']} {f['direction']} -> "
                      f"{actual} {realised:+.4f}%")
                graded += 1
                continue
            # Accumulated and written once below rather than inserted here. A query inside the
            # fetch loop is the shape this repository's query budget exists to stop: it is one
            # round trip per forecast against a free-tier pooler that admits few clients, and it
            # grows with the record rather than with the run.
            pending.append((f["id"], price, at, realised, actual, correct,
                            int(lateness.total_seconds() * 1000), source,
                            SCORER_VERSION, note))
            graded += 1

        if pending and not a.dry_run:
            cur.executemany('''
                INSERT INTO "BrainForecastOutcome"
                    ("forecastId", "observedPrice", "observedAt", "realisedPct", actual, correct,
                     "latenessMs", source, "scorerVersion", note)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT ("forecastId") DO NOTHING
            ''', pending)
        if not a.dry_run:
            conn.commit()
        print(f"  graded {graded}, still waiting on a bar {waiting}, ungradeable here {skipped}")

        # The record as it now stands, printed so a run's summary carries the number the site
        # shows rather than only the delta this run made.
        total = rows(cur, '''
            SELECT count(*) AS forecasts,
                   count(o.id) AS graded,
                   count(*) FILTER (WHERE o.correct) AS correct
              FROM "BrainForecast" f
              LEFT JOIN "BrainForecastOutcome" o ON o."forecastId" = f.id
        ''')[0]
        g = int(total["graded"] or 0)
        c = int(total["correct"] or 0)
        rate = f"{c / g * 100:.1f}%" if g else "no rate yet"
        print(f"  record: {total['forecasts']} forecasts, {g} graded, {c} right ({rate})")
    finally:
        cur.close()
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
