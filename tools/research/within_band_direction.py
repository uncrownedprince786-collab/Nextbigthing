"""Is there a usable direction inside the band, where the model says FLAT?

The question
------------
The validated US five-session model is fitted at a 2.0% label band: UP means "up at least 2% in
five sessions", DOWN means down at least that, and FLAT means **the move did not clear the band**.
FLAT is therefore a statement about *magnitude*, not about direction. On 2026-10-20 the model
called FLAT on 89 of 271 US instruments, and the site showed those 89 as having no direction at
all -- which reads to a user as "we have nothing", when what the model actually said was "we do
not expect a big move".

Those are different claims, and the second one still leaves a direction question open. A stock
expected to drift up 0.8% is not directionless; it is a weak long.

What is measured
----------------
On the holdout the model never saw, restricted to the rows it calls FLAT, does

    sign(P(UP) - P(DOWN))

predict the **sign of the realised return** better than the honest constant -- always naming
whichever sign was commonest among the training fold's FLAT rows? That constant is the comparator
because it is the one a person could actually have run on the morning; the within-session majority
is an oracle, and using it was the error `validate_lift.py` documents.

Nothing here widens the band, re-labels anything, or drops rows to make a number. The band stays
2.0%; the population is exactly the rows the served artifact calls FLAT; rows whose realised
return is exactly zero are excluded because they have no sign to predict, and they are counted and
reported rather than quietly dropped.

The arithmetic is the project's own: `significance.binomial_lift` against the fixed baseline rate,
`significance.mcnemar` pairing candidate against baseline on the same rows, and the date-blocked
bootstrap from `validate_lift` so overlapping five-session windows and a market that moves
together on a given day are not mistaken for independent evidence.

Promotion
---------
This script decides nothing. It writes `within_band_direction.json` and prints a verdict. A
direction only reaches the site through the registry, and only if the lower bound of the
bootstrap interval is above zero after Bonferroni adjustment -- and then as LOW confidence, which
is what a sub-band drift honestly is.
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "tools" / "foundation"))
sys.path.insert(0, str(ROOT / "tools"))

import significance  # noqa: E402
import train_v4_markets as tv  # noqa: E402
import validate_lift as vl  # noqa: E402
from baseline_experiment import CLASSES, EMBARGO  # noqa: E402

OUT = ROOT / "data" / "foundation" / "dataset" / "within_band_direction.json"
BRAIN_ROOT = ROOT / "data" / "foundation" / "brain"

#: 0 = DOWN, 1 = UP. A two-class sub-task over the rows the three-class model calls FLAT.
SIDES = ("DOWN", "UP")

#: Below this many signed FLAT holdout rows the question is not answerable, and saying so is the
#: honest output. Chosen before looking: the paired test needs discordant pairs, not just rows.
MIN_ROWS = 200


def holdout_split(dates: np.ndarray, train_end: str) -> tuple[np.ndarray, np.ndarray]:
    """The trainer's own split, restated over sorted dates: embargoed train, then holdout.

    Reproduced rather than imported because `fit_market` computes it inline and also fits; this
    needs the indices without refitting, since the point is to score the artifact that is served.
    """
    udates = np.unique(dates)
    didx = {d: i for i, d in enumerate(udates)}
    pos = np.asarray([didx[d] for d in dates])
    after = [d for d in udates if d > train_end]
    if not after:
        raise SystemExit(f"no session after {train_end}")
    cut = didx[after[0]]
    return np.where(pos < (cut - EMBARGO))[0], np.where(dates > train_end)[0]


def evaluate(market: str, horizon: int, band_scale: float, ds: Path, train_end: str,
             draws: int, arms: int, brain_root: Path | None = None) -> dict:
    """Measure one (market, horizon, band) arm. `brain_root` is injectable so the band guard
    below can be tested against a deliberately mislabelled artifact without one existing in the
    repository."""
    model_version = tv.artifact_name(market, horizon, band_scale)
    brain_dir = (brain_root or BRAIN_ROOT) / model_version
    if not (brain_dir / "model.json").exists():
        raise SystemExit(f"no artifact at {brain_dir}; train it before measuring it")
    model = tv.load_model(brain_dir)
    # The band the artifact was actually fitted at, not the one asked for on the command line.
    # This is the 2026-10-20 defect in miniature: a measurement attributed to the wrong model.
    man = json.loads((brain_dir / "manifest.json").read_text(encoding="utf-8"))
    if float(man["task"]["bandScale"]) != float(band_scale):
        raise SystemExit(f"{model_version} was fitted at {man['task']['bandScale']}x, not "
                         f"{band_scale}x; measuring it as the latter would misattribute the result")

    per = tv.load(ds, horizon=horizon, band_scale=band_scale)
    b = per[market]
    if not b["rows"]:
        raise SystemExit(f"no {market} rows in {ds}")
    order = np.argsort(b["dates"], kind="stable")
    X, dates, fwd = b["X"][order], b["dates"][order], b["fwd"][order]
    tr, te = holdout_split(dates, train_end)

    flat = CLASSES.index("FLAT")
    up, down = CLASSES.index("UP"), CLASSES.index("DOWN")

    def flat_rows(idx: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """The rows the served artifact calls FLAT, and the margin P(UP) - P(DOWN) on them.

        Scores are logits; the softmax is monotone in each coordinate's difference, so the sign of
        (logit_UP - logit_DOWN) is the sign of (P(UP) - P(DOWN)). No exponentials needed, and
        none taken, so nothing overflows on an extreme row.
        """
        S = tv.predict_matrix(model, X[idx])
        is_flat = S.argmax(axis=1) == flat
        return idx[is_flat], (S[is_flat, up] - S[is_flat, down])

    tr_flat, _ = flat_rows(tr)
    te_flat, margin = flat_rows(te)

    # The comparator, fixed before the holdout is looked at: whichever sign was commoner among the
    # training fold's own FLAT rows. Held constant across every session and every resample.
    tr_sign = np.sign(fwd[tr_flat])
    tr_up = int((tr_sign > 0).sum())
    tr_down = int((tr_sign < 0).sum())
    baseline_side = 1 if tr_up >= tr_down else 0
    baseline_from_train = tr_up / max(tr_up + tr_down, 1)

    te_sign = np.sign(fwd[te_flat])
    # A realised return of exactly zero has no sign to predict. Counted, not hidden.
    nonzero = te_sign != 0
    zeros = int((~nonzero).sum())
    rows = te_flat[nonzero]
    margin, te_sign = margin[nonzero], te_sign[nonzero]
    n = int(len(rows))
    if n < MIN_ROWS:
        return {"market": market, "horizonSessions": horizon, "bandScale": band_scale,
                "modelVersion": model_version, "verdict": "INSUFFICIENT",
                "why": f"only {n} FLAT holdout rows carry a signed return", "n": n}

    truth = (te_sign > 0).astype(np.int64)           # 1 = UP, 0 = DOWN
    # A margin of exactly zero cannot name a side; it is sent to the baseline rather than to a
    # coin, so the candidate is never credited with a guess it did not make.
    cand = np.where(margin > 0, 1, np.where(margin < 0, 0, baseline_side)).astype(np.int64)
    base = np.full(n, baseline_side, dtype=np.int64)
    dts = dates[rows]

    cand_right, base_right = cand == truth, base == truth
    acc = float(cand_right.mean())
    base_acc = float(base_right.mean())

    # Three tests, because each one answers a different objection.
    maj = significance.binomial_lift(int(cand_right.sum()), n, base_acc)
    paired = significance.mcnemar(int((cand_right & ~base_right).sum()),
                                  int((~cand_right & base_right).sum()))
    per_date = vl.lift_by_date(cand, truth, dts, baseline_side)
    point, lifts = vl.blocked_bootstrap(per_date, draws)
    se = float(lifts.std(ddof=1))
    lo, hi = (float(np.percentile(lifts, 2.5)), float(np.percentile(lifts, 97.5)))
    z = point / se if se > 0 else 0.0
    # Share of resamples at or below zero, doubled for a two-sided read, then Bonferroni over the
    # arms searched to get here. Reported raw as well, so the adjustment is visible rather than
    # buried.
    p_raw = float(2.0 * min((lifts <= 0).mean(), (lifts >= 0).mean()))
    p_adj = min(1.0, p_raw * max(arms, 1))

    # The gate: the interval's lower bound above zero, the paired test passing, and the adjusted
    # p-value still significant. Any one of these failing means no direction is served.
    passes = bool(lo > 0 and paired.get("passes") and p_adj < 0.05)

    # What the direction would look like if served: how many of the FLAT rows get each side, and
    # the median absolute move, which is the magnitude claim that goes beside it.
    served_up = int((cand == 1).sum())

    # The *other* claim, measured separately, which is the whole point of the exercise. A FLAT
    # call asserts a magnitude -- "this will not move 2% either way in five sessions". That is a
    # falsifiable statement and it deserves its own number, because the direction result above
    # says nothing about whether it holds. Precision: of the rows called FLAT, how many really
    # stayed inside the band. Compared against the rate at which *any* row stays inside it, so a
    # model that calls FLAT on everything gets no credit for the market being mostly quiet.
    threshold = float(man["task"]["labelThresholdPct"])
    inside_called = np.abs(fwd[te_flat]) < threshold
    inside_all = np.abs(fwd[te]) < threshold
    mag_precision = float(inside_called.mean()) if len(te_flat) else 0.0
    mag_base = float(inside_all.mean()) if len(te) else 0.0
    mag_test = significance.binomial_lift(int(inside_called.sum()), int(len(te_flat)), mag_base)
    magnitude = {
        "claim": f"the move stays inside +/-{threshold}% over {horizon} sessions",
        "thresholdPct": threshold,
        "precisionOnRowsCalledFlat": round(mag_precision, 4),
        "rateAcrossAllHoldoutRows": round(mag_base, 4),
        "lift": round(mag_precision - mag_base, 4),
        "test": mag_test,
        "holds": bool(mag_test.get("passes")),
    }
    return {
        "market": market, "horizonSessions": horizon, "bandScale": band_scale,
        "modelVersion": model_version,
        "artifactSha256": man["artifact"]["sha256"],
        "population": "holdout rows the served artifact classifies FLAT, with a non-zero return",
        "trainFlatRows": int(len(tr_flat)), "holdoutFlatRows": int(len(te_flat)),
        "zeroReturnRowsExcluded": zeros, "n": n,
        "baseline": {"side": SIDES[baseline_side],
                     "shareInTrainFold": round(baseline_from_train, 4),
                     "accuracyOnHoldout": round(base_acc, 4)},
        "candidate": {"rule": "sign(P(UP) - P(DOWN)) among FLAT rows",
                      "accuracy": round(acc, 4),
                      "predictedUp": served_up, "predictedDown": n - served_up},
        "lift": round(acc - base_acc, 4),
        "medianAbsMovePct": round(float(np.median(np.abs(fwd[rows]))), 4),
        "magnitude": magnitude,
        "tests": {
            "vsFixedBaseline": maj,
            "pairedAgainstBaseline": paired,
            "blockedBootstrap": {"lift": round(point, 4), "se": round(se, 4), "z": round(z, 2),
                                 "ci95": [round(lo, 4), round(hi, 4)],
                                 "sessions": len(per_date), "draws": draws,
                                 "pRaw": round(p_raw, 5), "armsSearched": arms,
                                 "pBonferroni": round(p_adj, 5)},
        },
        "verdict": "GO" if passes else "NO-GO",
        "confidenceIfServed": "LOW",
        "why": ("a sub-band drift is a weak claim by construction, so it is served as LOW or not "
                "at all; nothing here licenses MEDIUM or HIGH"),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--market", default="US")
    ap.add_argument("--horizon", type=int, default=5)
    ap.add_argument("--band-scale", type=float, default=2.0)
    ap.add_argument("--dataset", type=Path, default=tv.DEFAULT_DS)
    ap.add_argument("--train-end", default=tv.TRAIN_END)
    ap.add_argument("--boot", type=int, default=2000)
    ap.add_argument("--arms", type=int, default=1,
                    help="arms searched before this one, for the Bonferroni adjustment")
    ap.add_argument("--out", type=Path, default=OUT)
    a = ap.parse_args()

    r = evaluate(a.market, a.horizon, a.band_scale, a.dataset, a.train_end, a.boot, a.arms)
    a.out.write_text(json.dumps(r, indent=2) + "\n", encoding="utf-8")

    print(f"{r['modelVersion']}  within-band direction, {r['market']} h{r['horizonSessions']} "
          f"at {r['bandScale']}x")
    if r["verdict"] == "INSUFFICIENT":
        print(f"  {r['why']}")
        print(f"  -> {r['verdict']}")
        return 0
    print(f"  FLAT rows: {r['trainFlatRows']} train, {r['holdoutFlatRows']} holdout "
          f"({r['zeroReturnRowsExcluded']} with a zero return excluded), n = {r['n']}")
    print(f"  baseline : always {r['baseline']['side']}  "
          f"{r['baseline']['accuracyOnHoldout']:.4f} "
          f"({r['baseline']['shareInTrainFold']:.4f} of the train fold)")
    print(f"  candidate: {r['candidate']['accuracy']:.4f}  "
          f"({r['candidate']['predictedUp']} up / {r['candidate']['predictedDown']} down)  "
          f"lift {r['lift']:+.4f}")
    bs = r["tests"]["blockedBootstrap"]
    print(f"  blocked bootstrap over {bs['sessions']} sessions: SE {bs['se']:.4f}  "
          f"z {bs['z']:.2f}  95% CI [{bs['ci95'][0]:+.4f}, {bs['ci95'][1]:+.4f}]")
    print(f"  p {bs['pRaw']:.5f} raw, {bs['pBonferroni']:.5f} over {bs['armsSearched']} arm(s); "
          f"paired {'passes' if r['tests']['pairedAgainstBaseline'].get('passes') else 'fails'}")
    m = r["magnitude"]
    print(f"  magnitude: {m['claim']}")
    print(f"    holds on {m['precisionOnRowsCalledFlat']:.4f} of the rows called FLAT, against "
          f"{m['rateAcrossAllHoldoutRows']:.4f} across all holdout rows (lift {m['lift']:+.4f}) "
          f"-> {'holds' if m['holds'] else 'does not hold'}")
    print(f"  median absolute move {r['medianAbsMovePct']:.2f}% -- the magnitude beside the side")
    print(f"  -> {r['verdict']}" + ("  (would be served as LOW)" if r["verdict"] == "GO" else ""))
    print(f"  wrote {a.out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
