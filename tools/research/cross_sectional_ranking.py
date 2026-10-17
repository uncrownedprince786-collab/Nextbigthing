"""Cross-sectional opportunity ranking: rank instruments within a date, not all into one class.

    python tools/research/cross_sectional_ranking.py [--dataset DIR] [--cache FILE] [--out FILE]

The registered experiment
-------------------------
Registered 2026-10-17, before any number from this run was seen. It is the pre-declared next
question after two negative results on the crypto slice: the recency/window sweep
(`stationarity.py` -> `stationarity.json`) and the point-in-time prior correction
(`prevalence_adjustment.py` -> `prevalence_adjustment.json`). Both assumed the 20-session
**three-class direction** task (`label20` UP/FLAT/DOWN) and both failed. This asks whether the
task itself was wrong: not "will this asset rise, flat or fall", but **"which assets will move
most, relative to their peers, over the next 20 sessions"**.

**Question.** Does ranking crypto instruments *within a decision date* carry out-of-sample
signal, where forcing every instrument into the same three-class directional call did not?

**Target.** The cross-sectional rank of `fwd20` (the percent change of the close over the next
20 stored sessions) among the day's eligible instruments. Continuous and decision-shaped: no
threshold, no class, and a positive rank IC is exactly "the score orders the day's instruments
the way the day turned out". `fwd20` is the outcome and is **never** a feature.

**Eligible assets and cross-section.** Crypto rows from the frozen examples-v4-context dataset
(`.cache/foundation/dataset_v4/*.jsonl.gz`) with `mature20` true and a present `fwd20`. A
decision date forms a cross-section only if it has at least `MIN_XSEC = 10` eligible
instruments; smaller dates are dropped, not padded.

**Features.** The same 44 `ALL_FEATURES` (base + macro + context), point-in-time as stored. Where
the context source has no value the cell is NaN, imputed from the **training** fold's column mean
only, and standardised on the training fold only -- standardising on the whole series would leak
the evaluation period's distribution into the fit.

**Walk-forward, leakage-safe.** Evaluation years 2023, 2024, 2025, 2026. For each year the cut is
the first decision date of the year; the training set is every row with decision date <=
`train_end`, where `train_end` is the 20th-last distinct decision date strictly before the cut.
The 20-decision-date embargo is the same overlap guard every prior experiment used: a 20-session
label means the last training rows and the first evaluation rows would otherwise share forward
sessions. Each score is fitted on the training rows only and ranks the evaluation year's rows
only, within their own dates.

Scores (each ranked within a date; nothing is fitted for the price-only ones):
* **rankModel** -- ridge regression on the 44 features -> predicted `fwd20`, fitted on the
  training rows. The cross-sectional candidate: it learns the feature-to-return map and ranks by
  it. Fixed ridge penalty `RIDGE_LAMBDA` (selected once, here, not searched).
* **directionModel** -- the existing failed setup, for the head-to-head: a 3-class softmax on
  `label20` (the same `fit_softmax`), fitted on the training rows, scored by `P(UP) - P(DOWN)`
  and ranked within the date. This is "forcing all assets into the 20-session three-class call".
* **momentum** -- score = `r20` (price only, no fit). The classic cross-sectional signal.
* **reversal** -- score = `-r20` (price only). The opposite prior.
* **random** -- a fixed-seed permutation of the momentum score (control; IC must sit at zero).

**Metrics, per evaluation year.**
* **mean rank IC** -- Spearman correlation of score against `fwd20` within each date, averaged
  over the year's dates. The primary metric.
* **long-short spread** -- mean over dates of (mean `fwd20` of the top decile - mean `fwd20` of
  the bottom decile), in percent.
* **hit rate** -- share of dates where the top decile's mean `fwd20` exceeds the bottom's.
* **top-decile turnover** -- mean share of top-decile names replaced from one date to the next,
  reported so the cost of chasing the ranking is visible (there is no execution layer in this
  project, so this measures ranking, not profit).
* **regime breakdown** -- dates split by the cross-sectional median `fwd20` (equal-weight market
  up vs down) with the mean IC in each, so a result that only holds in one direction is seen.
* **uncertainty** -- moving-block bootstrap over decision dates, 20-date blocks, 400 resamples,
  on the mean IC and on the long-short spread. Consecutive dates overlap heavily and same-day
  instruments are correlated, so resampling rows would understate the interval.

**Baselines.** `random` is the floor; `momentum` and `reversal` are the price-only baselines;
`directionModel` is the formulation being tested against.

**Rejection / progression criteria, fixed before the run.** Cross-sectional ranking counts as a
promising direction only if **all** hold:
(a) the best of {rankModel, momentum, reversal} has mean IC > 0 in **at least 3 of 4** years;
(b) that score's mean IC exceeds its bootstrap half-width (pooled mean IC > pooled mean half-width
    over the four years);
(c) that score's long-short spread is positive in **at least 3 of 4** years;
(d) it beats `directionModel`'s mean IC in **at least 3 of 4** years (the point of the test).
Failing any of (a)-(d) is a result: ranking *this way* on *this slice* is also negative, and the
next question moves to data/horizon (a different outcome window or a widened eligible set), not to
another score on the same rows.

**Promotion.** None under any outcome: every evaluation year is exposed (2023-2026 have all been
scored by prior experiments). This decides the next question, not what ships; a pristine
prospective window would still be required before any candidate.
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "tools" / "foundation"))

from baseline_experiment import CLASSES, EMBARGO, SEED, fit_softmax  # noqa: E402
from train_v2_context import ALL_FEATURES  # noqa: E402

DATASET = ROOT / ".cache" / "foundation" / "dataset_v4"
CACHE = ROOT / ".cache" / "foundation" / "ranking_slice.npz"
OUT = ROOT / "data" / "foundation" / "dataset" / "cross_sectional_ranking.json"

EVAL_YEARS = ("2023", "2024", "2025", "2026")
MIN_XSEC = 10            # fewest instruments in a date for the date to form a cross-section
RIDGE_LAMBDA = 1.0       # fixed once, here, not searched
BOOTSTRAP = 400
BLOCK_DAYS = 20
TOP_FRAC = 0.1
CHANCE = 0.5

CRITERIA = {
    "promisingIfAllHold": [
        "(a) best of {rankModel, momentum, reversal} has mean IC > 0 in >= 3 of 4 years",
        "(b) that score's mean IC exceeds its bootstrap half-width",
        "(c) that score's long-short spread is positive in >= 3 of 4 years",
        "(d) it beats directionModel's mean IC in >= 3 of 4 years",
    ],
    "failing": "ranking this way on this slice is negative; next question is data/horizon "
               "(a different outcome window or a widened eligible set), not another score",
    "setBefore": "any number from this run was seen (registered 2026-10-17)",
    "promotion": "none; every evaluation period is exposed and no artifact is promotable",
}


def build_cache(ds: Path, prefix: str = "examples-v4-context") -> dict:
    X, fwd, y, dates, syms = [], [], [], [], []
    for f in sorted(ds.glob(f"{prefix}-*.jsonl.gz")):
        with gzip.open(f, "rt", encoding="utf-8") as fh:
            for line in fh:
                r = json.loads(line)
                if r.get("assetType") != "crypto":
                    continue
                pit = r.get("pit") or {}
                p, o = pit.get("f"), r.get("outcome") or {}
                if not p or o.get("label20") not in CLASSES or not o.get("mature20"):
                    continue
                if o.get("fwd20") is None:
                    continue
                c = (pit.get("ctx") or {}).get("f") or {}
                row, ok = [], True
                for k in ALL_FEATURES:
                    v = p.get(k) if k in p else c.get(k)
                    if isinstance(v, str):
                        v = {"up": 1.0, "down": -1.0}.get(v, 0.0)
                    if v is None:
                        row.append(np.nan)
                        continue
                    try:
                        row.append(float(v))
                    except (TypeError, ValueError):
                        ok = False
                        break
                if not ok:
                    continue
                X.append(row)
                fwd.append(float(o["fwd20"]))
                y.append(CLASSES.index(o["label20"]))
                dates.append(r["asOf"])
                syms.append(r["symbol"])
    return {"X": np.asarray(X, dtype=np.float64), "fwd20": np.asarray(fwd, dtype=np.float64),
            "y": np.asarray(y, dtype=np.int64), "dates": np.asarray(dates), "syms": np.asarray(syms)}


def load(args) -> dict:
    cache = Path(args.cache)
    if cache.exists():
        z = np.load(cache, allow_pickle=True)
        d = {k: z[k] for k in ("X", "fwd20", "y", "dates", "syms")}
        print(f"loaded cached ranking slice: {len(d['X']):,} rows")
        return d
    print(f"reading crypto rows from {args.dataset} ...")
    d = build_cache(Path(args.dataset))
    cache.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(cache, **d)
    print(f"rows {len(d['X']):,}  cached to {cache}")
    return d


def spearman(a: np.ndarray, b: np.ndarray) -> float:
    """Rank correlation without scipy: average ranks, then Pearson on the ranks."""
    if len(a) < 2:
        return float("nan")
    ra = _rank(a)
    rb = _rank(b)
    ra = ra - ra.mean()
    rb = rb - rb.mean()
    denom = np.sqrt((ra * ra).sum() * (rb * rb).sum())
    return float((ra * rb).sum() / denom) if denom > 0 else float("nan")


def _rank(x: np.ndarray) -> np.ndarray:
    order = np.argsort(x, kind="stable")
    ranks = np.empty(len(x), dtype=np.float64)
    ranks[order] = np.arange(len(x), dtype=np.float64)
    # average ranks over ties
    sx = x[order]
    i = 0
    while i < len(sx):
        j = i
        while j + 1 < len(sx) and sx[j + 1] == sx[i]:
            j += 1
        if j > i:
            ranks[order[i:j + 1]] = (i + j) / 2.0
        i = j + 1
    return ranks


def per_date(dates_yr: np.ndarray, score: np.ndarray, fwd: np.ndarray,
             ids: np.ndarray) -> dict:
    """IC, long-short spread, hit and top-decile turnover, ranking within each date.

    All four inputs are restricted to one evaluation year, so `score` is the year's score
    vector in row order and `ids` is the instrument identity (symbol) for turnover.
    """
    uniq = np.unique(dates_yr)
    ics, spreads, hits, turns = [], [], [], []
    prev_top = None
    for d in uniq:
        sel = np.where(dates_yr == d)[0]
        if len(sel) < MIN_XSEC:
            continue
        s, f, iid = score[sel], fwd[sel], ids[sel]
        ics.append(spearman(s, f))
        k = max(1, int(round(len(sel) * TOP_FRAC)))
        order = np.argsort(-s, kind="stable")
        top = order[:k]
        bot = order[-k:]
        spreads.append(float(f[top].mean() - f[bot].mean()))
        hits.append(1.0 if f[top].mean() > f[bot].mean() else 0.0)
        top_names = set(iid[top].tolist())
        if prev_top is not None:
            turns.append(1.0 - len(top_names & prev_top) / len(top_names))
        prev_top = top_names
    ics = np.asarray(ics, dtype=np.float64)
    return {"dates": uniq, "ic": ics, "spread": np.asarray(spreads, dtype=np.float64),
            "hit": np.asarray(hits, dtype=np.float64),
            "turnover": float(np.mean(turns)) if turns else None}


def block_bootstrap(values: np.ndarray, rng, n=BOOTSTRAP) -> dict:
    """Interval for the mean of a per-date series, resampling blocks of consecutive dates."""
    m = len(values)
    if m < 3:
        return {"mean": round(float(np.mean(values)), 4) if m else None, "halfWidth": None}
    blocks = [np.arange(i, min(i + BLOCK_DAYS, m)) for i in range(0, m, BLOCK_DAYS)]
    means = []
    for _ in range(n):
        pick = rng.integers(0, len(blocks), size=len(blocks))
        sel = np.concatenate([blocks[b] for b in pick])
        means.append(float(values[sel].mean()))
    lo, hi = np.percentile(means, [2.5, 97.5])
    return {"mean": round(float(np.mean(values)), 4), "p2_5": round(float(lo), 4),
            "p97_5": round(float(hi), 4), "halfWidth": round(float((hi - lo) / 2), 4),
            "resamples": len(means), "blockDays": BLOCK_DAYS}


def standardise(Xtr, Xte):
    mu = np.nanmean(Xtr, axis=0)
    mu = np.where(np.isnan(mu), 0.0, mu)
    sd = np.nanstd(Xtr, axis=0)
    sd[sd == 0] = 1.0
    fill = lambda A: (np.where(np.isnan(A), mu, A) - mu) / sd
    return fill(Xtr), fill(Xte)


def fit_ridge(Xtr_z, ytr, lam=RIDGE_LAMBDA):
    n, d = Xtr_z.shape
    Xb = np.hstack([Xtr_z, np.ones((n, 1))])
    A = Xb.T @ Xb + lam * np.eye(d + 1)
    return np.linalg.solve(A, Xb.T @ ytr)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dataset", default=str(DATASET))
    ap.add_argument("--cache", default=str(CACHE))
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args()

    d = load(a)
    X, fwd, y, dates, syms = d["X"], d["fwd20"], d["y"], d["dates"], d["syms"]
    if X.shape[1] != len(ALL_FEATURES):
        raise SystemExit(f"cache has {X.shape[1]} columns, ALL_FEATURES has {len(ALL_FEATURES)}")
    order = np.argsort(dates, kind="stable")
    X, fwd, y, dates, syms = X[order], fwd[order], y[order], dates[order], syms[order]
    r20 = X[:, ALL_FEATURES.index("r20")]
    print(f"rows {len(X):,}  columns {X.shape[1]}  {dates[0]}..{dates[-1]}  "
          f"{len(set(syms.tolist()))} instruments")

    rng = np.random.default_rng(SEED)
    rng_shuffle = np.random.default_rng(SEED + 11)
    rng_boot = np.random.default_rng(SEED + 12)

    years = {}
    for yr in EVAL_YEARS:
        te = np.where(np.char.startswith(dates.astype(str), yr))[0]
        if len(te) < 200:
            continue
        cut = dates[te[0]]
        uniq_before = np.unique(dates[dates < cut])
        if len(uniq_before) <= EMBARGO:
            continue
        train_end = uniq_before[-EMBARGO - 1]
        tr = np.where(dates <= train_end)[0]

        Xtr_z, Xte_z = standardise(X[tr], X[te])

        # rankModel: ridge -> predicted fwd20
        W = fit_ridge(Xtr_z, fwd[tr])
        score_rank = np.hstack([Xte_z, np.ones((len(te), 1))]) @ W

        # directionModel: the existing failed setup
        Wc = fit_softmax(Xtr_z, y[tr])
        Zc = np.hstack([Xte_z, np.ones((len(te), 1))]) @ Wc
        score_dir = Zc[:, CLASSES.index("UP")] - Zc[:, CLASSES.index("DOWN")]

        score_mom = r20[te]
        score_rev = -r20[te]
        score_rand = score_mom[rng_shuffle.permutation(len(te))]

        scores = {"rankModel": score_rank, "directionModel": score_dir,
                  "momentum": score_mom, "reversal": score_rev, "random": score_rand}

        per = {}
        dates_yr, fwd_yr, syms_yr = dates[te], fwd[te], syms[te]
        for name, sc in scores.items():
            r = per_date(dates_yr, sc, fwd_yr, syms_yr)
            ics = r["ic"][~np.isnan(r["ic"])]
            # regime split by the equal-weight market's realized direction that date
            up_days, dn_days = [], []
            for di, dd in enumerate(r["dates"]):
                icd = r["ic"][di]
                if np.isnan(icd):
                    continue
                sel = np.where(dates_yr == dd)[0]
                (up_days if fwd_yr[sel].mean() > 0 else dn_days).append(icd)
            per[name] = {
                "meanIC": round(float(ics.mean()), 4) if len(ics) else None,
                "icBootstrap": block_bootstrap(ics, np.random.default_rng(SEED + 13)),
                "longShortSpread": round(float(r["spread"].mean()), 4) if len(r["spread"]) else None,
                "spreadBootstrap": block_bootstrap(r["spread"], np.random.default_rng(SEED + 14)),
                "hitRate": round(float(r["hit"].mean()), 4) if len(r["hit"]) else None,
                "topDecileTurnover": None if r["turnover"] is None else round(r["turnover"], 4),
                "datesRanked": int(len(r["ic"])),
                "icUpMarketDays": round(float(np.mean(up_days)), 4) if up_days else None,
                "icDownMarketDays": round(float(np.mean(dn_days)), 4) if dn_days else None,
            }
        xsec = np.array([int((dates[te] == dd).sum()) for dd in np.unique(dates[te])])
        years[yr] = {
            "evalRows": int(len(te)), "trainRows": int(len(tr)),
            "evalFrom": str(dates[te[0]]), "evalTo": str(dates[te[-1]]),
            "decisionDates": int(len(np.unique(dates[te]))),
            "crossSectionMedianSize": int(np.median(xsec)),
            "fwd20Mean": round(float(fwd[te].mean()), 4),
            "scores": per,
        }
        print(f"\n{yr}: eval {len(te):,} rows, {years[yr]['decisionDates']} dates, "
              f"median x-sec {years[yr]['crossSectionMedianSize']}, fwd20 mean {years[yr]['fwd20Mean']:+.3f}")
        for name in ("rankModel", "directionModel", "momentum", "reversal", "random"):
            p = per[name]
            hw = (p["icBootstrap"] or {}).get("halfWidth")
            print(f"  {name:<15} IC {p['meanIC']:+.4f} +/-{hw}  L/S {p['longShortSpread']:+.3f}  "
                  f"hit {p['hitRate']}  turn {p['topDecileTurnover']}")

    # --- criteria ---------------------------------------------------------------------------
    def yearly(score_name, key):
        return [(yr, years[yr]["scores"][score_name].get(key)) for yr in EVAL_YEARS
                if yr in years]

    candidates = ("rankModel", "momentum", "reversal")
    best, best_ic_wins, best_mean_ic, best_mean_hw = None, -1, None, None
    for c in candidates:
        ics = [v for _, v in yearly(c, "meanIC") if v is not None]
        wins = sum(1 for v in ics if v > 0)
        mean_ic = round(float(np.mean(ics)), 4) if ics else None
        hws = [(years[yr]["scores"][c]["icBootstrap"] or {}).get("halfWidth") for yr in EVAL_YEARS
               if yr in years]
        hws = [h for h in hws if h is not None]
        mean_hw = round(float(np.mean(hws)), 4) if hws else None
        if wins > best_ic_wins:
            best, best_ic_wins, best_mean_ic, best_mean_hw = c, wins, mean_ic, mean_hw
    spread_wins = sum(1 for _, v in yearly(best, "longShortSpread") if v is not None and v > 0)
    dir_ics = dict(yearly("directionModel", "meanIC"))
    best_ics = dict(yearly(best, "meanIC"))
    beat_dir = sum(1 for yr, v in best_ics.items()
                   if v is not None and dir_ics.get(yr) is not None and v > dir_ics[yr])
    crit_a = best_ic_wins >= 3
    crit_b = best_mean_ic is not None and best_mean_hw is not None and best_mean_ic > best_mean_hw
    crit_c = spread_wins >= 3
    crit_d = beat_dir >= 3
    holds = crit_a and crit_b and crit_c and crit_d

    verdict = (
        f"cross-sectional ranking is promising on this slice: {best} clears all criteria"
        if holds else
        f"cross-sectional ranking is negative on this slice: {best} fails the criteria; next "
        "question is the outcome window or the eligible set, not another score on the same rows")

    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "version": "cross-sectional-ranking-v1",
        "registeredIn": "this file's docstring, 2026-10-17, before any run",
        "question": "does ranking crypto instruments within a date carry out-of-sample signal "
                    "where the 20-session three-class direction task did not",
        "target": "cross-sectional rank of fwd20 within each decision date; fwd20 never a feature",
        "slice": "crypto rows of the frozen examples-v4-context dataset; same slice as "
                 "stationarity.json and prevalence_adjustment.json",
        "minCrossSection": MIN_XSEC, "ridgeLambda": RIDGE_LAMBDA, "embargoDecisionDates": EMBARGO,
        "uncertainty": f"moving-block bootstrap over decision dates, {BLOCK_DAYS}-date blocks, "
                       f"{BOOTSTRAP} resamples",
        "preDeclaredCriteria": CRITERIA,
        "byEvaluationYear": years,
        "criteria": {
            "bestCandidate": best,
            "(a) mean IC > 0 in >=3 of 4 years": {"holds": crit_a, "yearsPositive": best_ic_wins},
            "(b) mean IC > mean half-width": {"holds": crit_b, "meanIC": best_mean_ic,
                                              "meanHalfWidth": best_mean_hw},
            "(c) long-short spread positive in >=3 of 4 years": {"holds": crit_c,
                                                                 "yearsPositive": spread_wins},
            "(d) beats directionModel IC in >=3 of 4 years": {"holds": crit_d, "yearsBeating": beat_dir},
            "allHold": holds,
        },
        "verdict": verdict,
        "exposure": "every evaluation period here has been scored before; exploratory evidence "
                    "only, never confirmatory, and nothing is promotable from it",
    }
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(payload, indent=1), encoding="utf-8")
    print(f"\ncriteria: {json.dumps(payload['criteria'], indent=1)}")
    print(f"\n{verdict}")
    print(f"wrote {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
