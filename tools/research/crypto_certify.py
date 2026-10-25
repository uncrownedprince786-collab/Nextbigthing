"""Which coins has this brain actually earned the right to speak about?

    python tools/research/crypto_certify.py
    python tools/research/crypto_certify.py --lanes crypto:m15 --coins BTCUSDT ETHUSDT

Every accuracy this repository has published so far is a **pool** number: one figure over 140
coins at once. That is the right way to measure a pooled model and the wrong way to decide what to
show a reader, because it says nothing about whether the thing works on the coin in front of them.
A lane at 53.7% could be 60% on the liquid majors and a coin flip on the small caps, and the page
would print the same sentence over both.

So this file measures each coin on its own and issues a verdict per coin and horizon. A coin that
passes is served. **A coin that fails is served nothing at all** -- not a weaker direction, not a
hedged one. The product decision is that a blank is honest and a guess dressed as a call is not.

The five gates, which are the lane gates applied to one coin
------------------------------------------------------------
Pre-registered in `crypto_conviction.py` and reused unchanged, because a gate relaxed for the
coins that fail it is not a gate:

  * **beats its own majority** -- accuracy above the larger class *of that coin's called rows*.
    A coin that rose 58% of the time in the test window needs to beat 58%, not 50%.
  * **calls both directions** -- neither above 0.80 of its calls. A model that only ever says UP
    about a coin in an uptrend has learned the trend, not the coin.
  * **bootstrap excludes zero** -- 95% day-blocked interval for (accuracy - majority) strictly
    above zero. Day-blocked because adjacent five-minute rows share a label window and an i.i.d.
    bootstrap would understate the interval by an order of magnitude.
  * **four of five walk-forward blocks** -- above its own block majority in at least four of five
    chronological slices. One lucky fortnight cannot carry a coin.
  * **enough called rows** -- at least `MIN_CALLED` of them. Without this the other four gates are
    decided by noise, and a 100% accurate coin over nine calls would certify.

Why this scores at stride 1 when the model was fitted at stride 16
-------------------------------------------------------------------
The stride is a *training cost* decision -- it thins the rows so a pooled fit over 140 coins fits
in memory. It is not a measurement decision, and scoring is free of it: no parameter is fitted
here, every test row is simply read. At stride 16 one coin contributes around 1,600 test rows, of
which maybe 200 clear the conviction floor, and 200 rows cannot support five gates. At stride 1 it
contributes around 26,000, and the gates mean something.

Each coin's matrix is built alone and uncached, one at a time. A single coin at stride 1 is about
87 MB; the pooled equivalent would be 24 million rows and would not fit on this machine. The
coin's bars are its own, so building them alone changes nothing -- except the market-context
block, which is read from Bitcoin exactly as it is in training and serving.
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

from crypto_horizons import HORIZONS  # noqa: E402
from crypto_matrix import _build_pool  # noqa: E402
from crypto_conviction import (  # noqa: E402
    blocks_above, load_artifact, score, training_config,
)
from train_crypto_short import day_blocked_bootstrap, labels_for, split  # noqa: E402

LANES = ROOT / "data" / "foundation" / "dataset" / "crypto_lanes.json"
OUT = ROOT / "data" / "foundation" / "dataset" / "crypto_certified.json"

#: Called rows a coin needs before its gates are read. Below this the sample decides the verdict.
MIN_CALLED = 500

#: Scoring stride. 1 = every test row; see the module docstring for why this is not the fit stride.
SCORE_STRIDE = 1


def servable_lanes() -> list[dict]:
    doc = json.loads(LANES.read_text(encoding="utf-8"))
    return [l for l in doc["lanes"] if l.get("servable")]


def lane_floor(lane: dict) -> float:
    """The margin a call must clear on this lane, or 0.0 when the lane has no floor.

    A zero floor is a real configuration -- it means the page speaks on every bar -- so it is
    honoured rather than treated as an error. But it is also what a lane looks like when the
    conviction stage has not run, which is the state `crypto_lanes.json` was left in by a pipeline
    that died between training and `crypto_conviction.py`. Certifying against a floor that is
    missing rather than chosen measures a population no reader is shown, so the caller prints
    which it is and the figure travels into the output.
    """
    c = lane.get("conviction")
    return float(c["floor"]) if c and c.get("floor") is not None else 0.0


def certify(p: np.ndarray, y: np.ndarray, ts: np.ndarray, floor: float) -> dict:
    """The five gates for one coin on one horizon."""
    sel = np.abs(p - 0.5) >= floor
    called = int(sel.sum())
    out: dict = {"testRows": int(len(y)), "called": called,
                 "coverage": round(called / len(y), 5) if len(y) else 0.0}
    if called < MIN_CALLED:
        out.update({"accuracy": None, "certified": False,
                    "why": f"only {called} called rows, needs {MIN_CALLED}"})
        return out

    yy = y[sel]
    pp = p[sel]
    pred = (pp >= 0.5).astype(int)
    up = float(yy.mean())
    maj_class = 1 if up >= 0.5 else 0
    majority = max(up, 1 - up)
    acc = float((pred == yy).mean())
    up_share = float(pred.mean())

    boot = day_blocked_bootstrap((pred == yy).astype(float),
                                 (yy == maj_class).astype(float),
                                 (ts[sel] // 86_400_000).astype(np.int64))
    wf = blocks_above(pp, yy)

    gates = {
        "aboveOwnMajority": bool(acc > majority),
        "bothDirectionsCalled": bool(max(up_share, 1 - up_share) <= 0.80),
        "bootstrapExcludesZero": bool(boot["excludesZero"]),
        "walkForwardMajority": bool(wf["blocksScored"] > 0
                                    and wf["blocksAboveMajority"] >= min(4, wf["blocksScored"])),
        "enoughCalledRows": True,
    }
    out.update({
        "accuracy": round(acc, 5),
        "ownMajority": round(majority, 5),
        "edgeOverMajority": round(acc - majority, 5),
        "upRate": round(up, 5),
        "upShareCalled": round(up_share, 5),
        "bootstrapCi95": boot["ci95"],
        "walkForward": f"{wf['blocksAboveMajority']}/{wf['blocksScored']}",
        "gates": gates,
        "certified": all(gates.values()),
        "why": None if all(gates.values())
        else ", ".join(k for k, v in gates.items() if not v) + " failed",
    })
    return out


def coin_rows(symbol: str, interval: str, context: bool) -> dict:
    """One coin's matrix, built alone and not cached."""
    return _build_pool([symbol], interval, SCORE_STRIDE, context)


def main() -> int:
    ap = argparse.ArgumentParser(description="Certify the brain per coin, per horizon.")
    ap.add_argument("--lanes", nargs="*", help="family:horizon; default every servable lane")
    ap.add_argument("--coins", nargs="*", help="default: the lane's own training pool")
    a = ap.parse_args()

    lanes = servable_lanes()
    if a.lanes:
        want = set(a.lanes)
        lanes = [l for l in lanes if f"{l['family']}:{l['horizon']}" in want]
    if not lanes:
        raise SystemExit("no servable lanes to certify")

    # Grouped by (family, interval) so each coin's matrix is built once and reused across every
    # horizon that reads the same corpus -- m5, m15, h1 and h4 all read the 5m bars.
    groups: dict[tuple[str, str], list[dict]] = {}
    for l in lanes:
        groups.setdefault((l["family"], l["interval"]), []).append(l)

    results: dict[str, dict] = {}
    for (family, interval), here in sorted(groups.items()):
        cfg = training_config(family, here[0]["horizon"])
        coins = a.coins or cfg["symbols"]
        print(f"\n=== {family} @ {interval}: {len(coins)} coins x "
              f"{len(here)} horizons ({', '.join(l['horizon'] for l in here)}) ===", flush=True)

        arts = {l["horizon"]: load_artifact(l["modelVersion"]) for l in here}
        floors = {l["horizon"]: lane_floor(l) for l in here}
        for l in here:
            f = floors[l["horizon"]]
            print(f"   {l['horizon']}: floor {f:.3f}"
                  + ("  ! no conviction floor on this lane -- certifying the ungated population, "
                     "which is what the page currently serves" if f == 0.0 else ""), flush=True)

        for i, sym in enumerate(coins, 1):
            try:
                data = coin_rows(sym, interval, cfg["context"])
            except Exception as e:                                  # noqa: BLE001
                print(f"  {i:>3}/{len(coins)}  {sym:<14} matrix failed: {e}", flush=True)
                continue
            X, ts = data["X"], data["ts"]
            step_ms = next(iter(data["corpora"].values()))["stepMs"]
            line = []
            for l in here:
                k = l["horizon"]
                y, usable, _ = labels_for(data, HORIZONS[k]["bars"])
                _tr, _va, te_m, _meta = split(ts, HORIZONS[k]["bars"], step_ms)
                te = np.flatnonzero(te_m & usable)
                te = te[np.argsort(ts[te], kind="stable")]
                if len(te) < MIN_CALLED:
                    r = {"testRows": int(len(te)), "called": 0, "accuracy": None,
                         "certified": False, "why": "too few test rows"}
                else:
                    p = score(arts[k], X[te])
                    r = certify(p, y[te], ts[te], floors[k])
                r["convictionFloor"] = floors[k]
                results.setdefault(sym, {})[f"{family}:{k}"] = r
                mark = "OK " if r["certified"] else "no "
                acc = f"{r['accuracy']:.4f}" if r.get("accuracy") is not None else "  --  "
                line.append(f"{k} {mark}{acc}")
            print(f"  {i:>3}/{len(coins)}  {sym:<14} " + "  ".join(line), flush=True)

    # Merged into whatever is already on disk, rather than replacing it.
    #
    # A run narrowed to one lane or a handful of coins is the normal way this gets used while a
    # retrain is in flight, and the first version of this file overwrote the whole document each
    # time -- so certifying the nine coins a reader had asked about silently discarded the twenty
    # certified an hour earlier. Verdicts are keyed by coin and lane, so a later run replaces
    # exactly what it re-measured and leaves the rest standing.
    merged: dict[str, dict] = {}
    if OUT.exists():
        try:
            merged = json.loads(OUT.read_text(encoding="utf-8")).get("coins", {}) or {}
        except (OSError, ValueError):
            merged = {}
    for sym, lanes_r in results.items():
        merged.setdefault(sym, {}).update(lanes_r)
    results = merged

    per_lane: dict[str, list[str]] = {}
    for sym, lanes_r in results.items():
        for key, r in lanes_r.items():
            if r["certified"]:
                per_lane.setdefault(key, []).append(sym)

    print("\n=== certified ===", flush=True)
    for key in sorted(per_lane):
        names = sorted(per_lane[key])
        print(f"   {key}: {len(names)} coins", flush=True)
    total = len({s for v in per_lane.values() for s in v})
    print(f"   {total} distinct coins certified on at least one horizon "
          f"out of {len(results)} measured", flush=True)

    doc = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "producedBy": "tools/research/crypto_certify.py",
        "what": ("per-coin, per-horizon verdict. A coin absent from a lane's list is served no "
                 "direction on that lane at all -- not a weaker one."),
        "gates": {
            "aboveOwnMajority": "accuracy above the larger class of that coin's called rows",
            "bothDirectionsCalled": "neither direction above 0.80 of its calls",
            "bootstrapExcludesZero": "95% day-blocked CI for (accuracy - majority) above zero",
            "walkForwardMajority": "above its own block majority in 4 of 5 chronological blocks",
            "enoughCalledRows": f"at least {MIN_CALLED} called rows on the test fold",
        },
        "minCalledRows": MIN_CALLED,
        "scoreStride": SCORE_STRIDE,
        "certifiedByLane": {k: sorted(v) for k, v in sorted(per_lane.items())},
        "coins": results,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    print(f"\nwrote {OUT}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
