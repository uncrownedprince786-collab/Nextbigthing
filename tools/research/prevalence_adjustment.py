"""Prevalence-adjusted scoring: point-in-time label-shift correction on the all-history fits.

    python tools/research/prevalence_adjustment.py [--cache FILE] [--out FILE]

The registered experiment
-------------------------
Registered in `BRAIN-CORPUS-COVERAGE-2026-10-17.md` section 10 on 2026-10-17, before any number
from this run was seen. The recency-vs-history experiment (`stationarity.py`, verdict in
`stationarity.json`) found that no shorter training window helps and named its own mechanism:
the model learns its training period's class lean and that lean becomes a liability exactly when
the mix shifts - prevalence shift, not window length. This experiment targets that mechanism
directly, on the same slice, with the same walk-forward protocol.

**Hypothesis.** Correcting the fitted model's class priors at scoring time - using prevalence
estimated point-in-time from recently *matured* outcomes - recovers out-of-sample separation
that the unadjusted fit destroys when the class mix shifts, without discarding any training
rows (which is what windowing did, and why it failed).

**Method (fixed before any number from this run is seen).**
* Same everything as `stationarity.py`: crypto slice from `.cache/foundation/crypto_slice.npz`
  (93,452 rows, 76 instruments), `ALL_FEATURES` (44), `fit_softmax`/`predict` from
  `baseline_experiment.py`, same SEED, 20-session embargo, walk-forward evaluation years
  2023-2026.
* Base model: the all-history fit per evaluation year, refitted deterministically and
  cross-checked against the metrics recorded in `stationarity.json` before the adjustment is
  applied (fidelity guard: any mismatch beyond rounding aborts the run).
* Adjustment (see the sign note below): for each class k, add `log(pi_recent,k / pi_train,k)`
  to the fitted logit before argmax - the standard label-shift prior correction (the training
  fit's intercept already encodes pi_train; the correction re-centres it on the recent prior).
  `pi_train` = class shares of that year's training rows. `pi_recent` = class shares of
  outcomes **matured as of the cut**: rows whose decision date is <= cut - 20 sessions (their
  20-session outcome had resolved), measured over the trailing 365 decision dates. Point-in-time
  by construction - only outcomes that had already resolved are visible to the adjustment, and
  the evaluation year's own rows are never consulted.
* Variant count: **one**. One pi_recent window (365 decision dates), fixed here. No sweep; a
  sweep would be the windowing experiment's mistake in a new place.

Pre-run resolution of a discrepancy in the registration prose
--------------------------------------------------------------
The registration sentence reads "subtract log(pi_recent/pi_train) from the fitted logit margin
before argmax (standard label-shift prior correction)". Subtracting that ratio is the *inverse*
of the standard correction; the parenthetical names the actual standard method (add log
pi_recent, subtract log pi_train - Lipton et al. 2018; Saerens et al. 2002). Implementing the
literal subtraction would be an anti-correction that pushes the prediction mix *toward* the
training lean when the world shifts away from it - the opposite of the registered hypothesis.
This script implements the **standard (add) form**, per the parenthetical. This choice was
written into the script before any result was computed, and is recorded in the output JSON so
the executed variant is unambiguous. No other element of the registration was altered.

Baselines (registered)
----------------------
(1) Unadjusted all-history fit per year (the recorded stationarity numbers, re-verified).
(2) That year's majority class. (3) Paired shuffled-label control at the same width and row
count: the labels of the matured pre-cut population are permuted (fixed seed) and the trailing
window's shares recomputed from the permuted labels, so the placebo correction has the same
structure and scale but carries no point-in-time prevalence information - any advantage the
real correction has over it is attributable to the real prevalence signal, not to the act of
shifting logits. (Permuting *within* the window would leave class counts invariant and make
the control a tautology; that was the first implementation, caught on the first run because
real-minus-shuffled was identically zero in every resample, and corrected before the reported
run. The criteria (a)-(c) never depended on the control.)
(4) The completed 18m-window result - cited for context from `stationarity.json`, never rerun.

Metrics (registered)
--------------------
Per year: adjusted minus unadjusted out-of-sample accuracy, each against its own year's
majority; predicted class mix (degeneracy guard: the unadjusted model predicted 0 FLAT rows in
every year); per-class recall/precision for both variants; predicted mass moved (how many rows
the correction actually flipped). Mean advantage across the four years. Real-minus-shuffled.
In-sample-to-OOS gap (the correction is an identity on its own training rows by construction -
pi_train against pi_train - so the adjusted in-sample equals the unadjusted in-sample).
Uncertainty: the same moving-block bootstrap over decision dates, 20-date blocks, 400
resamples (imported from `stationarity.py` so the implementation is identical, not similar).

Rejection criteria (fixed in the registration, before any run)
--------------------------------------------------------------
Prevalence adjustment counts as a mechanism only if **all three** hold:
(a) it beats the unadjusted all-history model in at least **3 of 4** evaluation years;
(b) the mean advantage across years **exceeds the bootstrap half-width** - resolved before the
    run as: mean of the four per-year (adjusted minus unadjusted) advantages > mean of the four
    per-year bootstrap half-widths;
(c) 2025's deficit improves by more than its own half-width **without** any of the three
    balanced years (2023, 2024, 2026) degrading beyond theirs - resolved before the run as:
    2025 advantage > halfWidth_2025 AND no balanced-year advantage < -halfWidth of that year.
Failing any of (a)-(c) is itself the result - "the lean is not correctable from recently
matured outcomes" - and the next registered hypothesis is **cross-sectional ranking**.

**Promotion.** None under any outcome: every evaluation year is exposed (2023-2026 have all
been scored by prior experiments). This experiment decides which question is asked next, not
what is shipped; a pristine prospective window would still be required before any candidate.
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
sys.path.insert(0, str(ROOT / "tools" / "foundation"))

from baseline_experiment import CLASSES, EMBARGO, SEED, fit_softmax, predict  # noqa: E402
from stationarity import BLOCK_DAYS, BOOTSTRAP, block_bootstrap, over_majority  # noqa: E402
from train_v2_context import ALL_FEATURES  # noqa: E402

CACHE = ROOT / ".cache" / "foundation" / "crypto_slice.npz"
OUT = ROOT / "data" / "foundation" / "dataset" / "prevalence_adjustment.json"
STATIONARITY = ROOT / "data" / "foundation" / "dataset" / "stationarity.json"

EVAL_YEARS = ("2023", "2024", "2025", "2026")
RECENT_WINDOW_DATES = 365      # pi_recent window, in trailing matured decision dates, registered
RNG_SHUFFLE = SEED + 1         # paired shuffled-label control, fixed before the run
RNG_BOOT_UNADJ = SEED + 2      # adjusted vs unadjusted bootstrap
RNG_BOOT_SHUF = SEED + 3       # adjusted vs shuffled-adjusted bootstrap

SIGN_RESOLUTION = (
    "registration prose said 'subtract log(pi_recent/pi_train)' while naming the operation "
    "'(standard label-shift prior correction)'; the two are inverses. The standard form "
    "(add log(pi_recent/pi_train) to the class logits) was implemented per the parenthetical, "
    "chosen and recorded in the script before any number from this run was seen. A literal "
    "subtraction would push the prediction mix toward the training lean when the world shifts "
    "away from it - the opposite of the registered hypothesis."
)

CRITERIA = {
    "allThreeMustHold": [
        "(a) beats unadjusted all-history in at least 3 of 4 evaluation years",
        "(b) mean advantage across years exceeds the bootstrap half-width: resolved before the "
            "run as mean(per-year advantage) > mean(per-year halfWidth)",
        "(c) 2025's advantage exceeds its own halfWidth, and no balanced year (2023/2024/2026) "
            "degrades below -halfWidth of that year",
    ],
    "failingAny": "the lean is not correctable from recently matured outcomes -> next "
                  "registered hypothesis is cross-sectional ranking",
    "setBefore": "any number from this run was seen (BRAIN-CORPUS-COVERAGE-2026-10-17.md section 10)",
    "promotion": "none; every evaluation period is exposed and no artifact is promotable",
}


def recent_prior(d_ord, y, dates, train_end):
    """pi_recent: class shares over the trailing RECENT_WINDOW_DATES matured decision dates.

    Matured = decision date <= train_end (= cut - EMBARGO decision dates, stationarity's
    embargo construction): by the cut, those rows' 20-session outcomes had resolved. Only
    already-matured outcomes are visible; the evaluation year's own rows are never consulted.
    """
    matured = np.where(d_ord <= train_end)[0]
    uniq = np.unique(d_ord[matured])
    if len(uniq) == 0:
        raise SystemExit("no matured decision dates before the cut")
    keep = uniq[-RECENT_WINDOW_DATES:]
    sel = matured[np.isin(d_ord[matured], keep)]
    shares = np.array([(y[sel] == i).mean() for i in range(len(CLASSES))])
    return shares, len(sel), len(keep), str(dates[sel[0]]), str(dates[sel[-1]])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cache", default=str(CACHE))
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args()

    z = np.load(a.cache, allow_pickle=True)
    X, y, dates = z["X"], z["y"], z["dates"]
    if X.shape[1] != len(ALL_FEATURES):
        raise SystemExit(f"cache has {X.shape[1]} columns, ALL_FEATURES has {len(ALL_FEATURES)}")
    o = np.argsort(dates, kind="stable")
    X, y, dates = X[o], y[o], dates[o]
    d_ord = np.array([datetime.fromisoformat(d).toordinal() for d in dates])
    print(f"rows {len(X):,}  columns {X.shape[1]}  {dates[0]}..{dates[-1]}")

    recorded = json.loads(STATIONARITY.read_text(encoding="utf-8"))["byEvaluationYear"]

    years = {}
    for yr in EVAL_YEARS:
        te = np.where(np.char.startswith(dates.astype(str), yr))[0]
        if len(te) < 500:
            continue
        cut = d_ord[te[0]]
        uniq_before = np.unique(d_ord[d_ord < cut])
        if len(uniq_before) <= EMBARGO:
            continue
        train_end = uniq_before[-EMBARGO - 1]
        tr = np.where(d_ord <= train_end)[0]

        # One fit, one standardisation - identical to stationarity's "all" window.
        Xtr, Xte = X[tr], X[te]
        mu = np.nanmean(Xtr, axis=0)
        mu = np.where(np.isnan(mu), 0.0, mu)
        Xtr = np.where(np.isnan(Xtr), mu, Xtr)
        Xte = np.where(np.isnan(Xte), mu, Xte)
        sd = Xtr.std(axis=0)
        sd[sd == 0] = 1.0
        W = fit_softmax((Xtr - mu) / sd, y[tr])

        z_tr = np.hstack([(Xtr - mu) / sd, np.ones((len(tr), 1))]) @ W
        z_te = np.hstack([(Xte - mu) / sd, np.ones((len(te), 1))]) @ W
        yp_unadj = z_te.argmax(axis=1)
        yp_tr = z_tr.argmax(axis=1)

        # Fidelity guard: the refit must reproduce the recorded all-history numbers.
        rec = recorded[yr]["windows"]["all"]
        acc, maj, over = over_majority(y[te], yp_unadj)
        mix = {c: int((yp_unadj == i).sum()) for i, c in enumerate(CLASSES)}
        if abs(acc - rec["accuracy"]) > 5e-4 or mix != rec["predictedMix"]:
            raise SystemExit(
                f"{yr}: refit does not reproduce stationarity.json "
                f"(acc {acc} vs {rec['accuracy']}, mix {mix} vs {rec['predictedMix']})")

        pi_train = np.array([(y[tr] == i).mean() for i in range(len(CLASSES))])
        pi_rec, n_rec, n_dates, rec_from, rec_to = recent_prior(d_ord, y, dates, train_end)
        if (pi_train == 0).any():
            raise SystemExit(f"{yr}: pi_train has a zero class share {pi_train}")
        with np.errstate(divide="ignore"):
            shift = np.log(pi_rec) - np.log(pi_train)          # standard label-shift correction
        z_adj = z_te + np.where(np.isfinite(shift), shift, 0.0)
        # pi_recent of 0 (log -> -inf) means no matured evidence of that class: the class logit
        # is driven to -inf. Applied exactly, not clipped, by zeroing its logit instead.
        for k in range(len(CLASSES)):
            if pi_rec[k] == 0:
                z_adj[:, k] = -np.inf
        yp_adj = z_adj.argmax(axis=1)

        # Paired shuffled-label control: permute the labels of the matured pre-cut population,
        # then take the trailing-window shares of the permuted labels - same window width and
        # row count as the real correction, but the window's label composition is a placebo
        # draw rather than the point-in-time prevalence. (The first run of this control
        # permuted *within* the window, which leaves class counts invariant and makes the
        # shuffled pi identical to the real pi by construction - a tautology, caught because
        # real-minus-shuffled came out exactly 0.0 in every resample. Criteria (a)-(c) do not
        # depend on the control; they compare adjusted against unadjusted only.)
        rng = np.random.default_rng(RNG_SHUFFLE)
        matured = np.where(d_ord <= train_end)[0]
        uniq = np.unique(d_ord[matured])
        keep = uniq[-RECENT_WINDOW_DATES:]
        win = matured[np.isin(d_ord[matured], keep)]
        y_shuf = y.copy()
        y_shuf[matured] = rng.permutation(y[matured])
        pi_shuf = np.array([(y_shuf[win] == i).mean() for i in range(len(CLASSES))])
        with np.errstate(divide="ignore"):
            shift_shuf = np.log(pi_shuf) - np.log(pi_train)
        z_shuf = z_te + np.where(np.isfinite(shift_shuf), shift_shuf, 0.0)
        for k in range(len(CLASSES)):
            if pi_shuf[k] == 0:
                z_shuf[:, k] = -np.inf
        yp_shuf = z_shuf.argmax(axis=1)

        def per_class(yp):
            out = {}
            for i, c in enumerate(CLASSES):
                m, pm = y[te] == i, yp == i
                out[c] = {
                    "recall": round(float((yp[m] == i).mean()), 4) if m.any() else None,
                    "precision": round(float((y[te][pm] == i).mean()), 4) if pm.any() else None,
                    "predicted": int(pm.sum()),
                }
            return out

        i_acc, i_maj, i_over = over_majority(y[tr], yp_tr)
        adj_acc, adj_maj, adj_over = over_majority(y[te], yp_adj)
        shuf_acc, _, shuf_over = over_majority(y[te], yp_shuf)
        boot = block_bootstrap(dates[te], y[te], yp_adj, yp_unadj,
                               np.random.default_rng(RNG_BOOT_UNADJ))
        boot_shuf = block_bootstrap(dates[te], y[te], yp_adj, yp_shuf,
                                    np.random.default_rng(RNG_BOOT_SHUF))

        years[yr] = {
            "evalRows": int(len(te)), "trainRows": int(len(tr)),
            "classShare": {c: round(float((y[te] == i).mean()), 4)
                           for i, c in enumerate(CLASSES)},
            "piTrain": {c: round(float(pi_train[i]), 4) for i, c in enumerate(CLASSES)},
            "piRecent": {c: round(float(pi_rec[i]), 4) for i, c in enumerate(CLASSES)},
            "piRecentFrom": rec_from, "piRecentTo": rec_to,
            "piRecentRows": int(n_rec), "piRecentDecisionDates": int(n_dates),
            "logShift": {c: (round(float(np.log(pi_rec[i]) - np.log(pi_train[i])), 4)
                             if pi_rec[i] > 0 else "-inf (class absent from recent window)")
                         for i, c in enumerate(CLASSES)},
            "unadjusted": {"accuracy": acc, "majority": maj, "overMajority": over,
                           "predictedMix": mix},
            "adjusted": {"accuracy": adj_acc, "majority": adj_maj, "overMajority": adj_over,
                         "predictedMix": {c: int((yp_adj == i).sum())
                                          for i, c in enumerate(CLASSES)},
                         "perClass": per_class(yp_adj)},
            "shuffledControl": {"accuracy": shuf_acc, "overMajority": shuf_over,
                                "piRecentShuffled": {c: round(float(pi_shuf[i]), 4)
                                                     for i, c in enumerate(CLASSES)}},
            "rowsFlipped": int((yp_adj != yp_unadj).sum()),
            "adjustedVsUnadjustedBootstrap": boot,
            "adjustedVsShuffledBootstrap": boot_shuf,
            "inSampleOnTrainingRows": {"accuracy": i_acc, "majority": i_maj,
                                       "overMajority": i_over,
                                       "note": "the correction is an identity on its own "
                                               "training rows (pi_train against pi_train), so "
                                               "adjusted in-sample equals unadjusted in-sample"},
            "inSampleToOOSgapAdjusted": round(i_over - adj_over, 4),
        }
        adv = round(adj_over - over, 4)
        print(f"\n{yr}: adj over {adj_over:+.4f} vs unadj {over:+.4f}  advantage {adv:+.4f}  "
              f"flipped {years[yr]['rowsFlipped']:,}  boot +/-"
              f"{(boot.get('halfWidth') if boot.get('halfWidth') is not None else float('nan')):.4f}")
        print(f"  piTrain {years[yr]['piTrain']}  piRecent {years[yr]['piRecent']}")
        print(f"  mix unadj {mix} -> adj {years[yr]['adjusted']['predictedMix']}")

    # Criteria evaluation, fixed definitions only.
    advs, hws = [], {}
    for yr in EVAL_YEARS:
        d = years.get(yr)
        if not d:
            continue
        adv = d["adjusted"]["overMajority"] - d["unadjusted"]["overMajority"]
        hw = (d["adjustedVsUnadjustedBootstrap"] or {}).get("halfWidth")
        advs.append((yr, round(adv, 4), hw))
        hws[yr] = hw
    wins = sum(1 for _, adv, _ in advs if adv > 0)
    mean_adv = round(float(np.mean([adv for _, adv, _ in advs])), 4)
    hw_vals = [hw for _, _, hw in advs if hw is not None]
    mean_hw = round(float(np.mean(hw_vals)), 4) if hw_vals else None
    crit_a = wins >= 3
    crit_b = (mean_hw is not None) and (mean_adv > mean_hw)
    adv_2025 = next((adv for yr, adv, _ in advs if yr == "2025"), None)
    hw_2025 = hws.get("2025")
    balanced_degrade = [yr for yr, adv, hw in advs
                        if yr != "2025" and hw is not None and adv < -hw]
    crit_c = (adv_2025 is not None and hw_2025 is not None
              and adv_2025 > hw_2025 and not balanced_degrade)
    holds = crit_a and crit_b and crit_c

    verdict = (
        "prevalence adjustment works: the mechanism named by the closed recency experiment is "
        "correctable at scoring time" if holds else
        "prevalence adjustment fails: the lean is not correctable from recently matured "
        "outcomes - next registered hypothesis is cross-sectional ranking")

    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "version": "prevalence-adjustment-v1",
        "registeredIn": "BRAIN-CORPUS-COVERAGE-2026-10-17.md section 10, before any run",
        "signResolution": SIGN_RESOLUTION,
        "controlNote": "the shuffled-label control permutes labels across the matured pre-cut "
                       "population, then takes the trailing window's shares (same width, same "
                       "row count). The first run permuted within the window, which leaves "
                       "class counts invariant - real-minus-shuffled was identically 0.0 in "
                       "every resample, a tautology. Corrected before the reported run; "
                       "criteria (a)-(c) compare adjusted vs unadjusted only and are "
                       "unaffected either way.",
        "slice": "crypto, from the examples-v4-context cache; same slice as stationarity.json",
        "recentWindowDecisionDates": RECENT_WINDOW_DATES,
        "maturityRule": "only rows whose decision date is <= cut - 20 sessions (outcome had "
                        "resolved by the cut) are visible to pi_recent; the evaluation year's "
                        "own rows are never consulted",
        "embargoSessions": EMBARGO,
        "uncertainty": f"moving-block bootstrap over decision dates, {BLOCK_DAYS}-date blocks, "
                       f"{BOOTSTRAP} resamples, identical implementation imported from "
                       "stationarity.py",
        "preDeclaredCriteria": CRITERIA,
        "byEvaluationYear": years,
        "criteria": {
            "(a) beats unadjusted in >=3 of 4 years": {"holds": crit_a, "wins": wins,
                                                       "perYear": [[y, a] for y, a, _ in advs]},
            "(b) mean advantage > mean halfWidth": {"holds": crit_b, "meanAdvantage": mean_adv,
                                                    "meanHalfWidth": mean_hw},
            "(c) 2025 clears its halfWidth, balanced years do not degrade beyond theirs":
                {"holds": crit_c, "advantage2025": adv_2025, "halfWidth2025": hw_2025,
                 "balancedYearsDegrading": balanced_degrade},
            "allThreeHold": holds,
        },
        "citedNotRerun": "the completed 18m-window result in stationarity.json "
                         "(overMajority -0.0327 in 2025, no year clear of the interval)",
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
