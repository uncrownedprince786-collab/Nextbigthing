"""Cost-aware, leakage-guarded walk-forward evaluation of trading rules.

    from walkforward import make_folds, evaluate, TrialLog, deflated_sharpe

This is evaluation infrastructure and nothing else. It trains no model, writes to no database and
changes no live rule. A rule is a plain function from one dataset record to -1 (short), 0 (stay
out) or +1 (long), optionally with a `fit` step that may only look at the training fold.

What it enforces, because each of these is how backtests lie:

* **Purge and embargo.** A training example whose outcome window reaches into the test period is
  a leak. `make_folds` removes every training date within `horizon + embargo` sessions of the test
  start, and `assert_no_overlap` re-checks the result so a bug in the first cannot hide.
* **Costs.** Every trade is charged the round trip from `tools/costs.py` under the low, base and
  high scenarios, with borrow for shorts, and a short in a market that forbids one is not
  counted rather than counted for free. A rule is reported at all three.
* **Controls.** `buy_and_hold` and `random_sign` run through the same folds and costs; a rule that
  does not beat both has found nothing.
* **Multiple testing.** Every evaluation is appended to a `TrialLog`, and the deflated Sharpe
  ratio discounts the best result by the number of trials, their dispersion, and the skew and
  kurtosis of the returns (Bailey and López de Prado, 2014).
* **Honest sample size.** Outcomes over `horizon` sessions overlap, so the effective number of
  independent trades is divided by the horizon, and the interval is a bootstrap over whole dates,
  not over rows, because rows on one date share one market move.

Records are the ones `tools/make_dataset.py` writes: `asOf`, `symbol`, `assetType`, `market`,
`candidate{...}` and `outcome{fwd1, fwd5, fwd20, ...}` with forward returns in percent.
"""

from __future__ import annotations

import json
import math
import random
import statistics
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable, Iterable

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from costs import SCENARIOS, round_trip_cost, NO_RETAIL_SHORT_MARKETS  # noqa: E402

Record = dict
Rule = Callable[[Record], int]

# Fields that describe the future. They may exist on a record under `outcome` and nowhere else; a
# feature with one of these names is a leak by construction.
FUTURE_NAMES = ("fwd", "mfe", "mae", "label", "outcome", "entryhit", "stophit", "netr", "grossr")


class LeakageError(AssertionError):
    pass


# ---------------------------------------------------------------- folds


@dataclass(frozen=True)
class Fold:
    train: tuple[str, ...]
    test: tuple[str, ...]


def make_folds(dates: Iterable[str], *, train_min: int, test_len: int, horizon: int,
               embargo: int = 5, step: int | None = None, rolling: int | None = None) -> list[Fold]:
    """Walk-forward folds over sorted session dates.

    Expanding by default (`rolling=None`), or a fixed-length trailing window with `rolling=N`.
    Training dates inside `horizon + embargo` sessions before the test start are dropped.
    """
    ds = sorted(set(dates))
    if train_min < 1 or test_len < 1 or horizon < 1:
        raise ValueError("train_min, test_len and horizon must be positive")
    step = step or test_len
    gap = horizon + embargo
    out: list[Fold] = []
    start = train_min
    while start + test_len <= len(ds):
        test = ds[start:start + test_len]
        train_end = start - gap
        if train_end > 0:
            lo = 0 if rolling is None else max(0, train_end - rolling)
            train = ds[lo:train_end]
            if train:
                out.append(Fold(tuple(train), tuple(test)))
        start += step
    for f in out:
        assert_no_overlap(f, ds, horizon, embargo)
    return out


def assert_no_overlap(fold: Fold, all_dates: list[str], horizon: int, embargo: int = 0) -> None:
    """The last training outcome window must close before the first test date, with room to spare."""
    idx = {d: i for i, d in enumerate(all_dates)}
    last_train, first_test = idx[fold.train[-1]], idx[fold.test[0]]
    if last_train + horizon + embargo >= first_test:
        raise LeakageError(f"training date {fold.train[-1]} has an outcome window that reaches "
                           f"the test period starting {fold.test[0]}")
    if set(fold.train) & set(fold.test):
        raise LeakageError("a date is in both the training and the test fold")


def assert_features_are_past_only(records: Iterable[Record]) -> None:
    """No feature may carry a future-looking name. Outcomes live under `outcome` only."""
    for r in records:
        for k in (r.get("candidate") or {}):
            if any(k.lower().startswith(n) for n in FUTURE_NAMES):
                raise LeakageError(f"candidate field {k!r} looks like an outcome")
        extra = [k for k in r if any(k.lower().startswith(n) for n in FUTURE_NAMES) and k != "outcome"]
        if extra:
            raise LeakageError(f"record carries future-looking top-level fields {extra}")


# ---------------------------------------------------------------- returns and costs


def trade_net_pct(rec: Record, side: int, horizon: int, scenario: str) -> float | None:
    """Net percent return of one trade, or None when it cannot be priced or was not mature."""
    if side == 0:
        return None
    fwd = (rec.get("outcome") or {}).get(f"fwd{horizon}")
    if fwd is None:
        return None
    short = side < 0
    if short and rec.get("market") in NO_RETAIL_SHORT_MARKETS:
        return None
    cost = round_trip_cost(1.0, rec["assetType"], scenario, short=short, sessions=horizon)
    return side * float(fwd) - 100.0 * cost


# ---------------------------------------------------------------- rules and controls


def buy_and_hold(rec: Record) -> int:
    return 1


def random_sign(seed: int = 1) -> Rule:
    """A coin per (symbol, date), reproducible and independent of order."""
    def rule(rec: Record) -> int:
        return 1 if random.Random(f"{seed}|{rec['symbol']}|{rec['asOf']}").random() < 0.5 else -1
    return rule


def setup_state(rec: Record) -> int:
    """The reconstructed setup's own direction, for judging the setup stage."""
    s = (rec.get("candidate") or {}).get("setupState")
    return 1 if s == "buy" else -1 if s == "short" else 0


# ---------------------------------------------------------------- statistics


def _phi(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def _phi_inv(p: float) -> float:
    """Inverse normal CDF (Acklam's rational approximation, accurate to about 1e-9)."""
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00, 3.754408661907416e+00]
    if not 0 < p < 1:
        raise ValueError("p must be in (0, 1)")
    if p < 0.02425:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p > 1 - 0.02425:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    q = p - 0.5
    r = q * q
    return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)


def moments(xs: list[float]) -> tuple[float, float, float, float]:
    n = len(xs)
    m = sum(xs) / n
    sd = math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1)) if n > 1 else 0.0
    if sd == 0:
        return m, 0.0, 0.0, 3.0
    skew = sum(((x - m) / sd) ** 3 for x in xs) / n
    kurt = sum(((x - m) / sd) ** 4 for x in xs) / n
    return m, sd, skew, kurt


def deflated_sharpe(sr: float, n_obs: int, skew: float, kurt: float, n_trials: int,
                    trial_sr_var: float | None = None) -> float:
    """Probability that the true Sharpe exceeds what the best of `n_trials` would show by luck.

    `sr` is the per-observation Sharpe of the selected rule, `trial_sr_var` the variance of the
    per-observation Sharpe across all trials (defaults to the sampling variance 1/n_obs when the
    log holds too few to estimate it). Returns a probability; 0.95 is the usual bar.
    """
    if n_obs < 3:
        return float("nan")
    n = max(1, n_trials)
    var = trial_sr_var if trial_sr_var and trial_sr_var > 0 else 1.0 / n_obs
    gamma = 0.5772156649015329
    sr0 = 0.0 if n == 1 else math.sqrt(var) * ((1 - gamma) * _phi_inv(1 - 1 / n)
                                               + gamma * _phi_inv(1 - 1 / (n * math.e)))
    denom = math.sqrt(max(1e-12, 1 - skew * sr + (kurt - 1) / 4 * sr * sr))
    return _phi((sr - sr0) * math.sqrt(n_obs - 1) / denom)


def block_bootstrap_mean(by_date: dict[str, list[float]], *, reps: int = 2000, seed: int = 7) -> tuple[float, float]:
    """95% interval of the mean trade return, resampling whole dates with replacement."""
    keys = sorted(by_date)
    if len(keys) < 2:
        return float("nan"), float("nan")
    rng = random.Random(seed)
    means = []
    for _ in range(reps):
        pick = [by_date[keys[rng.randrange(len(keys))]] for _ in keys]
        flat = [x for g in pick for x in g]
        if flat:
            means.append(sum(flat) / len(flat))
    means.sort()
    return means[int(0.025 * len(means))], means[int(0.975 * len(means)) - 1]


# ---------------------------------------------------------------- trial log


class TrialLog:
    """Every evaluation, appended as it happens, so the multiple-testing count cannot be forgotten."""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else None
        self.trials: list[dict] = []
        if self.path and self.path.exists():
            self.trials = [json.loads(l) for l in self.path.read_text(encoding="utf-8").splitlines() if l.strip()]

    def add(self, name: str, spec: dict, per_obs_sharpe: float, n_obs: int) -> None:
        t = {"name": name, "spec": spec, "perObsSharpe": per_obs_sharpe, "nObs": n_obs}
        self.trials.append(t)
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(t) + "\n")

    @property
    def count(self) -> int:
        return len(self.trials)

    def sharpe_variance(self) -> float | None:
        s = [t["perObsSharpe"] for t in self.trials if t["perObsSharpe"] == t["perObsSharpe"]]
        return statistics.variance(s) if len(s) >= 3 else None


# ---------------------------------------------------------------- evaluation


def evaluate(records: list[Record], rule: Rule, *, name: str, horizon: int = 20, train_min: int = 250,
             test_len: int = 60, embargo: int = 5, rolling: int | None = None,
             fit: Callable[[list[Record]], Rule] | None = None, log: TrialLog | None = None,
             seed: int = 7) -> dict:
    """Run `rule` through purged walk-forward folds and report it net of costs at three scenarios.

    If `fit` is given it is called once per fold with the training records only and must return the
    rule to use on that fold's test records; otherwise `rule` is used as is.
    """
    assert_features_are_past_only(records)
    dates = sorted({r["asOf"] for r in records})
    folds = make_folds(dates, train_min=train_min, test_len=test_len, horizon=horizon,
                       embargo=embargo, rolling=rolling)
    if not folds:
        raise ValueError("not enough dates for even one fold at these settings")
    by_date: dict[str, list[Record]] = {}
    for r in records:
        by_date.setdefault(r["asOf"], []).append(r)

    per_scn: dict[str, list[float]] = {s: [] for s in SCENARIOS}
    by_date_net: dict[str, list[float]] = {}
    gross: list[float] = []
    skipped_unpriceable = immature = 0
    for f in folds:
        use = rule
        if fit is not None:
            train = [r for d in f.train for r in by_date.get(d, [])]
            use = fit(train)
        for d in f.test:
            for r in by_date.get(d, []):
                side = use(r)
                if side == 0:
                    continue
                fwd = (r.get("outcome") or {}).get(f"fwd{horizon}")
                if fwd is None:
                    immature += 1
                    continue
                nets = {s: trade_net_pct(r, side, horizon, s) for s in SCENARIOS}
                if any(v is None for v in nets.values()):
                    skipped_unpriceable += 1
                    continue
                gross.append(side * float(fwd))
                for s in SCENARIOS:
                    per_scn[s].append(nets[s])
                by_date_net.setdefault(d, []).append(nets["base"])

    n = len(gross)
    out: dict = {"name": name, "horizon": horizon, "folds": len(folds), "trades": n,
                 "skippedUnpriceable": skipped_unpriceable, "immature": immature,
                 "testDates": sum(len(f.test) for f in folds)}
    if n < 3:
        out["verdict"] = "not enough trades to say anything"
        return out
    eff_n = max(1.0, n / horizon)
    m, sd, skew, kurt = moments(per_scn["base"])
    per_obs_sr = m / sd if sd else 0.0
    lo, hi = block_bootstrap_mean(by_date_net, seed=seed)
    out.update({
        "meanGrossPct": round(sum(gross) / n, 4),
        "meanNetPct": {s: round(sum(v) / len(v), 4) for s, v in per_scn.items()},
        "hitRateNetBase": round(sum(x > 0 for x in per_scn["base"]) / n, 4),
        "meanNetBaseCI95": [round(lo, 4), round(hi, 4)],
        "tStatEffective": round(m / (sd / math.sqrt(eff_n)), 3) if sd else None,
        "effectiveIndependentTrades": round(eff_n, 1),
        "annualisedSharpeBase": round(per_obs_sr * math.sqrt(252 / horizon), 3),
        "skew": round(skew, 3), "kurtosis": round(kurt, 3),
    })
    if log is not None:
        log.add(name, {"horizon": horizon, "train_min": train_min, "test_len": test_len,
                       "embargo": embargo, "rolling": rolling}, per_obs_sr, n)
        out["trialsLogged"] = log.count
        out["deflatedSharpeProbability"] = round(
            deflated_sharpe(per_obs_sr, int(eff_n), skew, kurt, log.count, log.sharpe_variance()), 4)
    out["survivesBaseCost"] = out["meanNetPct"]["base"] > 0 and lo > 0
    return out
