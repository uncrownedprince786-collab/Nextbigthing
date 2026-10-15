"""What was knowable about a macro series on a given day, and nothing more than that.

    from macro_context import as_of, context_for, SERIES_DIR

This is the macro layer's runtime consumer. `context_routing.py` routes macro to
`decision-context` and `integrity-veto`, never to `directional-evidence`, so **every record this
module returns is a reading with its provenance and no direction at all**. There is deliberately
no field a caller could read as a vote: a market-wide series handed to 616 instruments as a
per-asset direction is one fact counted 616 times, and `lib/decision.ts` already says of
`macroVeto` that it is "A veto only: it can turn a LONG or SHORT into a WAIT and can do nothing
else."

**Two publication rules, because the data has two kinds of series.**

*Unrevised series* (22 of 32) carry `availableAt` on every row -- the day the value was first
published. A reading is knowable on a decision date when `availableAt <= decision_date`. Nothing
else qualifies, which is what stops a CPI print dated the 1st being read on the 1st when it was
not published until the 16th.

*Revision-tracked series* (10 of 32) also carry a vintage file: `obs`, `firstSeen`, and a
`history` of `[date, value]` pairs, one per revision. For those the knowable value is the **last
revision published on or before the decision date**, not the final value -- a GDP figure revised
twice is three different facts, and a backtest that uses the third on the day the first was
printed is reading the future.

**Staleness is reported, never hidden.** A record carries `ageDays`, so a quarterly series read
eleven months later is visibly eleven months old rather than quietly current. Nothing here decides
what age is too old; that belongs to the consumer, and a reading that cannot be found returns
`None` rather than a default.
"""

from __future__ import annotations

import csv
import json
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
SERIES_DIR = ROOT / "data" / "foundation" / "macro"
VINTAGE_DIR = SERIES_DIR / "vintages"
MANIFEST = SERIES_DIR / "manifest.json"


def _d(text: str) -> date:
    return date.fromisoformat(text.strip())


def available_series(series_dir: Path | None = None) -> list[str]:
    """Series codes with a stored CSV, sorted."""
    d = series_dir or SERIES_DIR
    return sorted(p.stem for p in d.glob("*.csv"))


def _rows(code: str, series_dir: Path) -> list[tuple[date, str, date]]:
    """`(observation_date, value, availableAt)` for one series, oldest first."""
    path = series_dir / f"{code}.csv"
    if not path.exists():
        return []
    out = []
    with path.open(newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            raw = (r.get("value") or "").strip()
            avail = (r.get("availableAt") or "").strip()
            obs = (r.get("observation_date") or "").strip()
            if not raw or raw == "." or not avail or not obs:
                continue          # a missing print is missing, not zero
            out.append((_d(obs), raw, _d(avail)))
    out.sort(key=lambda t: (t[2], t[0]))
    return out


def _vintage(code: str, vintage_dir: Path) -> dict[str, list[tuple[date, str]]]:
    """`observation -> [(published, value), ...]` from the revision history, oldest first."""
    path = vintage_dir / f"{code}.jsonl"
    if not path.exists():
        return {}
    out: dict[str, list[tuple[date, str]]] = {}
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            rec = json.loads(line)
            hist = [(_d(d), v) for d, v in (rec.get("history") or []) if d and v not in (None, "")]
            if hist:
                out[rec["obs"]] = sorted(hist)
    return out


def as_of(code: str, on: date | str, series_dir: Path | None = None,
          vintage_dir: Path | None = None) -> dict | None:
    """The newest reading of `code` that was published on or before `on`, or `None`.

    `None` means nothing was knowable -- an unknown code, a date before the series began, or a
    series whose first publication is still in the future. It is never a zero and never the
    nearest value from the wrong side of the publication date.
    """
    on = on if isinstance(on, date) else _d(on)
    sd = series_dir or SERIES_DIR
    vd = vintage_dir or VINTAGE_DIR
    rows = _rows(code, sd)
    if not rows:
        return None

    known = [r for r in rows if r[2] <= on]
    if not known:
        return None

    # **Why the vintage wins outright for a tracked series.** The CSV pairs the *latest revised*
    # value with the *first* publication date. For CPI's 2010-01-01 observation it stores
    # availableAt 2010-02-16 beside 217.488 -- but the vintage history shows 217.488 is the
    # 2015-02-28 revision, and what was actually printed in 2010 was 217.587. Reading `value`
    # off that row on its own `availableAt` would hand a decision a figure five years early.
    # So where a revision history exists it is the only source of the value, and the CSV is used
    # for nothing but knowing which observations exist.
    vint = _vintage(code, vd)
    if vint:
        for obs, _csv_value, _csv_published in sorted(known, key=lambda t: t[0], reverse=True):
            seen = [h for h in vint.get(obs.isoformat(), []) if h[0] <= on]
            if seen:
                published, value = seen[-1]
                revisions = len(seen) - 1
                break
        else:
            return None            # nothing in this series had been printed yet
    else:
        obs, value, published = max(known, key=lambda t: (t[2], t[0]))
        revisions = 0

    return {
        "series": code,
        "observationDate": obs.isoformat(),
        "value": value,                        # kept as text: the source's own precision
        "availableAt": published.isoformat(),
        "asOf": on.isoformat(),
        "ageDays": (on - obs).days,
        "revisionsKnown": revisions,
        "revisionTracked": bool(vint),
        "source": f"data/foundation/macro/{code}.csv",
    }


def context_for(on: date | str, codes: list[str] | None = None,
                series_dir: Path | None = None, vintage_dir: Path | None = None) -> dict:
    """Every requested series as it stood on `on`, with the ones that were not knowable named.

    The absent list is part of the answer. A context block that silently omits what it could not
    read is indistinguishable from one where everything was fine.
    """
    sd = series_dir or SERIES_DIR
    wanted = codes if codes is not None else available_series(sd)
    readings, absent = {}, []
    for c in wanted:
        rec = as_of(c, on, sd, vintage_dir)
        if rec is None:
            absent.append(c)
        else:
            readings[c] = rec
    return {
        "asOf": on if isinstance(on, str) else on.isoformat(),
        "readings": readings,
        "notKnowable": absent,
        "role": "decision-context",
        "mayVote": False,
    }
