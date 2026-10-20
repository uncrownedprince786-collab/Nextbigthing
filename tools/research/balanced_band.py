"""A label band each market can actually be trained on, derived from the training fold alone.

Why
---
Four of five markets have artifacts and no validated lane, and the band is the reason. The shared
rule scales a 2.0% threshold by sqrt(horizon/20), so every market is judged against the same
number -- and a 2.0% move over five sessions means something entirely different in each:

    market     holdout rows inside +/-2.0%   what the model learned to predict
    FX                      0.9361           FLAT, on 100.0% of rows
    Crypto                  0.4161           DOWN, on 98.0% of rows
    PK                      0.3831           UP,   on 75.1% of rows

FX barely moves 2% in a week, so "will it move 2%" has one sensible answer and the model gives it.
That is not a model failing to read direction; it is a question with no information in it. Crypto
has the opposite problem at the same threshold.

The rule
--------
The band is the **33.3rd percentile of |forward return| within the training fold**, per market, so
each of DOWN / FLAT / UP holds about a third of the training rows.

Three properties make this a labelling decision rather than a search:

1. It is computed from the training fold only -- the same embargoed split the trainer uses -- so
   the holdout plays no part in choosing it.
2. It is a quantile of the return distribution, not a function of any model's accuracy. Nothing
   here is tuned against a score, so there is no arm to adjust for.
3. It is fixed before the fit and recorded in the manifest, so the claim the model makes is
   stated in the artifact rather than inferred.

This is the opposite of exploiting class imbalance: it removes the imbalance that let FX score
0.9361 by answering FLAT to everything. It does not make the claim stronger -- a 0.4% band on FX
is a *weaker* statement than a 2.0% one, and the band is reported in percent beside every result
so nobody can mistake the two. Accuracy against a balanced three-class problem is also not
comparable to accuracy against a 94%-FLAT one, which is exactly why the comparator here is each
market's own holdout majority share under its own band, recomputed, and never the old number.

What it does not do
-------------------
Promote anything. It writes `balanced_band_markets.json` and prints per-market verdicts under the
project's existing gates (`significance.binomial_lift` against the holdout majority,
`significance.mcnemar` against the price-only model on the same rows, non-degeneracy, and both
directions recalled). A lane reaches the site only through `signal_validation.py`, and only after
`validate_lift.py` has tested it the hard way.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "tools" / "foundation"))
sys.path.insert(0, str(ROOT / "tools"))

import significance  # noqa: E402
import train_v4_markets as tv  # noqa: E402
from baseline_experiment import CLASSES, EMBARGO, FEATURES, metrics  # noqa: E402
from shadow_markets import MARKETS  # noqa: E402
from train_v1 import degeneracy  # noqa: E402
from train_v2_context import ALL_FEATURES, fit_and_score  # noqa: E402

OUT = ROOT / "data" / "foundation" / "dataset" / "balanced_band_markets.json"

#: The share of training rows the band aims to put in FLAT. A third, so all three classes carry
#: comparable weight. Stated as a constant because it is a pre-registered choice, not a parameter.
FLAT_SHARE = 1.0 / 3.0

#: Floors, because a band can be too small to mean anything. Below this the "move" is inside the
#: spread for most instruments and the label is noise dressed as a class.
MIN_BAND_PCT = 0.10


def split_indices(dates: np.ndarray, train_end: str) -> tuple[np.ndarray, np.ndarray]:
    """The trainer's embargoed chronological split."""
    udates = np.unique(dates)
    didx = {d: i for i, d in enumerate(udates)}
    pos = np.asarray([didx[d] for d in dates])
    after = [d for d in udates if d > train_end]
    if not after:
        return np.asarray([], dtype=int), np.asarray([], dtype=int)
    cut = didx[after[0]]
    return np.where(pos < (cut - EMBARGO))[0], np.where(dates > train_end)[0]


def band_from_train_fold(fwd_train: np.ndarray) -> float:
    """The threshold that puts about a third of the training fold inside the band.

    A quantile of |return|, so it is symmetric by construction: the same number bounds UP and
    DOWN, and a market whose returns are skewed does not get a band that leans one way.
    """
    return float(max(np.quantile(np.abs(fwd_train), FLAT_SHARE), MIN_BAND_PCT))


def label_at(fwd: np.ndarray, band_pct: float) -> np.ndarray:
    """Class indices under an explicit percentage band, in the project's class order."""
    up, down, flat = CLASSES.index("UP"), CLASSES.index("DOWN"), CLASSES.index("FLAT")
    y = np.full(len(fwd), flat, dtype=np.int64)
    y[fwd >= band_pct] = up
    y[fwd <= -band_pct] = down
    return y


def fit_one(market: str, b: dict, train_end: str, horizon: int) -> dict:
    X, dates, fwd = b["X"], b["dates"], b["fwd"]
    order = np.argsort(dates, kind="stable")
    X, dates, fwd = X[order], dates[order], fwd[order]
    tr, te = split_indices(dates, train_end)
    if len(tr) < tv.MIN_TRAIN_ROWS or len(te) < tv.MIN_HOLDOUT_ROWS:
        return {"market": market, "trained": False,
                "reason": f"below the data floor (train {len(tr)}, holdout {len(te)})",
                "rows": int(len(fwd))}

    # Chosen here, on the training fold, before the holdout is touched.
    band_pct = band_from_train_fold(fwd[tr])
    y = label_at(fwd, band_pct)
    train_mix = {c: round(float((y[tr] == i).mean()), 4) for i, c in enumerate(CLASSES)}

    price_cols = [ALL_FEATURES.index(f) for f in FEATURES]
    _, yp_price, _ = fit_and_score(X, y, tr, te, price_cols)
    _, yp, _ = fit_and_score(X, y, tr, te, list(range(len(ALL_FEATURES))))

    yt = y[te]
    m, m_price = metrics(yt, yp), metrics(yt, yp_price)
    majority = float(max((yt == i).mean() for i in range(len(CLASSES))))
    deg = degeneracy(yp, yt)
    collapse = tv.collapse_analysis(yt, yp)

    maj_test = significance.binomial_lift(int((yp == yt).sum()), int(len(yt)), majority)
    right, right_price = (yp == yt), (yp_price == yt)
    paired = significance.mcnemar(int((right & ~right_price).sum()),
                                  int((~right & right_price).sum()))
    checks = {
        "accuracyAboveHoldoutMajority": [m["accuracy"], round(majority, 4), maj_test["passes"],
                                         maj_test],
        "beatsThePriceOnlyModel": [m["accuracy"], m_price["accuracy"], paired["passes"], paired],
        "notDegenerate": [deg["degenerate"], False, not deg["degenerate"]],
        "bothDirectionsPredicted": [
            {"DOWN": m.get("recall_DOWN"), "UP": m.get("recall_UP")}, 0.2,
            bool((m.get("recall_DOWN") or 0) >= 0.2 and (m.get("recall_UP") or 0) >= 0.2)],
    }
    return {
        "market": market, "trained": True,
        "bandPct": round(band_pct, 4),
        "bandChosenFrom": f"the {FLAT_SHARE:.3f} quantile of |fwd{horizon}| in the training fold",
        "trainClassMix": train_mix,
        "rows": int(len(y)), "trainRows": int(len(tr)), "holdoutRows": int(len(te)),
        "holdoutSessions": int(len(set(dates[te].tolist()))),
        "accuracy": m["accuracy"], "holdoutMajorityShare": round(majority, 4),
        "priceOnlyAccuracy": m_price["accuracy"],
        "balancedAccuracy": round(float(np.mean([
            float((yp[yt == i] == i).mean()) if int((yt == i).sum()) else 0.0
            for i in range(len(CLASSES))])), 4),
        "recall": {c: m.get(f"recall_{c}") for c in CLASSES},
        "predictedMix": collapse["predictedShare"],
        "collapse": collapse,
        "checks": checks,
        "verdict": "GO" if all(v[2] for v in checks.values()) else "NO-GO",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--horizon", type=int, default=5)
    ap.add_argument("--dataset", type=Path, default=tv.DEFAULT_DS)
    ap.add_argument("--train-end", default=tv.TRAIN_END)
    ap.add_argument("--markets", nargs="*", default=list(MARKETS))
    ap.add_argument("--out", type=Path, default=OUT)
    a = ap.parse_args()

    # Any band loads the same `fwd`; the labels this run uses are derived below, not read.
    per = tv.load(a.dataset, horizon=a.horizon, band_scale=1.0)
    results = {}
    for market in a.markets:
        b = per.get(market)
        if not b or not b["rows"]:
            results[market] = {"market": market, "trained": False, "reason": "no rows"}
            continue
        results[market] = fit_one(market, b, a.train_end, a.horizon)

    doc = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "producedBy": "tools/research/balanced_band.py",
        "horizonSessions": a.horizon,
        "trainEnd": a.train_end,
        "embargoSessions": EMBARGO,
        "bandRule": (f"per market, the {FLAT_SHARE:.3f} quantile of |forward return| in the "
                     f"training fold, floored at {MIN_BAND_PCT}%"),
        "whyNotTheSharedBand": ("a single 2.0% band puts 93.6% of FX rows in FLAT and the model "
                                "answers FLAT to everything; the band, not the model, was the "
                                "limit"),
        "comparability": ("accuracy under a per-market band is not comparable to accuracy under "
                          "the shared band, and neither is comparable across markets; each is "
                          "read against its own holdout majority share"),
        "promotionRule": ("nothing here is promoted; a lane reaches the site only through "
                          "signal_validation.py after validate_lift.py"),
        "markets": results,
    }
    a.out.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")

    print(f"balanced band, horizon {a.horizon}, train end {a.train_end}")
    for market, r in results.items():
        if not r.get("trained"):
            print(f"  {market:10s} not trained -- {r.get('reason')}")
            continue
        c = r["checks"]
        print(f"  {market:10s} band +/-{r['bandPct']:.2f}%  "
              f"acc {r['accuracy']:.4f} vs majority {r['holdoutMajorityShare']:.4f} "
              f"({'pass' if c['accuracyAboveHoldoutMajority'][2] else 'fail'})  "
              f"price-only {r['priceOnlyAccuracy']:.4f} "
              f"({'pass' if c['beatsThePriceOnlyModel'][2] else 'fail'})  "
              f"balanced {r['balancedAccuracy']:.4f}  -> {r['verdict']}")
        print(f"             predicted {r['predictedMix']}  train mix {r['trainClassMix']}")
    print(f"  wrote {a.out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
