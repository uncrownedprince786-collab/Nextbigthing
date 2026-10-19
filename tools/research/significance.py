"""Whether a measured lift is bigger than the noise in the measurement.

The gate this was written for
-----------------------------
`train_v4_markets.py` asked `accuracy > majority` and called the answer GO. Measured on
2026-10-19, the Commodity candidate scored **0.4438** against a holdout majority share of
**0.4410** on 1,424 rows. That is four more correct answers than always naming the commonest
class, and the standard error of a proportion at that rate and that sample is **0.0132** -- so the
lift is **0.21 standard errors**, which is the number you get from a coin that is not biased. The
gate reported GO. Three of the other four markets scored *below* their own baseline and were
correctly refused, so the gate was not broken in general; it was simply unable to tell a real
difference from a small one, and a difference that small has no direction.

A gate that passes noise is worse than no gate, because its output is a sentence with the word
GO in it. `brain.md` thinking principle 3 says a sample size decides how much weight a reading
earns and is never left unstated, and principle 8 says a thin reading said plainly beats a
confident one that cannot be checked. This file is those two principles as arithmetic.

What is tested, and why each test is the one it is
--------------------------------------------------
* **Against a fixed baseline rate** (the holdout majority share): a one-sided normal
  approximation to the binomial. The baseline here is a constant computed from the holdout
  labels, not a second set of predictions, so there are no pairs to match and the ordinary
  one-sample proportion test is the right one.
* **Against another model scored on the same rows** (the price-only model): McNemar's test on
  the discordant pairs. Both models answer the *same* holdout rows, so their errors are
  correlated and treating the two accuracies as independent samples would understate the noise.
  Only the rows where the two disagree carry information about which is better, which is exactly
  what McNemar counts.

Both are one-sided at 95% (`Z_95`), because the question is only ever "is the candidate better",
never "is it different". Both use a normal approximation rather than an exact test: scipy is not
a dependency of this project and the approximation is accurate at the sample sizes here
(hundreds to thousands of rows). Where a sample is too small for the approximation to mean
anything, the result says so rather than returning a verdict -- `enoughData` is false and the
test does not pass.

Nothing here decides whether a model is promoted. It decides whether a number is evidence.
"""

from __future__ import annotations

import math

#: One-sided 95%: the 0.95 quantile of the standard normal. A promotion gate asks a directional
#: question, so the whole 5% sits in the tail being tested rather than being split across two.
Z_95 = 1.645

#: Below this many trials the normal approximation to the binomial is not trustworthy, and a
#: verdict computed from it would be a decimal place pretending to be evidence. The usual rule of
#: thumb is that `n * p` and `n * (1 - p)` both exceed 5; at the baseline rates this project sees
#: (0.36 to 0.73) 30 trials clears that comfortably and still refuses the genuinely tiny samples.
MIN_TRIALS = 30


def binomial_lift(correct: int, n: int, baseline: float, z: float = Z_95) -> dict:
    """Does `correct/n` beat the fixed rate `baseline` by more than sampling noise?

    `baseline` is a rate, not a second set of predictions -- the holdout majority share, or any
    other constant the candidate has to clear. The standard error is computed **under the null**
    (at `baseline`, not at the observed accuracy), which is what a hypothesis test does: the
    question is how surprising this result would be if the candidate were really no better.

    Returns the whole calculation, not just the verdict, so a manifest records why a candidate
    passed or failed rather than only that it did.
    """
    if n <= 0:
        return {"accuracy": None, "baseline": round(float(baseline), 4), "n": 0,
                "enoughData": False, "passes": False,
                "why": "no holdout rows, so there is nothing to test"}
    accuracy = correct / n
    p0 = float(baseline)
    # A degenerate baseline (every holdout row one class) has no variance to compare against.
    if not 0.0 < p0 < 1.0:
        return {"accuracy": round(accuracy, 4), "baseline": round(p0, 4), "n": int(n),
                "enoughData": False, "passes": False,
                "why": f"the baseline rate is {p0:.4f}, which leaves nothing to beat"}
    se = math.sqrt(p0 * (1.0 - p0) / n)
    threshold = p0 + z * se
    enough = n >= MIN_TRIALS
    passes = bool(enough and accuracy > threshold)
    lift = accuracy - p0
    return {
        "accuracy": round(accuracy, 4),
        "baseline": round(p0, 4),
        "n": int(n),
        "lift": round(lift, 4),
        "standardError": round(se, 4),
        # How many standard errors the lift is worth. This is the number that makes a 0.0028
        # difference on 1,424 rows legible: 0.21, not "above".
        "z": round(lift / se, 2) if se > 0 else None,
        "requiredAccuracy": round(threshold, 4),
        "zRequired": z,
        "enoughData": enough,
        "passes": passes,
        "why": (
            f"{accuracy:.4f} vs a {p0:.4f} baseline on {n} rows is {lift / se:.2f} standard "
            f"errors; {'clears' if passes else 'does not clear'} the {threshold:.4f} needed at "
            f"one-sided {z}" if enough else
            f"only {n} holdout rows, under the {MIN_TRIALS} this approximation needs"
        ),
    }


def mcnemar(only_candidate_right: int, only_other_right: int, z: float = Z_95) -> dict:
    """Is the candidate better than a model scored on the *same* rows?

    `only_candidate_right` (b) counts the rows the candidate got right and the other got wrong;
    `only_other_right` (c) is the reverse. Rows where both agree carry no information about which
    is better and are deliberately not counted -- that is the whole point of the paired test.

    A continuity correction is applied, which makes the test slightly conservative. For a gate
    that decides whether to call something evidence, erring toward "not yet" is the right
    direction to err in.
    """
    b, c = int(only_candidate_right), int(only_other_right)
    discordant = b + c
    if discordant == 0:
        return {"onlyCandidateRight": b, "onlyOtherRight": c, "discordant": 0,
                "enoughData": False, "passes": False,
                "why": "the two models answered every holdout row the same way"}
    enough = discordant >= MIN_TRIALS
    # Signed, continuity-corrected. |b - c| - 1 floors at 0 so a one-row difference cannot be
    # turned into a negative numerator and read as significance in the wrong direction.
    corrected = max(abs(b - c) - 1, 0)
    stat = corrected / math.sqrt(discordant)
    signed = stat if b >= c else -stat
    passes = bool(enough and b > c and signed > z)
    return {
        "onlyCandidateRight": b,
        "onlyOtherRight": c,
        "discordant": discordant,
        "z": round(signed, 2),
        "zRequired": z,
        "enoughData": enough,
        "passes": passes,
        "why": (
            f"the candidate was right where the other was wrong on {b} rows and wrong where it "
            f"was right on {c}; z = {signed:.2f} against the {z} needed"
            if enough else
            f"only {discordant} rows separate the two models, under the {MIN_TRIALS} this "
            f"approximation needs"
        ),
    }
