"""How far does a coin actually travel over each window, in units of its own volatility?

    python tools/research/crypto_levels.py

A direction with no levels is not usable: "UP over the next fifteen minutes" does not say where to
get in, where to be wrong, or where to take it off. Those three numbers have to come from
somewhere, and there are only two honest places -- a model fitted to predict them, or a
measurement of what the market has actually done.

There is no model here that predicts magnitude. The brain is binary and predicts the **sign** of
the forward return and nothing else; a target derived from its probability would be a size claim
it never made. So the levels are a measurement, and this file is that measurement.

What is measured
----------------
For every horizon, over every usable row of the training folds, in units of the row's own
14-bar ATR at the decision instant:

  * **the favourable excursion** -- how far price went the predicted way before the window closed,
    at the median and the quartiles. This is what a target is: the distance a typical win reaches.
  * **the adverse excursion** -- how far it went the *wrong* way first, on the rows that ended up
    going the right way. This is what a stop has to survive. A stop inside the median adverse
    excursion of a winning trade is a stop that takes winners off.
  * **how often each candidate stop/target pair would have been hit first**, which is the only
    number that makes a pair a choice rather than a preference.

Scaled by ATR, not by a fixed percentage, because a 0.5% stop is a scratch on Bitcoin and a round
trip on a small coin. ATR at the decision bar is already in the feature vector, is computed from
the same window the model read, and is the serving path's own number -- so a level printed on the
page is the same arithmetic as the level measured here.

Why the training folds and not the test fold
--------------------------------------------
These are not a prediction and they are not scored, but they are still a *choice* made from data,
and a choice made on the test fold spends it. The quantiles come from the training and validation
folds; the holdout stays for the thing it is for.

What this is NOT
----------------
Not a backtest, not a strategy, and not a profitability claim. No transaction cost, spread,
funding or slippage is in any number here, and the hit rates below are measured on the direction
being *correct* -- the model is right about 53% of the time ungated, so the unconditional
expectation of these levels is not the conditional one printed beside them.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))

from crypto_horizons import HORIZONS, ORDER  # noqa: E402
from crypto_matrix import prepare_cached  # noqa: E402
from crypto_conviction import training_config  # noqa: E402
from intraday_features import FEATURES  # noqa: E402
from train_crypto_short import split  # noqa: E402

OUT = ROOT / "data" / "foundation" / "dataset" / "crypto_levels.json"

ATR_COLUMN = FEATURES.index("atr14")

#: The stop and target multiples offered, in ATR units at the decision bar. Fixed before the run.
CANDIDATES = [
    (0.5, 0.75), (0.5, 1.0), (0.75, 1.0), (0.75, 1.5),
    (1.0, 1.0), (1.0, 1.5), (1.0, 2.0), (1.5, 2.0),
    # Wider rungs, added after the first sweep came back monotone in the stop width: every
    # candidate was net-negative and the widest was least so, because the fee is a fixed
    # fraction of notional and shrinks in R as the stop grows. A ladder whose best entry is its
    # last entry has not been measured, it has been truncated.
    (2.0, 3.0), (2.0, 4.0), (3.0, 4.0), (3.0, 6.0), (4.0, 8.0), (6.0, 12.0),
    (8.0, 16.0), (10.0, 20.0), (15.0, 30.0),
]


def excursions(close: np.ndarray, keep: np.ndarray, bars_ahead: int,
               step_ok: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """`(best, worst, final)` as signed fractions of the entry price, over the forward window.

    `best` and `worst` are the highest and lowest close reached inside the window -- read from
    closes rather than from highs and lows on purpose: the model is fitted on closes, the label is
    a close-to-close sign, and a target measured on intrabar highs would be a target a close-based
    claim never promised.
    """
    n = len(keep)
    best = np.full(n, np.nan)
    worst = np.full(n, np.nan)
    final = np.full(n, np.nan)
    for off in range(1, bars_ahead + 1):
        idx = keep + off
        ok = step_ok & (idx < len(close))
        if not ok.any():
            continue
        rel = np.full(n, np.nan)
        rel[ok] = close[idx[ok]] / close[keep[ok]] - 1.0
        best = np.where(np.isnan(best), rel, np.fmax(best, rel))
        worst = np.where(np.isnan(worst), rel, np.fmin(worst, rel))
        if off == bars_ahead:
            final = rel
    return best, worst, final


def measure(tag: str, symbols: list[str], stride: int, horizons: list[str]) -> dict:
    out: dict[str, dict] = {}
    for interval in sorted({HORIZONS[k]["interval"] for k in horizons}):
        here = [k for k in horizons if HORIZONS[k]["interval"] == interval]
        data = prepare_cached(symbols, interval, stride,
                              context=training_config(tag, here[0])["context"])
        X, ts = data["X"], data["ts"]
        atr = X[:, ATR_COLUMN].astype(np.float64)   # already a fraction of price
        step_ms = next(iter(data["corpora"].values()))["stepMs"]

        for key in here:
            bars_ahead = HORIZONS[key]["bars"]
            tr_m, va_m, _te_m, _meta = split(ts, bars_ahead, step_ms)
            fit_rows = tr_m | va_m

            bests, worsts, finals, atrs = [], [], [], []
            offset = 0
            for _s, meta in data["corpora"].items():
                full_ts, full_close, keep = meta["_series"]
                n = len(keep)
                if n == 0:
                    continue
                here_rows = fit_rows[offset:offset + n]
                # Only rows whose whole forward window is consecutive: an excursion measured
                # across a venue outage is an excursion through a market nobody was trading.
                fwd = keep + bars_ahead
                aligned = np.zeros(n, dtype=bool)
                ok = fwd < len(full_close)
                aligned[ok] = (full_ts[fwd[ok]] - full_ts[keep[ok]]) == bars_ahead * meta["stepMs"]
                use = here_rows & aligned
                if use.any():
                    b, w, f = excursions(full_close, keep, bars_ahead, use)
                    bests.append(b[use])
                    worsts.append(w[use])
                    finals.append(f[use])
                    atrs.append(atr[offset:offset + n][use])
                offset += n

            if not bests:
                out[key] = {"rows": 0, "note": "no usable rows"}
                continue
            best = np.concatenate(bests)
            worst = np.concatenate(worsts)
            final = np.concatenate(finals)
            a = np.concatenate(atrs)
            good = np.isfinite(best) & np.isfinite(worst) & np.isfinite(final) & (a > 1e-9)
            best, worst, final, a = best[good], worst[good], final[good], a[good]
            if len(best) < 1000:
                out[key] = {"rows": int(len(best)), "note": "under 1000 rows, not reported"}
                continue

            # Everything in ATR units, and oriented by the direction that actually happened, so
            # "favourable" means the way the row went and not the way it rose.
            up = final > 0
            fav = np.where(up, best, -worst) / a
            adv = np.where(up, -worst, best) / a
            fin = np.abs(final) / a

            rows = {}
            for stop_m, target_m in CANDIDATES:
                # On the rows that ended the predicted way: did the target come before the stop?
                # Measured only where the direction was right, because that is the population a
                # direction call puts you in when it is right -- the unconditional number is this
                # times the model's accuracy, and is stated as such rather than blended in.
                hit_t = fav >= target_m
                hit_s = adv >= stop_m
                clean = hit_t & ~hit_s
                stopped = hit_s & ~hit_t
                both = hit_t & hit_s
                rows[f"{stop_m}/{target_m}"] = {
                    "stopAtr": stop_m,
                    "targetAtr": target_m,
                    "reachedTargetWithoutTouchingStop": round(float(clean.mean()), 5),
                    "stoppedWithoutReachingTarget": round(float(stopped.mean()), 5),
                    "touchedBoth": round(float(both.mean()), 5),
                    "neither": round(float((~hit_t & ~hit_s).mean()), 5),
                }

            def q(x: np.ndarray, p: float) -> float:
                return round(float(np.quantile(x, p)), 4)

            out[key] = {
                "rows": int(len(best)),
                "interval": interval,
                "barsAhead": bars_ahead,
                "minutesAhead": HORIZONS[key]["minutes"],
                "favourableExcursionAtr": {"p25": q(fav, .25), "median": q(fav, .5),
                                           "p75": q(fav, .75), "p90": q(fav, .90)},
                "adverseExcursionAtr": {"p25": q(adv, .25), "median": q(adv, .5),
                                        "p75": q(adv, .75), "p90": q(adv, .90)},
                "finalMoveAtr": {"median": q(fin, .5), "p75": q(fin, .75), "p90": q(fin, .90)},
                "medianAtrPctOfPrice": round(float(np.median(a)) * 100, 4),
                "pairs": rows,
            }
            m = out[key]
            print(f"   {key}: {len(best):,} rows  favourable median {m['favourableExcursionAtr']['median']}"
                  f" ATR  adverse median {m['adverseExcursionAtr']['median']} ATR"
                  f"  median ATR {m['medianAtrPctOfPrice']:.3f}% of price", flush=True)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Measure how far price travels over each window.")
    ap.add_argument("--horizons", nargs="*", default=ORDER)
    ap.add_argument("--tags", nargs="*", default=["btc", "crypto"],
                    help="families to measure. The per-coin lanes need their own excursions: "
                         "the backtest writes them a servedPair and nothing else, so "
                         "lib/cryptoLevels.bestPair finds no `pairs` table, returns null, and "
                         "the page shows a direction with no entry, stop or target")
    a = ap.parse_args()

    doc = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "producedBy": "tools/research/crypto_levels.py",
        "unit": "ATR(14) at the decision bar, as a fraction of price",
        "measuredOn": "the training and validation folds only; the test fold is not read here",
        "whatThisIsNot": [
            "Not a prediction. The brain predicts the sign of the forward return and nothing "
            "else; these distances are what the market has done, not what it will do.",
            "Not a backtest and not a profitability claim. No transaction cost, spread, funding "
            "or slippage is in any number here.",
            "The hit rates are measured on rows where the direction turned out correct. A "
            "direction is right about half the time, so the unconditional rate is lower and is "
            "not what these numbers say.",
        ],
        "candidates": [{"stopAtr": s, "targetAtr": t} for s, t in CANDIDATES],
        "families": {},
    }
    # The same pool and stride the lane was fitted on, read off its manifest. These distances are
    # not the model's output, but they are reported beside it, and measuring them over a different
    # set of rows than the model was trained on would make the two describe different markets.
    for tag in a.tags:
        print(f"== {tag}", flush=True)
        # Both intervals. The session horizons read the 4-hour corpus and were left out of the
        # first version of this file, which gave `crypto d20` a direction the page could not put
        # an entry, a stop or a target under -- a call with nowhere to act on it.
        here = {}
        for interval in ("5m", "4h"):
            keys = [k for k in a.horizons if HORIZONS[k]["interval"] == interval]
            if not keys:
                continue
            cfg_i = training_config(tag, keys[0])
            here.update(measure(tag, cfg_i["symbols"], cfg_i["stride"], keys))
        doc["families"][tag] = here
    # Merged into what is already there, and the served pair preserved.
    #
    # This file is regenerated per family now, and it also carries `servedPair` written by
    # crypto_backtest.py. Overwriting wholesale would drop every family not in this run and
    # every pair the sweep chose -- which is how the levels vanished from the page once already.
    OUT.parent.mkdir(parents=True, exist_ok=True)
    if OUT.exists():
        try:
            old = json.loads(OUT.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            old = {}
        merged = old.get("families", {})
        for fam, hz in doc["families"].items():
            for h, v in hz.items():
                prev = (merged.get(fam) or {}).get(h) or {}
                if prev.get("servedPair") and "servedPair" not in v:
                    v["servedPair"] = prev["servedPair"]
                merged.setdefault(fam, {})[h] = v
        doc["families"] = merged
    OUT.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
