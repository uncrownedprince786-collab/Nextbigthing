"""How accurate can this brain be made, if it is allowed to speak as rarely as it likes?

    python tools/research/crypto_ceiling.py --lanes crypto:m5 crypto:m15 crypto:h1

The goal set for this model is **90% directional accuracy, per coin, on confident calls only**.
Every measurement so far has been taken under a constraint that makes that goal unreachable by
construction: `crypto_conviction.py` picks a floor from a ladder that stops at 0.15 of margin and
refuses any floor that speaks on fewer than one validation bar in ten. A brain that must answer
10% of all bars cannot be 90% right unless the market is 90% predictable, and it is not.

So this file removes the constraint and asks the question properly. For each lane it sorts the
test fold by how far the model's probability sits from a half, and walks the coverage down --
50%, 10%, 1%, 0.1%, to the single most confident call in the fold -- reporting the accuracy of
each tail. That curve is the honest answer to "can it reach 90%": either some coverage reaches it
with enough rows to mean anything, or the curve flattens below it and the number is not there to
be had at any selectivity.

The same curve is computed **per coin**, because the goal is per coin and because a pooled rate
can hide a wide spread -- a lane at 54% overall could be 70% on one coin and 45% on another, and
only the per-coin table can say.

What would make a tail real
---------------------------
A tail is only worth serving if the accuracy survives the three things that make small samples
lie:

  * **enough rows.** The tails are reported with their row counts and nothing under 200 rows gets
    an accuracy at all. A 100% tail over 7 rows is noise with a flattering name.
  * **a majority that it beats.** The extreme tails are where the model is most sure, and the rows
    it is most sure about are not a balanced sample -- a tail that is 88% UP rows and 90% correct
    has found a trend, not an edge. Every row carries its own base rate.
  * **the same answer on data used to choose.** The curve is computed on validation and on test.
    A threshold read off the test curve is a threshold fitted to the holdout; the validation curve
    is where a floor may be chosen and the test curve is where the choice is scored, once.

Nothing here changes what is served. It measures what is available to serve.
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

from crypto_conviction import lane_rows, load_artifact, score  # noqa: E402


def score_chunked(artifact: dict, X: np.ndarray, rows: np.ndarray,
                  chunk: int = 200_000) -> np.ndarray:
    """Probabilities for `rows` of `X`, a slice at a time, in the matrix's own dtype.

    Scoring the fold in one go would gather every row into a single array first -- on the pooled
    five-minute lane that is a 400 MB allocation to produce 1.5 MB of probabilities, and on a
    machine with under 2 GB free it is the difference between this running beside a training job
    and the two of them fighting over swap. The chunk is gathered, scored and dropped.

    float32 throughout, because the GBM bins its input to uint8 and the cast to float64 is
    arithmetically invisible to it.
    """
    out = np.empty(len(rows), dtype=np.float64)
    for i in range(0, len(rows), chunk):
        idx = rows[i:i + chunk]
        out[i:i + chunk] = score(artifact, X[idx])
    return out

OUT = ROOT / "data" / "foundation" / "dataset" / "crypto_ceiling.json"

#: Coverages to report, as a fraction of the fold. Walked down to a thousandth of the fold, which
#: on the pooled five-minute lane is still a few hundred rows.
COVERAGES = (1.0, 0.50, 0.25, 0.10, 0.05, 0.025, 0.01, 0.005, 0.0025, 0.001)

#: Below this many rows an accuracy is not reported. A rate over a handful of rows is not a rate,
#: and the whole point of this file is to find out whether 90% is real.
MIN_ROWS = 200

#: The target the work is aimed at.
TARGET = 0.90


def pegged_tickers() -> set[str]:
    """Bare tickers the universe builder flagged as dollar-pegged, or an empty set."""
    p = ROOT / "data" / "foundation" / "dataset" / "crypto_universe.json"
    try:
        return {a["ticker"].upper()
                for a in json.loads(p.read_text(encoding="utf-8"))["assets"] if a.get("pegged")}
    except (OSError, KeyError, ValueError):
        return set()


def tail(p: np.ndarray, y: np.ndarray, coverage: float) -> dict:
    """Accuracy over the `coverage` most confident rows, with the base rate it must beat."""
    n_rows = len(y)
    want = max(1, int(round(n_rows * coverage)))
    margin = np.abs(p - 0.5)
    # The margin that admits exactly `want` rows. Ties at the cut are kept, so the realised
    # coverage can exceed the requested one rather than breaking a tie arbitrarily.
    cut = float(np.partition(margin, n_rows - want)[n_rows - want]) if want < n_rows else 0.0
    sel = margin >= cut
    n = int(sel.sum())
    out = {
        "requestedCoverage": coverage,
        "minMargin": round(cut, 6),
        "minProb": round(0.5 + cut, 6),
        "rows": n,
        "coverage": round(n / n_rows, 6),
    }
    if n < MIN_ROWS:
        out.update({"accuracy": None, "note": f"under {MIN_ROWS} rows, not reported"})
        return out
    yy = y[sel]
    pred = (p[sel] >= 0.5).astype(int)
    up = float(yy.mean())
    acc = float((pred == yy).mean())
    out.update({
        "accuracy": round(acc, 5),
        "majorityHere": round(max(up, 1 - up), 5),
        "marginOverMajority": round(acc - max(up, 1 - up), 5),
        "upRate": round(up, 5),
        "upShareCalled": round(float(pred.mean()), 5),
        "reachesTarget": bool(acc >= TARGET),
    })
    return out


def curve(p: np.ndarray, y: np.ndarray) -> list[dict]:
    return [tail(p, y, c) for c in COVERAGES]


def best_accuracy(rows: list[dict]) -> tuple[float | None, float | None]:
    """The highest reported accuracy on a curve, and the coverage it was reached at."""
    scored = [r for r in rows if r.get("accuracy") is not None]
    if not scored:
        return None, None
    best = max(scored, key=lambda r: r["accuracy"])
    return best["accuracy"], best["coverage"]


def symbol_ids(data: dict) -> tuple[np.ndarray, list[str]]:
    """A symbol index per row of the concatenated matrix, in corpus order.

    `prepare_cached` concatenates one block of rows per coin in the order of `corpora`, so the
    block boundaries are the running sum of each coin's kept-row count. This is the same walk
    `crypto_levels.py` does to slice its excursions back apart.
    """
    names = list(data["corpora"].keys())
    ids = np.empty(len(data["ts"]), dtype=np.int32)
    offset = 0
    for i, (_sym, meta) in enumerate(data["corpora"].items()):
        n = len(meta["_series"][2])
        ids[offset:offset + n] = i
        offset += n
    if offset != len(ids):
        raise SystemExit(f"corpus blocks cover {offset} rows, matrix has {len(ids)}")
    return ids, names


def run_lane(tag: str, horizon: str, per_coin: bool) -> dict:
    name = f"brain-c1-{tag}-{horizon}"
    artifact = load_artifact(name)
    r = lane_rows(tag, horizon)
    X = r["data"]["X"]

    p_va = score_chunked(artifact, X, r["va"])
    y_va = r["y"][r["va"]]
    p_te = score_chunked(artifact, X, r["te"])
    y_te = r["y"][r["te"]]

    val_curve = curve(p_va, y_va)
    test_curve = curve(p_te, y_te)

    print(f"\n== {name}: {len(y_te):,} test rows, "
          f"widest test margin {np.abs(p_te - 0.5).max():.4f} "
          f"(p={0.5 + np.abs(p_te - 0.5).max():.4f})", flush=True)
    print("   coverage        rows   acc     majority  margin   reaches 90%", flush=True)
    for row in test_curve:
        if row.get("accuracy") is None:
            print(f"   {row['coverage']:>8.4%}  {row['rows']:>10,}   "
                  f"{row.get('note', '')}", flush=True)
            continue
        print(f"   {row['coverage']:>8.4%}  {row['rows']:>10,}   {row['accuracy']:.4f}  "
              f"{row['majorityHere']:.4f}   {row['marginOverMajority']:+.4f}  "
              f"{'YES' if row['reachesTarget'] else 'no'}", flush=True)

    best_te, at_cov = best_accuracy(test_curve)

    coins: list[dict] = []
    if per_coin:
        ids, names = symbol_ids(r["data"])
        te_ids = ids[r["te"]]
        pegged = pegged_tickers()
        for i, sym in enumerate(names):
            m = te_ids == i
            n = int(m.sum())
            if n < MIN_ROWS:
                coins.append({"symbol": sym, "rows": n, "note": "too few test rows"})
                continue
            cp, cy = p_te[m], y_te[m]
            c_curve = curve(cp, cy)
            acc, cov = best_accuracy(c_curve)
            ung = c_curve[0]
            base = sym.upper()[:-4] if sym.upper().endswith("USDT") else sym.upper()
            coins.append({
                "symbol": sym,
                "rows": n,
                # A pegged coin at the top of this table is not a find. Its direction is
                # oscillation in the fourth decimal of a dollar, and a peg genuinely does
                # mean-revert, so the model can be both very sure and very right about moves worth
                # a fiftieth of the fee. Marked here so the table cannot be read as a result.
                "pegged": base in pegged,
                "ungatedAccuracy": ung.get("accuracy"),
                "ungatedMajority": ung.get("majorityHere"),
                "bestAccuracy": acc,
                "bestAtCoverage": cov,
                "reachesTarget": bool(acc is not None and acc >= TARGET),
                "curve": c_curve,
            })
        scored = [c for c in coins if c.get("bestAccuracy") is not None]
        hit = [c for c in scored if c["reachesTarget"]]
        scored.sort(key=lambda c: -c["bestAccuracy"])
        print(f"\n   per coin: {len(scored)} coins with enough test rows, "
              f"{len(hit)} reach {TARGET:.0%} at some coverage", flush=True)
        for c in scored[:10]:
            print(f"      {c['symbol']:<16} ungated {c['ungatedAccuracy']:.4f}  "
                  f"best {c['bestAccuracy']:.4f} at {c['bestAtCoverage']:.3%} "
                  f"of its {c['rows']:,} rows"
                  f"{'   <- PEGGED, not a tradable direction' if c['pegged'] else ''}", flush=True)

    return {
        "family": tag,
        "horizon": horizon,
        "modelVersion": name,
        "rows": {"validation": int(len(y_va)), "test": int(len(y_te))},
        "widestTestMargin": round(float(np.abs(p_te - 0.5).max()), 6),
        "validationCurve": val_curve,
        "testCurve": test_curve,
        "bestTestAccuracy": best_te,
        "bestAtCoverage": at_cov,
        "reachesTarget": bool(best_te is not None and best_te >= TARGET),
        "perCoin": coins,
    }


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Map accuracy against how rarely the brain is allowed to speak.")
    ap.add_argument("--lanes", nargs="*",
                    default=["crypto:m5", "crypto:m15", "crypto:h1", "crypto:d20"])
    ap.add_argument("--per-coin", action="store_true", default=True)
    ap.add_argument("--no-per-coin", dest="per_coin", action="store_false")
    a = ap.parse_args()

    lanes = []
    for spec in a.lanes:
        tag, horizon = spec.split(":")
        lanes.append(run_lane(tag, horizon, a.per_coin))

    doc = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "producedBy": "tools/research/crypto_ceiling.py",
        "target": TARGET,
        "question": ("whether any conviction threshold, at any coverage, reaches 90% directional "
                     "accuracy on the holdout -- pooled and per coin"),
        "minRows": MIN_ROWS,
        "coverages": list(COVERAGES),
        "lanes": lanes,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=1), encoding="utf-8")

    print("\n=== answer ===", flush=True)
    for ln in lanes:
        n_hit = sum(1 for c in ln["perCoin"] if c.get("reachesTarget"))
        n_scored = sum(1 for c in ln["perCoin"] if c.get("bestAccuracy") is not None)
        best = ln["bestTestAccuracy"]
        print(f"   {ln['modelVersion']}: pooled best "
              f"{best:.4f} at {ln['bestAtCoverage']:.3%} coverage"
              if best is not None else f"   {ln['modelVersion']}: nothing reportable",
              flush=True)
        print(f"      coins reaching {TARGET:.0%}: {n_hit} of {n_scored}", flush=True)
    print(f"\nwrote {OUT}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
