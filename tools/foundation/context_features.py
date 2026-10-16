"""The contextual state as it was knowable at a session's close, for one instrument.

    python tools/foundation/context_features.py --as-of 2024-03-01 [--symbol AAPL]
    python tools/foundation/context_features.py --coverage [--out DIR]

What this is
------------
`context_routing.py` records that every context layer has a consumer and that every consumer
resolves. It does **not** claim any of them reaches the model, and a direct read of a dataset row
confirms they do not: `pit.f` holds fifteen price and volume fields and the row carries no context
block at all. This file is the missing producer -- the seam between layers that are already built,
already point-in-time aware and already tested, and a feature vector that has never seen them.

It is a **producer only**. Nothing here joins a dataset, freezes anything or trains anything; those
are the next milestone and are deliberately not started here. What this gives them is a function
that answers one question honestly: *what could have been known about the world at the close of
this session, for this instrument, without reading one byte dated after it.*

The availability rules, and why they are not all the same
---------------------------------------------------------
* **Macro and rates** come from `macro_pit.py`'s artifact, whose every row already holds, for date
  D, each series' newest observation whose **`availableAt`** is on or before D -- not the newest
  observation *dated* on or before D, which is the mistake that makes a macro backtest look
  prescient. The row for D is therefore safe to read **at** D, and this is the one layer where
  `<= as_of` is correct rather than sloppy. Its manifest records
  `observationsDatedAfterTheirSession: 0`.
* **Events, press and filings** are read **strictly before** `as_of`. An event dated on the
  session itself is not yet a fact about a decision taken at that session's close -- the project's
  routing table states the rule as "publication time strictly before the decision timestamp", and
  strictness is what keeps an announcement from informing the bar it moved.
* **Reaction priors** need more than their own date: a prior built from a forward window is only
  knowable once that window has **closed**. The artifact dates its own windows, so the rule reads
  `forward["20"].exitSession < as_of` rather than an assumed number of calendar days. An event
  from last week contributes nothing yet, and saying so costs a row that was never ours.

What is deliberately excluded, and why that is the honest answer
----------------------------------------------------------------
* **The operational news feed is excluded from historical features.** `jobs/lineage.py` prunes it
  at 70 days, so for any session older than that there is nothing stored and never was. A
  historical feature built from it would be measuring the retention window, not the news. The
  exclusion is reported as a field, not omitted, because a reader is entitled to know that one of
  the six layers could not be done rather than to find five and assume six.
* **An event's `market` block is never read.** It holds `peakDate`, `z` and `returnPct` -- the
  market's reaction *to* the event, which is the future at the event's own date. `FORBIDDEN_KEYS`
  names it and a test asserts no value under it reaches a feature.
* **Levels are excluded; changes and ages are not.** A trending level is a proxy for the date, and
  a model handed one learns the calendar. The recorded context experiment fixed this already
  (`levelsExcluded: "chg only"`), and that decision is inherited here rather than re-litigated.

Missing is missing
------------------
Every block carries a `status`. An absent reading is `None` with `status` `"absent"`, never a zero
and never a neutral: "could not look" is not "nothing there". A consumer that wants a number for a
missing input must choose one itself, visibly, which is the only way that choice stays reviewable.

`mayVote` is untouched. Nothing here casts a direction; these are non-voting inputs to a learned
model and explanatory evidence, exactly the role the policy already permits them.
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from bisect import bisect_right
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent

DEFAULT_MACRO = ROOT / ".cache" / "foundation" / "macro_rebuild" / "macro-sessions.jsonl.gz"
EVENTS = ROOT / "data" / "foundation" / "events" / "events.json"
PRESS = ROOT / "data" / "foundation" / "events" / "press_evidence.jsonl"
REACTIONS = ROOT / "data" / "foundation" / "events" / "reactions.jsonl.gz"
OUT_DIR = ROOT / "data" / "foundation" / "dataset"

VERSION = "context-features-v1"

#: The macro and rate series carried into features, in a fixed order because a model's feature
#: vector is positional. Ten of the artifact's thirty-one: the curve and policy rate, the
#: inflation expectation, two risk gauges, the dollar and oil, and the one weekly labour series
#: with a real publication lag. The rest are monthly or quarterly and move too rarely to inform a
#: twenty-session decision without mostly measuring their own staleness.
SERIES = ("DGS10", "T10Y2Y", "T10Y3M", "DFF", "T10YIE",
          "VIXCLS", "NFCI", "DTWEXBGS", "DCOILWTICO", "ICSA")

#: A series contributes `chg` and `age`, never `v`. See the module docstring: a level is a proxy
#: for the date. `age` is kept because a fresh print and a stale one are different evidence and a
#: consumer cannot tell them apart from the change alone.
PER_SERIES = ("chg", "age")

#: Lookback for the count features. Ninety days is the shortest window that holds more than one
#: quarter's events for most instruments without reaching back into a different regime.
WINDOW_DAYS = 90

#: Read from an event record. Everything else -- `market` above all -- is the future at the
#: event's own date and may never reach a feature.
EVENT_KEYS = ("date", "category", "instrument", "tier", "verified", "cluster", "name")
FORBIDDEN_KEYS = ("market", "wikidata", "wikipedia")

#: The horizon whose window must have closed before a reaction may inform a prior.
PRIOR_HORIZON = "20"

NEWS_EXCLUSION = (
    "operational news feed: jobs/lineage.py prunes it at 70 days, so no historical corpus exists "
    "for any session older than that. A feature built from it would measure the retention window "
    "rather than the news."
)


def _d(s: str) -> date:
    return date.fromisoformat(s[:10])


def _median(xs: list[float]) -> float | None:
    if not xs:
        return None
    xs = sorted(xs)
    n = len(xs)
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2


class ContextSource:
    """Every context artifact, indexed once, answering by date and instrument.

    Built with `load()`. Holding the indexes on an instance rather than in module globals is what
    lets a test construct one from fixtures without touching the repository's own artifacts, and
    lets a dataset build hold exactly one copy across a million rows.
    """

    def __init__(self, macro_dates, macro_rows, events, press, reactions, provenance):
        self.macro_dates = macro_dates          # sorted list[date]
        self.macro_rows = macro_rows            # parallel list[dict]
        self.events = events                    # instrument -> sorted list[(date, rec)]
        self.press = press                      # instrument -> sorted list[date]
        self.reactions = reactions              # instrument -> list[(exitSession, returnPct)]
        self.provenance = provenance

    # -- loading ---------------------------------------------------------------------------

    @classmethod
    def load(cls, macro: Path = DEFAULT_MACRO, events: Path = EVENTS,
             press: Path = PRESS, reactions: Path = REACTIONS) -> "ContextSource":
        prov: dict = {"version": VERSION, "loadedAt": datetime.now(timezone.utc)
                      .isoformat(timespec="seconds")}

        macro_dates: list[date] = []
        macro_rows: list[dict] = []
        if Path(macro).exists():
            with gzip.open(macro, "rt", encoding="utf-8") as fh:
                for line in fh:
                    r = json.loads(line)
                    macro_dates.append(_d(r["d"]))
                    macro_rows.append(r["m"])
            order = sorted(range(len(macro_dates)), key=macro_dates.__getitem__)
            macro_dates = [macro_dates[i] for i in order]
            macro_rows = [macro_rows[i] for i in order]
        prov["macro"] = {"path": str(macro), "present": bool(macro_dates), "rows": len(macro_dates),
                         "rule": "newest observation whose availableAt <= D (macro_pit.py)"}

        ev: dict[str, list] = defaultdict(list)
        if Path(events).exists():
            doc = json.loads(Path(events).read_text(encoding="utf-8"))
            for e in doc.get("events", []):
                if not e.get("verified"):
                    continue          # an unverified candidate is not evidence
                rec = {k: e.get(k) for k in EVENT_KEYS}
                ev[e.get("instrument") or "MKT"].append((_d(e["date"]), rec))
        for k in ev:
            ev[k].sort(key=lambda t: t[0])
        prov["events"] = {"path": str(events), "present": bool(ev),
                          "instruments": len(ev), "rows": sum(len(v) for v in ev.values()),
                          "rule": "verified events only, date strictly before as_of",
                          "neverRead": list(FORBIDDEN_KEYS)}

        pr: dict[str, list] = defaultdict(list)
        if Path(press).exists():
            seen: set[tuple] = set()
            for line in Path(press).read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                r = json.loads(line)
                pub = r.get("publishedAt")
                if not pub:
                    continue          # no publication time, no availability, no feature
                key = (r.get("instrument"), r.get("dedupeKey") or r.get("url"), pub[:10])
                if key in seen:
                    continue          # the same article under two routes is one article
                seen.add(key)
                pr[r.get("instrument") or "MKT"].append(_d(pub))
        for k in pr:
            pr[k].sort()
        prov["press"] = {"path": str(press), "present": bool(pr),
                         "instruments": len(pr), "rows": sum(len(v) for v in pr.values()),
                         "rule": "publishedAt strictly before as_of; retrievedAt is never "
                                 "treated as availability"}

        rx: dict[str, list] = defaultdict(list)
        if Path(reactions).exists():
            with gzip.open(reactions, "rt", encoding="utf-8") as fh:
                for line in fh:
                    r = json.loads(line)
                    fwd = (r.get("forward") or {}).get(PRIOR_HORIZON) or {}
                    exit_session, ret = fwd.get("exitSession"), fwd.get("returnPct")
                    if not exit_session or ret is None:
                        continue      # an unclosed or unmeasured window is not a prior
                    key = r.get("symbol") or r.get("instrument")
                    if key:
                        rx[key].append((_d(exit_session), float(ret)))
        for k in rx:
            rx[k].sort(key=lambda t: t[0])
        prov["reactions"] = {"path": str(reactions), "present": bool(rx),
                             "instruments": len(rx), "rows": sum(len(v) for v in rx.values()),
                             "rule": f"forward['{PRIOR_HORIZON}'].exitSession strictly before "
                                     "as_of; an open window is not a prior"}
        prov["news"] = {"status": "excluded", "reason": NEWS_EXCLUSION}
        return cls(macro_dates, macro_rows, dict(ev), dict(pr), dict(rx), prov)

    # -- the blocks ------------------------------------------------------------------------

    def macro_at(self, as_of: date) -> dict:
        """The macro and rate state knowable at `as_of`, as changes and ages."""
        if not self.macro_dates:
            return {"status": "absent", "reason": "no macro artifact loaded", "f": self._nulls()}
        i = bisect_right(self.macro_dates, as_of) - 1
        if i < 0:
            return {"status": "absent", "reason": "as_of precedes the macro artifact",
                    "f": self._nulls()}
        row, used = self.macro_rows[i], self.macro_dates[i]
        f: dict[str, float | None] = {}
        for s in SERIES:
            o = row.get(s) or {}
            for k in PER_SERIES:
                v = o.get(k)
                f[f"macro_{s}_{k}"] = None if v is None else float(v)
        return {"status": "observed", "asOf": used.isoformat(),
                "ageDays": (as_of - used).days, "f": f}

    def events_at(self, as_of: date, instrument: str | None) -> dict:
        """Dated events for this instrument and market-wide, strictly before `as_of`."""
        keys = [k for k in ({instrument, "MKT"} if instrument else {"MKT"}) if k]
        rows = [t for k in keys for t in self.events.get(k, []) if t[0] < as_of]
        if not any(k in self.events for k in keys):
            return {"status": "absent", "reason": "no event record for this instrument",
                    "f": {"ctx_eventsIn90d": None, "ctx_daysSinceEvent": None}}
        rows.sort(key=lambda t: t[0])
        recent = [t for t in rows if (as_of - t[0]).days <= WINDOW_DAYS]
        last = rows[-1][0] if rows else None
        return {"status": "observed",
                "f": {"ctx_eventsIn90d": float(len(recent)),
                      "ctx_daysSinceEvent": None if last is None else float((as_of - last).days)}}

    def press_at(self, as_of: date, instrument: str | None) -> dict:
        """Press and official-document records published strictly before `as_of`."""
        keys = [k for k in ({instrument, "MKT"} if instrument else {"MKT"}) if k]
        if not any(k in self.press for k in keys):
            return {"status": "absent", "reason": "no press record for this instrument",
                    "f": {"ctx_pressIn90d": None}}
        n = sum(1 for k in keys for d in self.press.get(k, [])
                if d < as_of and (as_of - d).days <= WINDOW_DAYS)
        return {"status": "observed", "f": {"ctx_pressIn90d": float(n)}}

    def prior_at(self, as_of: date, instrument: str | None) -> dict:
        """Reaction priors whose forward window had already closed before `as_of`."""
        if not instrument or instrument not in self.reactions:
            return {"status": "absent", "reason": "no matured reaction for this instrument",
                    "f": {"ctx_maturedPriors": None, "ctx_priorMedianFwd20": None}}
        matured = [ret for exit_s, ret in self.reactions[instrument] if exit_s < as_of]
        if not matured:
            return {"status": "absent", "reason": "no reaction window had closed by this session",
                    "f": {"ctx_maturedPriors": 0.0, "ctx_priorMedianFwd20": None}}
        return {"status": "observed",
                "f": {"ctx_maturedPriors": float(len(matured)),
                      "ctx_priorMedianFwd20": _median(matured)}}

    def at(self, as_of: date | str, instrument: str | None = None) -> dict:
        """The whole context block for one asset-session. Never reads past `as_of`."""
        if isinstance(as_of, str):
            as_of = _d(as_of)
        return {
            "asOf": as_of.isoformat(),
            "instrument": instrument,
            "version": VERSION,
            "macro": self.macro_at(as_of),
            "events": self.events_at(as_of, instrument),
            "press": self.press_at(as_of, instrument),
            "reactionPrior": self.prior_at(as_of, instrument),
            "news": {"status": "excluded", "reason": NEWS_EXCLUSION, "f": {}},
        }

    # -- the vector ------------------------------------------------------------------------

    @staticmethod
    def _nulls() -> dict[str, None]:
        return {f"macro_{s}_{k}": None for s in SERIES for k in PER_SERIES}

    @staticmethod
    def feature_names() -> list[str]:
        """The ordered feature names. A model's vector is positional, so this is the contract."""
        names = [f"macro_{s}_{k}" for s in SERIES for k in PER_SERIES]
        names += ["ctx_eventsIn90d", "ctx_daysSinceEvent", "ctx_pressIn90d",
                  "ctx_maturedPriors", "ctx_priorMedianFwd20"]
        return names

    @staticmethod
    def vector(block: dict) -> list[float | None]:
        """`block` flattened into `feature_names()` order, **keeping None as None**.

        A missing value is handed on as missing. Turning it into 0.0 here would bury the one fact
        the consumer needs to decide anything, and every consumer in this repository that has
        wanted a number for an absent input has chosen it visibly at the point of use.
        """
        flat: dict[str, float | None] = {}
        for part in ("macro", "events", "press", "reactionPrior", "news"):
            flat.update((block.get(part) or {}).get("f") or {})
        return [flat.get(n) for n in ContextSource.feature_names()]


# -- coverage ------------------------------------------------------------------------------

def coverage(src: ContextSource, sessions: list[date], instruments: list[str]) -> dict:
    """How often each block actually answers, measured rather than assumed.

    A producer that returns a block for every row proves nothing; what matters is how many of
    those blocks carry an observation. Reported per block so a thin layer cannot hide inside a
    healthy average.
    """
    seen = {k: 0 for k in ("macro", "events", "press", "reactionPrior")}
    nulls = {n: 0 for n in ContextSource.feature_names()}
    rows = 0
    for d in sessions:
        for inst in instruments:
            b = src.at(d, inst)
            rows += 1
            for k in seen:
                if (b[k] or {}).get("status") == "observed":
                    seen[k] += 1
            for name, v in zip(ContextSource.feature_names(), ContextSource.vector(b)):
                if v is None:
                    nulls[name] += 1
    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "version": VERSION,
        "rowsMeasured": rows,
        "sessions": len(sessions), "instruments": len(instruments),
        "observedShareByBlock": {k: round(v / rows, 4) if rows else None for k, v in seen.items()},
        "nullShareByFeature": {k: round(v / rows, 4) if rows else None for k, v in nulls.items()},
        "featureOrder": ContextSource.feature_names(),
        "excluded": {"operational news feed": NEWS_EXCLUSION},
        "provenance": src.provenance,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--as-of")
    ap.add_argument("--symbol")
    ap.add_argument("--coverage", action="store_true")
    ap.add_argument("--out", default=str(OUT_DIR))
    a = ap.parse_args()

    src = ContextSource.load()
    for k in ("macro", "events", "press", "reactions"):
        p = src.provenance[k]
        print(f"  {k:<10} present={str(p['present']):<5} rows={p.get('rows')}")
    print(f"  news       EXCLUDED -- {NEWS_EXCLUSION[:60]}...")

    if a.coverage:
        if not src.macro_dates:
            raise SystemExit("no macro artifact; rebuild it before measuring coverage")
        step = max(1, len(src.macro_dates) // 200)
        sessions = src.macro_dates[::step]
        insts = sorted(set(list(src.events) + list(src.press) + list(src.reactions)))[:40]
        rep = coverage(src, sessions, insts or ["MKT"])
        out = Path(a.out) / "context_features_coverage.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(rep, indent=1), encoding="utf-8")
        print(f"\nrows {rep['rowsMeasured']}  observed share by block:")
        for k, v in rep["observedShareByBlock"].items():
            print(f"  {k:<14} {v}")
        print(f"wrote {out}")
        return 0

    if a.as_of:
        print()
        print(json.dumps(src.at(a.as_of, a.symbol), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
