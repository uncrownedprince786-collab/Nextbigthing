"""Turn replayed sessions into a supervised dataset: point-in-time features, forward outcomes.

    python tools/make_dataset.py --replay <dir> --out <dir>

What this is, and what it deliberately is not
---------------------------------------------
`tools/replay_batch.py` records what the **rule engine** decided on a past session. That is not
a training set. The engine refuses most candidates -- measured over eight sessions, 398
directional setups produced 0 LONG and 0 SHORT, because a direction needs a confirmation leg and
the confirmation tables hold only recent days -- and treating "the engine would not trade this"
as "there is nothing to learn here" confuses a trading policy with a dataset.

So this file keeps three things apart, in three sets of fields:

  * **candidate** -- the reconstructed setup at that date: its state, entry and invalidation.
  * **decision** -- what the live rules actually said, carried verbatim and never overridden.
  * **outcome** -- what the price then did, computed from stored bars after that date.

An example is emitted for every asset with a reconstructed setup, whatever the engine decided.
Nothing here weakens a rule: the engine's verdict is a column, not a filter.

Targets, defined before any of them were generated
--------------------------------------------------
Two kinds, kept apart on purpose:

  * **Continuous** -- `fwd1`, `fwd5`, `fwd20`: the percent change of the close from the as-of
    session to +1, +5 and +20 *sessions* (not calendar days), plus `mfe`/`mae`, the furthest
    favourable and adverse close inside the 20-session window. These need no threshold and are
    the honest primary target.
  * **Categorical** -- `label20`, from `fwd20` against a threshold fixed here before the first
    row was written: a move must clear **`LABEL_THRESHOLD_PCT` (2%)** to count as UP or DOWN,
    and anything inside that band is FLAT. The band exists so a label is not assigned to noise;
    2% is roughly a typical 20-session round-trip cost plus slippage at the base assumption, so
    a move smaller than it is not tradeable even when its sign is right.

A horizon is only labelled when it has **fully elapsed**: +20 needs 20 stored sessions after the
as-of date. A horizon short of that is `null` and counted as immature, never as a flat outcome.

Ambiguity
---------
`entryHit`/`stopHit` are judged on daily closes, because that is what is stored. When a single
session's close is beyond both the candidate entry and its invalidation, the ordering inside that
day is unknowable from daily bars and the row is marked `ambiguous` rather than resolved by a
guess. `tools/trade_sim.py` makes the same refusal for the same reason.

Nothing is written to any database.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import math
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "jobs"))
sys.path.insert(0, str(ROOT / "tools"))

import costs as cost_model  # noqa: E402
from nbt import db  # noqa: E402

HORIZONS = (1, 5, 20)
WINDOW = max(HORIZONS)
LABEL_THRESHOLD_PCT = 2.0
DATASET_VERSION = 1


def arg(name: str, default: str | None = None) -> str | None:
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def rules_version() -> str:
    out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                         capture_output=True, text=True).stdout.strip()
    return out or "unknown"


def forward_bars(cur, as_of: date) -> dict[str, list[dict]]:
    """Up to WINDOW sessions strictly after `as_of`, per asset, oldest first.

    Strictly after: the as-of close is the base an outcome is measured from, so including it
    would make a zero-session return look like a one-session one.
    """
    cur.execute(
        '''
        SELECT "assetId", date, close
        FROM (
            SELECT s."assetId", s.date, s.close,
                   row_number() OVER (PARTITION BY s."assetId" ORDER BY s.date ASC) AS rn
            FROM "PriceSnapshot" s
            WHERE s.date > %s AND s.close IS NOT NULL
        ) t
        WHERE rn <= %s
        ORDER BY "assetId", date ASC
        ''',
        (as_of, WINDOW),
    )
    out: dict[str, list[dict]] = {}
    for r in cur.fetchall():
        out.setdefault(r["assetId"], []).append(r)
    return out


def base_closes(cur, as_of: date) -> dict[str, float]:
    """Each asset's newest close on or before `as_of` -- the price an outcome is measured from."""
    cur.execute(
        '''
        SELECT DISTINCT ON ("assetId") "assetId", close
        FROM "PriceSnapshot"
        WHERE date <= %s AND close IS NOT NULL
        ORDER BY "assetId", date DESC
        ''',
        (as_of,),
    )
    return {r["assetId"]: float(r["close"]) for r in cur.fetchall()}


def label_threshold_pct(horizon: int) -> float:
    """The move a `horizon`-session call has to clear to be UP or DOWN rather than FLAT.

    **Why this is not one number for every horizon.** `LABEL_THRESHOLD_PCT` is 2%, and it was
    chosen for the 20-session window. Reusing it at 5 sessions would not be a stricter rule, it
    would be a different question: a 2% move is ordinary over a month and rare over a week, so
    nearly every short call would come back FLAT and the label would be measuring the calendar
    rather than the direction.

    So the threshold scales with the square root of the horizon, which is how the spread of a
    random walk's cumulative return grows. That is a textbook relationship, fixed here **before
    any 5-session result was looked at**, and it is deliberately not a knob: there is no argument
    to tune, and the 20-session value it is anchored to is the one this project has used from the
    first row it stored.

        1 session  -> 0.45%        5 sessions -> 1.0%        20 sessions -> 2.0%

    At 20 it returns exactly `LABEL_THRESHOLD_PCT`, so `label20` is bit-for-bit the label it
    always was and nothing already trained or stored changes meaning.
    """
    return round(LABEL_THRESHOLD_PCT * math.sqrt(horizon / float(WINDOW)), 2)


def label_for(fwd: float | None, horizon: int) -> str | None:
    """`UP`/`DOWN`/`FLAT` for a forward return, or `None` when the horizon has not elapsed.

    `None` is not FLAT. A window that has not closed has no direction, and the one way this
    project can lie to itself about a model is to read an unelapsed horizon as a flat outcome.
    """
    if fwd is None:
        return None
    t = label_threshold_pct(horizon)
    return "UP" if fwd >= t else "DOWN" if fwd <= -t else "FLAT"


def outcomes(base: float, bars: list[dict]) -> dict:
    """Forward returns, extremes and the categorical label. Immature horizons stay null."""
    closes = [float(b["close"]) for b in bars]
    out: dict = {"sessionsAvailable": len(closes)}
    for h in HORIZONS:
        out[f"fwd{h}"] = (round((closes[h - 1] / base - 1) * 100, 4)
                          if len(closes) >= h and base else None)
    if closes and base:
        out["mfe"] = round((max(closes) / base - 1) * 100, 4)
        out["mae"] = round((min(closes) / base - 1) * 100, 4)
    else:
        out["mfe"] = out["mae"] = None
    # Every horizon is labelled, not just the longest. `fwd{h} is None` is already the maturity
    # test -- a horizon short of its sessions stays null above -- so `mature{h}` is that fact
    # named rather than a second rule that could drift from it.
    for h in HORIZONS:
        f = out.get(f"fwd{h}")
        out[f"label{h}"] = label_for(f, h)
        out[f"mature{h}"] = f is not None
    return out


def plan_outcome(state: str, base: float, entry, invalid, bars: list[dict]) -> dict:
    """Whether the candidate's own entry and invalidation were reached, on stored closes.

    Returns `ambiguous` when one session's close is beyond both, because daily bars cannot order
    what happened inside the day -- the same refusal `trade_sim.py` makes.
    """
    res = {"entryHit": None, "stopHit": None, "ambiguous": False, "sessionsHeld": None}
    if state not in ("buy", "short") or entry is None or invalid is None or not bars:
        return res
    long_ = state == "buy"
    for i, b in enumerate(bars, 1):
        c = float(b["close"])
        hit_entry = c >= entry if long_ else c <= entry
        hit_stop = c <= invalid if long_ else c >= invalid
        if hit_entry and hit_stop:
            return {**res, "ambiguous": True, "sessionsHeld": i}
        if hit_stop:
            return {**res, "entryHit": False, "stopHit": True, "sessionsHeld": i}
        if hit_entry:
            return {**res, "entryHit": True, "stopHit": False, "sessionsHeld": i}
    return {**res, "entryHit": False, "stopHit": False, "sessionsHeld": len(bars)}


def main() -> None:
    replay_dir = Path(arg("--replay") or (ROOT.parent / "nbt-private" / "replay"))
    out_dir = Path(arg("--out") or (ROOT.parent / "nbt-private" / "dataset"))
    out_dir.mkdir(parents=True, exist_ok=True)

    setup_files = sorted(replay_dir.glob("setups-*.jsonl"))
    if not setup_files:
        raise SystemExit(f"no setups-*.jsonl in {replay_dir}; run tools/replay_batch.py first")

    conn = db()
    cur = conn.cursor()
    cur.execute('SELECT a.id, a.symbol, a."assetType"::text AS "assetType", i.market '
                'FROM "Asset" a JOIN "Industry" i ON i.id = a."industryId"')
    asset_by_id = {r["id"]: r for r in cur.fetchall()}

    rules = rules_version()
    rows_out: list[dict] = []
    per_date: list[dict] = []

    for f in setup_files:
        as_of = date.fromisoformat(f.stem.replace("setups-", ""))
        setups = [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]
        fwd = forward_bars(cur, as_of)
        base = base_closes(cur, as_of)

        counts = {"examples": 0, "directionalCandidates": 0, "mature20": 0,
                  "ambiguous": 0, "excludedNoBase": 0, "excludedNoForward": 0}
        for s in setups:
            aid = s["assetId"]
            asset = asset_by_id.get(aid)
            b = base.get(aid)
            bars = fwd.get(aid, [])
            if asset is None or not b:
                counts["excludedNoBase"] += 1
                continue
            if not bars:
                counts["excludedNoForward"] += 1
                continue
            o = outcomes(b, bars)
            plan = plan_outcome(s["state"], b, s.get("entryLevel"), s.get("invalidateLevel"), bars)
            directional = s["state"] in ("buy", "short")
            rec = {
                "asOf": as_of.isoformat(),
                "assetId": aid,
                "symbol": asset["symbol"],
                "assetType": asset["assetType"],
                "market": asset["market"],
                "rulesVersion": rules,
                "datasetVersion": DATASET_VERSION,
                # --- candidate (reconstructed, point-in-time)
                "candidate": {
                    "setupState": s["state"],
                    "directional": directional,
                    "entryLevel": s.get("entryLevel"),
                    "invalidateLevel": s.get("invalidateLevel"),
                    "confidence": s.get("confidence"),
                    "conditions": s.get("conditions"),
                    "missingInputs": s.get("missing"),
                    "against": s.get("against"),
                },
                # --- what the live rules said. Carried, never overridden.
                "engineDecision": "WAIT",
                "engineDecisionNote": (
                    "The replayed rule engine returned WAIT for every name on these dates; a "
                    "direction needs a confirmation leg and the confirmation tables hold only "
                    "recent days. Recorded as a field, not used to filter this dataset."
                ),
                # --- outcome
                "outcome": {**o, **plan, "baseClose": b},
                "quality": {
                    "inputsOmitted": ["News", "HumanSignal", "MacroGate",
                                      "AssetFactor", "AssetAnalog"],
                    "survivorship": "current-universe-only",
                    "priceSource": "PriceSnapshot (stored)",
                },
            }
            if directional and o.get("fwd20") is not None and b:
                risk = abs(b - s["invalidateLevel"]) if s.get("invalidateLevel") else None
                if risk:
                    gross = o["fwd20"] / 100 * b / risk
                    rec["outcome"]["grossR20"] = round(gross, 4)
                    rec["outcome"]["netR20"] = cost_model.sensitivity(
                        gross, fill=b, risk=risk, asset_type=asset["assetType"],
                        short=s["state"] == "short", sessions=20, market=asset["market"],
                    )
            counts["examples"] += 1
            counts["directionalCandidates"] += int(directional)
            counts["mature20"] += int(o["mature20"])
            counts["ambiguous"] += int(plan["ambiguous"])
            rows_out.append(rec)
        per_date.append({"asOf": as_of.isoformat(), **counts})
        print(f"  {as_of}  examples {counts['examples']:4}  directional {counts['directionalCandidates']:3}"
              f"  mature+20 {counts['mature20']:4}  ambiguous {counts['ambiguous']:3}")

    conn.close()

    path = out_dir / f"examples-v{DATASET_VERSION}.jsonl.gz"
    payload = "\n".join(json.dumps(r) for r in rows_out).encode("utf-8")
    with gzip.open(path, "wb") as fh:
        fh.write(payload)
    digest = hashlib.sha256(payload).hexdigest()

    totals = {k: sum(d[k] for d in per_date) for k in
              ("examples", "directionalCandidates", "mature20", "ambiguous",
               "excludedNoBase", "excludedNoForward")}
    label_counts: dict[str, int] = {}
    for r in rows_out:
        lab = r["outcome"]["label20"]
        label_counts[str(lab)] = label_counts.get(str(lab), 0) + 1

    manifest = {
        "dataset": "historical-examples",
        "version": DATASET_VERSION,
        "rulesVersion": rules,
        "artifact": path.name,
        "sha256": digest,
        "uncompressedBytes": len(payload),
        "rows": len(rows_out),
        "dateRange": [per_date[0]["asOf"], per_date[-1]["asOf"]] if per_date else None,
        "totals": totals,
        "label20Counts": label_counts,
        "targets": {
            "continuous": ["fwd1", "fwd5", "fwd20", "mfe", "mae"],
            "categorical": {"field": "label20", "thresholdPct": LABEL_THRESHOLD_PCT,
                            "definedBeforeGeneration": True},
        },
        "limitations": [
            "Reduced-input: News, HumanSignal, MacroGate, AssetFactor and AssetAnalog were not "
            "reconstructed, so these are not the inputs the live system had on those dates.",
            "Survivorship: the asset universe is today's active names, so delisted and renamed "
            "names are absent. This is NOT a survivorship-bias-free sample.",
            "Outcomes use daily closes; intraday ordering of entry and stop is unknowable and "
            "such rows are marked ambiguous rather than resolved.",
            "engineDecision is carried for reference; no rule was weakened to produce examples.",
        ],
        "reproduce": "python tools/replay_batch.py --dates <csv> && python tools/make_dataset.py",
    }
    (out_dir / f"manifest-v{DATASET_VERSION}.json").write_text(
        json.dumps(manifest, indent=1), encoding="utf-8")
    print(json.dumps({"rows": len(rows_out), "totals": totals,
                      "label20": label_counts, "sha256": digest[:16]}, indent=1))
    print(f"artifact: {path}")


if __name__ == "__main__":
    main()
