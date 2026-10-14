"""Re-replay a sample of sessions and require byte-identical output: the leakage test for the replay.

    python tools/determinism_check.py --outputs outputs --runs runs.json --n 40 --seed 20261014

A replay of session D is supposed to depend only on data dated D or earlier. The strongest test of
that is time: run it again after the database has changed -- new closes, new news, new derived
rows all written since -- and compare. If the two outputs differ, something the replay reads
depends on data from after D.

This is the test that would have caught the two unbounded reads fixed in 7cae2f6
(`all_industry_relative` and the `AssetAnalog` read in `decide.mjs`): the divergence between two
copies of the same session appeared the moment `cron-us-prices` wrote new closes mid-run.

Sampling is stratified so every year is represented, seeded so the same sessions can be re-checked,
and always includes the earliest and latest sessions, where edge handling is most likely to differ.

Read-only against the database; replays into a scratch directory.
"""

from __future__ import annotations

import hashlib
import json
import random
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from reconcile_replay import RUN, check_pair  # noqa: E402
from worker import arg, replay_one  # noqa: E402


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def canonical(outputs: Path, runs: dict) -> dict[str, dict]:
    """The newest valid output per date from a run whose code matches the current replay code."""
    best: dict[str, tuple[int, dict]] = {}
    for art in sorted(p for p in outputs.iterdir() if p.is_dir()):
        m = RUN.fullmatch(art.name)
        rid = int(m.group(1)) if m else 0
        if not runs.get(str(rid), {}).get("trusted"):
            continue
        for dec in art.rglob("decisions-*.json"):
            day = dec.stem.removeprefix("decisions-")
            st = dec.parent / f"setups-{day}.jsonl"
            if check_pair(dec, st, day) is None and (day not in best or rid > best[day][0]):
                best[day] = (rid, {"decisions": dec, "setups": st, "run": str(rid)})
    return {d: v[1] for d, v in best.items()}


def stratified(days: list[str], n: int, seed: int) -> list[str]:
    rng = random.Random(seed)
    by_year: dict[str, list[str]] = {}
    for d in days:
        by_year.setdefault(d[:4], []).append(d)
    picks = {days[0], days[-1]}
    per = max(1, (n - 2) // max(1, len(by_year)))
    for y, ds in sorted(by_year.items()):
        picks.update(rng.sample(ds, min(per, len(ds))))
    rest = [d for d in days if d not in picks]
    rng.shuffle(rest)
    while len(picks) < n and rest:
        picks.add(rest.pop())
    return sorted(picks)[:max(n, 2)]


def main() -> int:
    outputs = Path(arg("--outputs"))
    runs = json.loads(Path(arg("--runs")).read_text(encoding="utf-8"))
    n, seed = int(arg("--n") or 40), int(arg("--seed") or 20261014)
    canon = canonical(outputs, runs)
    if not canon:
        print("::error title=determinism::no trusted verified outputs to compare against")
        return 2
    sample = stratified(sorted(canon), n, seed)
    differ, failed = [], []
    with tempfile.TemporaryDirectory() as tmp:
        from datetime import date
        for day in sample:
            r = replay_one(date.fromisoformat(day), Path(tmp))
            if not r["ok"]:
                failed.append({"day": day, "stage": r.get("stage"), "error": r.get("error", "")[:120]})
                continue
            same_dec = sha(Path(tmp) / f"decisions-{day}.json") == sha(canon[day]["decisions"])
            same_set = sha(Path(tmp) / f"setups-{day}.jsonl") == sha(canon[day]["setups"])
            if not (same_dec and same_set):
                differ.append({"day": day, "run": canon[day]["run"],
                               "decisionsDiffer": not same_dec, "setupsDiffer": not same_set})
    report = {"verdict": "PASS" if not differ and not failed else "FAIL",
              "canonicalSessions": len(canon), "sampled": len(sample), "identical": len(sample) - len(differ) - len(failed),
              "differing": differ[:30], "replayFailures": failed[:10],
              "seed": seed, "sampleYears": sorted({d[:4] for d in sample})}
    Path("determinism.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(f"::notice title=determinism {report['verdict']}::{json.dumps(report)}")
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
