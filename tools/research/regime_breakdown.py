"""Assign a session to a named market regime, so results can be read per regime.

    from regime_breakdown import episode_of, episodes_in_training, stratify

**Why this is an evaluation consumer and never a feature.** A regime window is drawn after the
fact: "the 2022 rate-shock bear" is known to have ended only once it had. Handing that label to a
model as an input would tell it the future of the very period it is predicting, which is the
look-ahead leakage the dataset's own checks exist to prevent. So the regime layer is routed to
`evaluation-stratification` in `tools/foundation/context_routing.py`: it splits measured results
for reporting and never enters a predictor.

**A session outside every episode is `none`, not "calm".** The episodes cover drawdowns and named
stress windows; the rest of the record is simply unlabelled. Calling it calm would be a claim the
episode list never made.

Source of truth is `data/foundation/dataset/historical_regimes.json`, whose `namedEpisodes` carry
`inTrainingData` -- so the eight episodes that predate 2018 are excluded here rather than silently
matching nothing.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
REGIMES_FILE = ROOT / "data" / "foundation" / "dataset" / "historical_regimes.json"

OUTSIDE = "none"


def episodes_in_training(path: Path | None = None) -> list[tuple[str, str, str]]:
    """`(name, start, end)` for every named episode that overlaps the training data."""
    p = path or REGIMES_FILE
    payload = json.loads(p.read_text(encoding="utf-8"))
    out = []
    for e in payload.get("namedEpisodes") or []:
        if not e.get("inTrainingData"):
            continue
        window = e.get("window") or []
        if len(window) == 2 and all(window):
            out.append((e["episode"], window[0], window[1]))
    return sorted(out, key=lambda t: t[1])


def episode_of(date: str, episodes: list[tuple[str, str, str]]) -> str:
    """The first episode whose window contains `date`, or `OUTSIDE`.

    Windows can overlap -- a recovery can begin inside a drawdown -- so the earliest-starting
    match wins and the choice is stated rather than left to dictionary order.
    """
    for name, lo, hi in episodes:
        if lo <= date <= hi:
            return name
    return OUTSIDE


def stratify(dates, truth, pred, keys) -> dict:
    """Accuracy against the majority-class rate, grouped by each key in `keys`.

    `keys` maps a group name to a sequence aligned with `dates`. Every group reports its own
    majority rate, because a group's accuracy is meaningless against another group's base rate.
    """
    out: dict[str, dict] = {}
    for key_name, values in keys.items():
        buckets: dict[str, list[tuple[int, int]]] = defaultdict(list)
        for v, t, p in zip(values, truth, pred):
            buckets[v].append((t, p))
        rows = {}
        for group, pairs in sorted(buckets.items()):
            if not pairs:
                continue
            n = len(pairs)
            hits = sum(1 for t, p in pairs if t == p)
            maj = Counter(t for t, _ in pairs).most_common(1)[0][1]
            rows[group] = {
                "n": n,
                "accuracy": round(hits / n, 4),
                "majorityRate": round(maj / n, 4),
                "margin": round(hits / n - maj / n, 4),
            }
        out[key_name] = rows
    return out
