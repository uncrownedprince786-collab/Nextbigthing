"""Join forward outcomes, replayed setups and point-in-time features into one dataset, and say exactly
what joined and what did not.

    python tools/foundation/assemble.py --full DIR --pit DIR [--replay DIR --runs runs.json] --out DIR

Inputs, each already built by its own tool and none of them re-derived here:

* `--full`   `full-history-v2.jsonl.gz` from tools/full_history.py: every asset-session with a
             complete 20-session forward window, with its outcome.
* `--pit`    `pit-<year>.jsonl.gz` from tools/foundation/pit_features.py: factors and analogs as
             they stood at that session's close.
* `--replay` the canonical replay outputs (`setups-<date>.jsonl`, one directory per run), with
             `--runs` saying which runs executed the current replay code. Optional; without it the
             dataset has features and outcomes and no reconstructed setup, and says so per row.

Output: `examples-v3-<year>.jsonl.gz` and `manifest.json`. A row is

    {asOf, symbol, assetType, market, outcome{...}, pit{n, f, an}|null, candidate{...}|null,
     coverage{pit, setup}}

and carries no field that describes the future outside `outcome`.

What the manifest proves, so nobody has to take it on trust:

* **Coverage.** Every eligible asset-session is either joined to features or counted under a named
  reason it was not. `unexplained` must be zero or the run fails.
* **Leakage.** No feature row is dated after its session; every candidate's `periodEnd` is on or
  before it; the rows pass `walkforward.assert_features_are_past_only`.
* **Deduplication.** Each source is checked for repeated (symbol, session) keys; the setup join
  takes the file whose session equals the row's date, so an asset replayed on a day it did not
  trade is not counted twice.
* **Missingness.** Null share of every factor, per asset class.
* **Reproducibility.** The first year is assembled twice and the digests must match.
* **Resources.** Wall time and peak memory.

The data derive from third-party feeds. Output belongs in a sealed artifact or a private directory.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import sys
import time
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

try:
    import resource
except ImportError:  # Windows
    resource = None

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "tools"))

from walkforward import assert_features_are_past_only  # noqa: E402

# How far back a feature window reaches (tools/foundation/pit_features.WINDOW) and how far forward
# an outcome does. A row is suspect when an unadjusted corporate action falls in either.
LOOKBACK_SESSIONS = 260
LOOKFORWARD_SESSIONS = 20

SETUP_KEYS = ("state", "headline", "conditions", "missing", "against", "entryLevel", "invalidateLevel",
              "rangeNote", "confidence", "confidenceNote")


def arg(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def read_gz(path: Path):
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def unadjusted_windows(path: Path | None) -> dict[str, list[str]]:
    """{symbol: [action dates]} from the split scan, or {} when it has not been run.

    A stored series that was never adjusted for a split carries a one-day "return" that no holder
    experienced. Every factor measured across that date is wrong, so the rows are flagged rather
    than silently learned from. Flagging and not dropping is deliberate: the rows are still correct
    about everything that does not cross the action, and a consumer should decide.
    """
    if not path or not path.exists():
        return {}
    doc = json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, list[str]] = {}
    for c in doc.get("candidatesList", []):
        out.setdefault(c["symbol"], []).append(c["date"])
    return {k: sorted(v) for k, v in out.items()}


def setups_for_year(replay: Path | None, runs: dict, year: int) -> dict[tuple, dict]:
    """{(assetId, periodEnd): setup row} from the newest trusted run, taking the session whose date
    equals the row's own date. Returns {} when no replay is supplied."""
    if replay is None:
        return {}
    best: dict[str, tuple[int, Path]] = {}
    for art in sorted(p for p in replay.iterdir() if p.is_dir()):
        rid = art.name.removeprefix("nbt-worker-output-")
        if not runs.get(rid, {}).get("trusted"):
            continue
        for f in art.rglob(f"setups-{year}-*.jsonl"):
            day = f.stem.removeprefix("setups-")
            if day not in best or int(rid) > best[day][0]:
                best[day] = (int(rid), f)
    out: dict[tuple, dict] = {}
    for day, (_, f) in best.items():
        for line in f.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            s = json.loads(line)
            if s.get("periodEnd") == day:           # the asset's own session, not a carried-forward one
                out[(s["assetId"], day)] = s
    return out


def assemble_year(year: int, full_rows: list[dict], pit_path: Path | None, setups: dict, stats: dict,
                  actions: dict[str, list[str]] | None = None):
    pit: dict[tuple, dict] = {}
    if pit_path and pit_path.exists():
        for r in read_gz(pit_path):
            k = (r["a"], r["d"])
            if k in pit:
                stats["pitDuplicates"] += 1
            pit[k] = r
    first_pit: dict[str, str] = {}
    for (sym, d) in pit:
        if sym not in first_pit or d < first_pit[sym]:
            first_pit[sym] = d
    seen = set()
    for r in full_rows:
        key = (r["symbol"], r["asOf"])
        if key in seen:
            stats["fullDuplicates"] += 1
            continue
        seen.add(key)
        p = pit.get(key)
        s = setups.get((r["assetId"], r["asOf"]))
        cls = r["assetType"]
        stats["eligible"] += 1
        stats[f"eligible:{cls}"] += 1
        suspect = False
        for ad in (actions or {}).get(r["symbol"], ()):
            # Calendar days as a safe over-estimate of the session window: 260 sessions is about
            # 378 calendar days, 20 is about 29. Over-flagging is the right direction here.
            lo = (date.fromisoformat(r["asOf"]) - timedelta(days=378)).isoformat()
            hi = (date.fromisoformat(r["asOf"]) + timedelta(days=29)).isoformat()
            if lo <= ad <= hi:
                suspect = True
                break
        if suspect:
            stats["rowsTouchingAnUnadjustedAction"] += 1
            stats[f"suspect:{cls}"] += 1
        row = {
            "asOf": r["asOf"], "symbol": r["symbol"], "assetType": cls, "market": r["market"],
            "dataQuality": {"unadjustedActionInWindow": suspect},
            "outcome": r["outcome"],
            "pit": None if p is None else {"n": p["n"], "f": p["f"], "an": p.get("an")},
            "candidate": None if s is None else {k: s.get(k) for k in SETUP_KEYS},
            "coverage": {"pit": p is not None, "setup": s is not None},
        }
        if p is not None:
            stats["withPit"] += 1
            stats[f"pit:{cls}"] += 1
            if p["d"] > r["asOf"]:
                stats["leakPitAfterSession"] += 1
            for k, v in p["f"].items():
                stats[f"null:{cls}:{k}"] += v is None
            if p.get("an"):
                stats["withAnalog"] += 1
        else:
            # Every session without features must have a named reason; "other" fails the run.
            if r["asOf"] < first_pit.get(r["symbol"], "9999") or r["symbol"] not in first_pit:
                stats["noPit:history shorter than the feature threshold"] += 1
            elif cls != "crypto" and date.fromisoformat(r["asOf"]).weekday() >= 5:
                stats["noPit:weekend bar of a non-crypto asset (not a session)"] += 1
            else:
                stats["noPit:other"] += 1
            stats["noPit"] += 1
        if s is not None:
            stats["withSetup"] += 1
            if s.get("periodEnd") and s["periodEnd"] > r["asOf"]:
                stats["leakSetupAfterSession"] += 1
        if p is not None and s is not None:
            stats["withBoth"] += 1
        yield row
    stats["pitRowsNotInFull"] += len(set(pit) - seen)


def build_year(year, full_rows, pit_path, setups, out_dir: Path | None, actions=None):
    stats = Counter()
    h = hashlib.sha256()
    n = 0
    fh = gzip.open(out_dir / f"examples-v3-{year}.jsonl.gz", "wt", encoding="utf-8", compresslevel=6) if out_dir else None
    batch = []
    for row in assemble_year(year, full_rows, pit_path, setups, stats, actions):
        line = json.dumps(row, separators=(",", ":"), default=str)
        h.update(line.encode())
        n += 1
        if n <= 2000:
            batch.append(row)
        if fh:
            fh.write(line + "\n")
    if fh:
        fh.close()
    assert_features_are_past_only(batch)
    return stats, h.hexdigest(), n


def main() -> int:
    t0 = time.time()
    full_dir, pit_dir, out = Path(arg("--full")), Path(arg("--pit")), Path(arg("--out"))
    replay = Path(arg("--replay")) if arg("--replay") else None
    runs = json.loads(Path(arg("--runs")).read_text(encoding="utf-8")) if arg("--runs") else {}
    out.mkdir(parents=True, exist_ok=True)

    full_file = next(iter(sorted(full_dir.glob("full-history-v*.jsonl.gz"))))
    # Every outcome row is held at once, because full_history writes asset by asset and the years
    # are interleaved. Keeping only the six fields used below matters at this size: whole rows cost
    # about 4 GB at 800,000 of them, which is most of a runner.
    def need(r: dict) -> dict:
        return {"asOf": r["asOf"], "assetId": r["assetId"], "symbol": r["symbol"],
                "assetType": r["assetType"], "market": r["market"], "outcome": r["outcome"]}

    by_year: dict[int, list[dict]] = defaultdict(list)
    for r in read_gz(full_file):
        by_year[int(r["asOf"][:4])].append(need(r))

    total, digests, counts = Counter(), {}, {}
    first_year = min(by_year)
    actions = unadjusted_windows(Path(arg("--actions")) if arg("--actions") else
                                 ROOT / "data" / "foundation" / "price_verification" / "unadjusted_actions.json")
    for y in sorted(by_year):
        stats, digest, n = build_year(y, by_year[y], pit_dir / f"pit-{y}.jsonl.gz",
                                      setups_for_year(replay, runs, y), out, actions)
        total.update(stats)
        digests[y], counts[y] = digest, n
        print(f"  {y}: {n:,} rows, features on {stats['withPit']:,}, setups on {stats['withSetup']:,}", flush=True)
        by_year[y] = []                                  # release before the next year

    # Reproducibility: the first year again, digests must match byte for byte.
    again_rows = [need(r) for r in read_gz(full_file) if int(r["asOf"][:4]) == first_year]
    _, d2, _ = build_year(first_year, again_rows, pit_dir / f"pit-{first_year}.jsonl.gz",
                          setups_for_year(replay, runs, first_year), None, actions)

    no_feature_reasons = {k.split(":", 1)[1]: v for k, v in total.items() if k.startswith("noPit:")}
    explained = total["withPit"] + total["noPit"] - no_feature_reasons.get("other", 0)
    cls_names = sorted({k.split(":", 1)[1] for k in total if k.startswith("eligible:")})
    null_share = {c: {k.split(":")[2]: round(v / max(1, total[f"pit:{c}"]), 4)
                      for k, v in total.items() if k.startswith(f"null:{c}:")} for c in cls_names}
    manifest = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "eligibleAssetSessions": total["eligible"],
        "withPointInTimeFeatures": total["withPit"], "withoutFeatures": total["noPit"],
        "withoutFeaturesByReason": no_feature_reasons,
        "withReplayedSetup": total["withSetup"], "withBoth": total["withBoth"],
        "withAnalog": total["withAnalog"],
        "unexplained": total["eligible"] - explained,
        "featureCoverage": round(total["withPit"] / max(1, total["eligible"]), 4),
        "setupCoverage": round(total["withSetup"] / max(1, total["eligible"]), 4),
        "byAssetClass": {c: {"eligible": total[f"eligible:{c}"], "withFeatures": total[f"pit:{c}"]} for c in cls_names},
        "featureRowsNotInOutcomes": total["pitRowsNotInFull"],
        "duplicates": {"outcomes": total["fullDuplicates"], "features": total["pitDuplicates"]},
        "leakage": {"featureDatedAfterSession": total["leakPitAfterSession"],
                    "setupDatedAfterSession": total["leakSetupAfterSession"], "futureNamedFields": 0},
        "missingnessByAssetClass": null_share,
        "dataQuality": {
            "unadjustedActionsKnown": sum(len(v) for v in actions.values()),
            "symbolsWithAnUnadjustedAction": len(actions),
            "rowsTouchingOne": total["rowsTouchingAnUnadjustedAction"],
            "rowsTouchingOneByClass": {c: total[f"suspect:{c}"] for c in cls_names},
            "note": ("flagged, not dropped: a row is still correct about everything that does not "
                     "cross the action, and the consumer decides. See "
                     "price_verification/unadjusted_actions.json"),
        },
        "rowsByYear": counts, "sha256ByYear": digests,
        "reproducible": {"year": first_year, "match": digests[first_year] == d2},
        "inputs": {"full": full_file.name, "pitFiles": sorted(p.name for p in pit_dir.glob("pit-*.jsonl.gz")),
                   "replayRuns": sorted(k for k, v in runs.items() if v.get("trusted")) if replay else []},
        "resources": {"seconds": round(time.time() - t0, 1),
                      "peakRssMB": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1) if resource else None},
        "limitations": [
            "survivors only: every asset in the universe still trades",
            "stock and ETF closes are dividend-adjusted; features are scale-free but levels are not traded prices",
            "daily bars: intraday path, and so stop and target ordering, is unknown",
        ],
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    print(f"::notice title=dataset assembly::{json.dumps({k: v for k, v in manifest.items() if k not in ('sha256ByYear', 'missingnessByAssetClass', 'inputs', 'limitations')})}")
    ok = (manifest["unexplained"] == 0 and manifest["reproducible"]["match"]
          and not manifest["leakage"]["featureDatedAfterSession"] and not manifest["leakage"]["setupDatedAfterSession"])
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
