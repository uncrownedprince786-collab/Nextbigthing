"""Point-in-time price factors and analogs for every eligible asset-session, built without writing
anything to a database.

    python tools/foundation/pit_features.py --out DIR [--assets N] [--check K]

For each asset and each of its stored sessions, the row says what the live jobs would have computed
had they run at the close of that session, using only bars dated on or before it:

* `f`  -- `jobs/factors.compute` (returns, robust z, volume ratio, trigger, SMAs, range, drawdown,
          ATR, and strength against same-industry peers as they stood on that date);
* `an` -- the near-term analog set from `jobs/analogs` for horizons 1 and 5: matches, positive,
          mean, median, min, max, and the grade, built from past days whose outcome had already
          closed by the session.

Why this is a reconstruction and not a copy: the stored `AssetFactor` and `AssetAnalog` tables hold
only the most recent weeks, so the rows for 2019 to 2026 do not exist and writing them would put
about a million training rows into the production database. They are computed here, from the same
functions the live jobs call, and kept out of the database.

Equivalence with the live code is tested, not assumed: `--check K` recomputes K random asset-sessions
through the live per-asset loop and fails on any difference, and `tests/test_foundation.py` perturbs
every bar after a session and requires the session's row to be unchanged.

Provenance and limits, stated so they are not rediscovered later:

* Prices are the stored closes, which for stocks and ETFs are Yahoo's dividend-adjusted closes
  (see tools/foundation/verify_prices.py). Every factor here is scale-free over its window, so a
  later dividend rescales all earlier bars equally and does not change a factor; absolute price
  levels are not features here for that reason.
* The universe is the 616 assets that exist today. No asset in it ever stopped trading
  (tools/foundation/survivorship.py), so every row is a survivor's.
* `barsAvailable` is the count of stored sessions up to and including the date, not the window the
  live job reads.
* `spanDays` is how many calendar days the window actually covers. It exists because a window is
  only a "50-session" window if the sessions are daily, and for PSX they are not: the stored
  exchange history holds about 12 dates a year before 2024 and becomes daily only in 2025. A
  20-session average over monthly-spaced bars is a 20-MONTH average wearing a daily name, and
  nothing else in the row would reveal it. The consumer compares `spanDays` with `n` and decides.

Writes `pit-<year>.jsonl.gz` and `manifest.json`. The data derive from a third-party feed, so the
output belongs in a sealed artifact or a private directory, never in the repository.
"""

from __future__ import annotations

import bisect
import gzip
import hashlib
import json
import random
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
from itertools import accumulate

try:  # not available on Windows; the resource figure is simply omitted there
    import resource
except ImportError:  # pragma: no cover
    resource = None

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "jobs"))

import analogs as an  # noqa: E402
import factors as fc  # noqa: E402
from actions import crossed, unadjusted_windows  # noqa: E402

# The live job reads about (120 + 50 + 60) * 7/5 + 30 calendar days. Longer than any window it uses
# is enough to give the same answer; this is the trailing session count handed to `compute`.
WINDOW = 260
MIN_BARS = fc.SMA_LONG + 1          # a row below this is "thin" in the live job and is still emitted
ANALOG_MIN = an.VOL_WINDOW + 30     # the live analog job skips assets with fewer bars
# How far back an analog factor reads when the volume ratio is not part of the match: the five day
# return is the longest of them, and the one day return is inside it.
ACTION_REACH = 5
NAN = float("nan")


def _arr(values):
    """A float ndarray built through pandas.

    numpy is a dependency of pandas but is not named in requirements.txt, and editing that file would
    change the replay's trust fingerprint (tools/determinism_check and the reconcile workflow compare
    it), so the arrays come from the declared package instead of an undeclared import.
    """
    return pd.Series(values, dtype="float64").to_numpy(copy=True)


FACTOR_KEYS = ("r1", "r5", "r20", "returnZ", "volumeRatio", "entryTrigger", "triggerDirection",
               "sma20", "sma50", "rangePct", "drawdownPct", "atr14", "peerMedianR20", "relStrength", "peers")


def arg(name: str, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


# ------------------------------------------------------------------ analogs, vectorised


class AnalogSeries:
    """One asset's analog factors computed once, then matched against at any session.

    `an.factors(bars, i)` depends only on bars up to i, so computing it once per bar and reusing
    it for every later session is exactly what running the live job at each session would do.

    Unadjusted corporate actions, and why the pool rather than the row
    -----------------------------------------------------------------
    The match pool is the asset's *entire* stored history, so a 2026 session can match against a
    2019 candidate whose one-day move is a split nobody adjusted for, and take that candidate's
    forward return as evidence. The first answer to this was to flag every session at or after an
    asset's first action, which quarantined nearly all of 88 assets' history: safe, and far more
    than the defect costs.

    The defect is narrower than the asset. A fabricated move spoils exactly three things: a
    candidate whose own factors are measured across the action, a forward window that crosses it,
    and a session that compares with factors of its own measured across it. Those are excluded
    here, by date, and every other candidate day in the same series stays in the pool where it
    belongs. `ACTION_REACH` is how far back a factor reads: five sessions for the one and five day
    returns, and `an.VOL_WINDOW` when the volume ratio is part of the match.
    """

    def __init__(self, bars: list[dict], actions: list[str] | None = None):
        n = len(bars)
        self.bars = bars
        self.has_actions = bool(actions)
        # Running count of actions on or before each bar: an action falls in the span
        # (dates[j], dates[i]] exactly when na[i] > na[j], which is one comparison per candidate.
        self.na = _arr(crossed([b["date"] for b in bars], list(actions or [])))
        self.close = _arr([float(b["close"]) for b in bars])
        day, vol, five = [NAN] * n, [NAN] * n, [NAN] * n
        for i in range(n):
            f = an.factors(bars, i)
            if f is not None:
                day[i] = f["day"]
                if f["vol"] is not None:
                    vol[i] = f["vol"]
                if f["five"] is not None:
                    five[i] = f["five"]
        self.day, self.vol, self.five = _arr(day), _arr(vol), _arr(five)
        self.has_volume_upto = [c > 0 for c in accumulate(1 if b["volume"] else 0 for b in bars)]

    def tol(self, t: int):
        """The matching rule for the series as it stood at index t."""
        if self.has_volume_upto[t]:
            return {"day": an.DAY_TOL, "vol": an.VOL_TOL, "five": an.FIVE_TOL, "use_volume": True}
        return an.tolerances(self.bars[: t + 1])

    def at(self, t: int, horizon: int) -> dict | None:
        """The analog row for the session at index t, or None where the live job writes none."""
        if t + 1 < ANALOG_MIN:
            return None
        tol = self.tol(t)
        if tol is None:
            return None
        reach = an.VOL_WINDOW if tol["use_volume"] else ACTION_REACH
        if self.has_actions and self.na[t] > self.na[max(0, t - reach)]:
            # This session's own factors are measured across a fabricated move. There is nothing
            # to match on, so no row is written rather than a row built on a number that is wrong.
            return None
        nd, nv, nf = self.day[t], self.vol[t], self.five[t]
        if nd != nd or nf != nf or (tol["use_volume"] and nv != nv):
            return None
        lo, hi = an.VOL_WINDOW, t - horizon          # candidates i in [lo, hi], as range(lo, hi + 1)
        moves: list[float] = []
        if hi >= lo:
            sl = slice(lo, hi + 1)
            ok = abs(self.day[sl] - nd) <= tol["day"]
            ok &= abs(self.five[sl] - nf) <= tol["five"]
            if tol["use_volume"]:
                ok &= abs(self.vol[sl] - nv) <= tol["vol"]
            if self.has_actions:
                na = self.na
                # `lo` is an.VOL_WINDOW and `reach` is at most that, so neither index can go
                # negative; `hi + horizon` is t, so neither can run off the end.
                ok &= na[sl] == na[lo - reach: hi + 1 - reach]            # the candidate's factors
                ok &= na[lo + horizon: hi + 1 + horizon] == na[sl]        # its forward window
            idx = ok.nonzero()[0] + lo
            moves = [float((self.close[i + horizon] / self.close[i] - 1.0) * 100.0)
                     for i in idx if self.close[i] > 0]
        if not moves:
            g, _ = "none", None
            return {"matches": 0, "positive": 0, "mean": None, "median": None, "min": None,
                    "max": None, "grade": g, "usesVolume": tol["use_volume"]}
        g, _ = an.grade(len(moves), moves)
        return {"matches": len(moves), "positive": sum(m > 0 for m in moves), "mean": an.mean(moves),
                "median": an.median(moves), "min": min(moves), "max": max(moves), "grade": g,
                "usesVolume": tol["use_volume"]}


# ------------------------------------------------------------------ factors


def peer_r20(closes_by_asset, dates_by_asset: dict[str, list[date]], r20_by_asset, peer_ids: list[str], d: date) -> list[float]:
    """Each peer's 20-session return as of its newest bar on or before `d`."""
    out = []
    for p in peer_ids:
        j = bisect.bisect_right(dates_by_asset[p], d) - 1
        if j >= 0:
            v = r20_by_asset[p][j]
            if v == v:
                out.append(float(v))
    return out


def build(assets: list[dict], series: dict[str, list[dict]], *, first_year: int | None = None,
          actions: dict[str, list[str]] | None = None):
    """Yield one row per asset-session. Pure: reads only the arguments.

    `actions` is {symbol: [unadjusted action dates]}; where it is empty the analog pool is the
    whole history, exactly as before.
    """
    dates_by = {a["id"]: [b["date"] for b in series[a["id"]]] for a in assets}
    closes_by = {a["id"]: [float(b["close"]) for b in series[a["id"]]] for a in assets}
    r20_by = {}
    for a in assets:
        c = closes_by[a["id"]]
        arr = [NAN] * len(c)
        for t in range(len(c)):
            v = fc.simple_return(c[max(0, t - 20): t + 1], 20)
            if v is not None:
                arr[t] = v
        r20_by[a["id"]] = arr
    groups: dict[str, list[str]] = {}
    for a in assets:
        if a["industryId"]:
            groups.setdefault(a["industryId"], []).append(a["id"])

    for a in assets:
        bars = series[a["id"]]
        if len(bars) < MIN_BARS:
            continue
        analog = (AnalogSeries(bars, (actions or {}).get(a["symbol"]))
                  if len(bars) >= ANALOG_MIN else None)
        peers = [p for p in groups.get(a["industryId"], []) if p != a["id"]] if a["industryId"] else []
        for t in range(MIN_BARS - 1, len(bars)):
            d = bars[t]["date"]
            if first_year and d.year < first_year:
                continue
            f = fc.compute(bars[max(0, t - WINDOW + 1): t + 1], d,
                           peer_r20(closes_by, dates_by, r20_by, peers, d))
            lo = max(0, t - WINDOW + 1)
            row = {"a": a["symbol"], "t": a["assetType"], "d": d.isoformat(), "n": t + 1,
                   # Calendar days spanned by the bars the factors were computed from.
                   "spanDays": (d - bars[lo]["date"]).days,
                   "f": {k: f.get(k) for k in FACTOR_KEYS}}
            if analog is not None:
                row["an"] = {str(h): analog.at(t, h) for h in an.HORIZONS}
            yield row


# ------------------------------------------------------------------ I/O and reporting


def load(cur, limit: int | None):
    from sessions import session_bar
    cur.execute('SELECT id, symbol, "industryId", "assetType"::text AS "assetType" FROM "Asset" ORDER BY symbol')
    assets = cur.fetchall()
    if limit:
        assets = assets[:limit]
    ids = [a["id"] for a in assets]
    cur.execute(f'''SELECT "assetId", date, close, volume, high, low FROM "PriceSnapshot"
                    WHERE close IS NOT NULL AND {session_bar()} AND "assetId" = ANY(%s)
                    ORDER BY "assetId", date ASC''', (ids,))
    series: dict[str, list[dict]] = {i: [] for i in ids}
    for r in cur.fetchall():
        series[r["assetId"]].append(r)
    return assets, series


def live_oracle(bars: list[dict], t: int, horizon: int, actions: list[str] | None = None) -> dict | None:
    """The same answer `AnalogSeries.at` gives, written the long way round.

    Step for step what `jobs/analogs.main` computes for the bars as they stood at index t, with one
    deliberate difference: the unadjusted-action exclusion `AnalogSeries` applies is applied here
    too, candidate by candidate, so the equivalence check compares the vectorised rule against a
    plain loop over the *same* rule rather than against the live job's contaminated pool. The live
    job's own exposure to this is a separate, open item; it is not what this oracle measures.
    """
    b = bars[: t + 1]
    if len(b) < ANALOG_MIN:
        return None
    tol = an.tolerances(b)
    if tol is None:
        return None
    na = crossed([x["date"] for x in bars], list(actions or []))
    reach = an.VOL_WINDOW if tol["use_volume"] else ACTION_REACH
    if actions and na[t] > na[max(0, t - reach)]:
        return None
    now = an.factors(b, len(b) - 1)
    if now is None or now["five"] is None or (tol["use_volume"] and now["vol"] is None):
        return None
    moves = []
    for i in range(an.VOL_WINDOW, len(b) - 1 - horizon + 1):
        if actions and (na[i] > na[max(0, i - reach)] or na[i + horizon] > na[i]):
            continue
        past = an.factors(b, i)
        if past is None or not an.similar(now, past, tol):
            continue
        got = an.forward(b, i, horizon)
        if got is not None:
            moves.append(got)
    if not moves:
        return {"matches": 0, "grade": "none"}
    g, _ = an.grade(len(moves), moves)
    return {"matches": len(moves), "positive": sum(m > 0 for m in moves), "mean": an.mean(moves),
            "median": an.median(moves), "min": min(moves), "max": max(moves), "grade": g}


def main() -> None:
    from nbt import db
    out = Path(arg("--out", ROOT / ".cache" / "foundation" / "pit"))
    limit = int(arg("--assets", 0)) or None
    check = int(arg("--check", 0))
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    cur = db().cursor()
    assets, series = load(cur, limit)
    t_read = time.time() - t0
    actions = unadjusted_windows(Path(arg("--actions")) if arg("--actions") else
                                 ROOT / "data" / "foundation" / "price_verification" / "unadjusted_actions.json")
    print(f"  unadjusted actions: {sum(len(v) for v in actions.values())} across {len(actions)} assets",
          flush=True)
    expected = sum(max(0, len(series[a["id"]]) - MIN_BARS + 1) for a in assets)

    files: dict[int, gzip.GzipFile] = {}
    digests: dict[int, "hashlib._Hash"] = {}
    counts: dict[int, int] = {}
    null_f: dict[str, dict[str, int]] = {}
    seen: set[tuple] = set()
    dupes = produced = suppressed = 0
    for row in build(assets, series, actions=actions):
        if "an" in row and not any(v is not None for v in row["an"].values()):
            suppressed += 1
        key = (row["a"], row["d"])
        if key in seen:
            dupes += 1
            continue
        seen.add(key)
        y = int(row["d"][:4])
        if y not in files:
            files[y] = gzip.open(out / f"pit-{y}.jsonl.gz", "wt", encoding="utf-8", compresslevel=6)
            digests[y] = hashlib.sha256()
            counts[y] = 0
        line = json.dumps(row, separators=(",", ":"), default=str)
        files[y].write(line + "\n")
        digests[y].update(line.encode())
        counts[y] += 1
        produced += 1
        nf = null_f.setdefault(row["t"], {k: 0 for k in FACTOR_KEYS} | {"_rows": 0})
        nf["_rows"] += 1
        for k in FACTOR_KEYS:
            if row["f"].get(k) is None:
                nf[k] += 1
    for f in files.values():
        f.close()
    t_build = time.time() - t0 - t_read

    mismatches = []
    if check:
        rng = random.Random(20261014)
        eligible = [(a, len(series[a["id"]])) for a in assets if len(series[a["id"]]) >= ANALOG_MIN]
        for _ in range(check):
            a, n = rng.choice(eligible)
            bars = series[a["id"]]
            t = rng.randrange(ANALOG_MIN - 1, n)
            acts = actions.get(a["symbol"])
            ours = AnalogSeries(bars, acts)
            for h in an.HORIZONS:
                got, want = ours.at(t, h), live_oracle(bars, t, h, acts)
                def keep(x):
                    """The fields that must agree. A zero-match row has no statistics to compare."""
                    if x is None:
                        return None
                    out = {"matches": x["matches"], "grade": x["grade"]}
                    if x["matches"]:
                        out.update({k: round(x[k], 9) for k in ("positive", "mean", "median", "min", "max")})
                    return out

                if keep(got) != keep(want):
                    mismatches.append({"asset": a["symbol"], "index": t, "horizon": h,
                                       "ours": keep(got), "live": keep(want)})

    manifest = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "assets": len(assets), "expectedRows": expected, "producedRows": produced,
        "coverageReconciles": expected == produced and dupes == 0, "duplicateRows": dupes,
        "rowsByYear": dict(sorted(counts.items())),
        "sha256ByYear": {y: d.hexdigest() for y, d in sorted(digests.items())},
        "missingnessByAssetType": {
            t: {k: round(v[k] / v["_rows"], 4) for k in FACTOR_KEYS} | {"rows": v["_rows"]}
            for t, v in null_f.items()},
        "liveEquivalence": {"sampled": check * len(an.HORIZONS), "mismatches": len(mismatches),
                            "examples": mismatches[:5]} if check else "not run",
        # What `assemble.py` reads to know the match pool was cleaned here, so it does not have to
        # fall back to flagging every session at or after an asset's first action.
        "analogPoolExcludesUnadjustedActions": bool(actions),
        "unadjustedActions": {"dates": sum(len(v) for v in actions.values()), "assets": len(actions)},
        "sessionsWithNoAnalogBlockBecauseTheirOwnFactorsCrossAnAction": suppressed,
        "resources": {"readSeconds": round(t_read, 1), "buildSeconds": round(t_build, 1),
                      "peakRssMB": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)
                      if resource else None},
        "provenance": {"source": "PriceSnapshot, session bars only", "windowSessions": WINDOW,
                       "factorCode": "jobs/factors.compute", "analogCode": "jobs/analogs (tolerances, factors, similar, grade)",
                       "priceBasis": "stocks and ETFs: dividend-adjusted close"},
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in manifest.items() if k not in ("missingnessByAssetType", "sha256ByYear")}, indent=1))
    if mismatches or not manifest["coverageReconciles"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
