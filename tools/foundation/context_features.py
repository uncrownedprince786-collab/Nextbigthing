"""The contextual state as it was knowable at a session's close, for one instrument.

    python tools/foundation/context_features.py --as-of 2024-03-01 [--symbol AAPL] [--market US]
    python tools/foundation/context_features.py --coverage [--out DIR]

What this is
------------
`context_routing.py` records that every context layer has a consumer and that every consumer
resolves. It does **not** claim any of them reaches the model, and a direct read of a dataset row
confirms they do not: `pit.f` holds fifteen price and volume fields and the row carries no context
block at all. This file is the missing producer -- the seam between layers that are already built,
already point-in-time aware and already tested, and a feature vector that has never seen them.

It is a **producer only**: `assemble.py` performs the join, and the dataset freeze and training are
downstream of that.

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
  `forward["20"].exitSession < as_of` rather than an assumed number of calendar days.

Scope: market-wide, instrument-specific, or unresolved -- never silently the first
--------------------------------------------------------------------------------------
The first version of this file let every named instrument fall back to `MKT`, which read as 100%
coverage and meant that one company's earnings counted as context for all 617 names. The scopes are
now separate fields, and a record contributes to exactly one of three:

* **market** -- the corpus says `MKT`, or the name scopes to a whole market (`MARKET_SCOPED`).
  Contributes to every row, or to every row of that market.
* **own** -- the name resolves, after `ALIASES`, to a symbol in the universe. Contributes to that
  symbol's rows and to nothing else.
* **unresolved** -- it resolves to neither. **Counted in its own feature and dropped from both
  scopes.** A record whose subject we cannot establish is not market-wide news; it is a record we
  could not place, and the difference is the whole point of this paragraph.

**`PSX` is why this needs a table rather than a rule.** In the events corpus it is the Pakistan
Stock Exchange; in the universe it is Phillips 66's ticker. Matching on the string would have
attached Pakistani geopolitical events to a US refiner -- not a look-ahead leak, a *wrong subject*
leak, which no date check would ever catch. It is market-scoped to `PK`, and
`tests/test_context_features.py` pins that Phillips 66 never sees it.

What is deliberately excluded, and why that is the honest answer
----------------------------------------------------------------
* **The operational news feed is excluded from historical features.** `jobs/lineage.py` prunes it
  at 70 days, so for any session older than that there is nothing stored and never was. A
  historical feature built from it would be measuring the retention window, not the news. The
  exclusion is reported as a field, not omitted, because a reader is entitled to know that one of
  the six layers could not be done rather than to find five and assume six. A **live-only** news
  input at inference time is a separate question and is not answered here; nothing may turn such a
  field into a historical training feature.
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
missing input must choose one itself, visibly.

`mayVote` is untouched. Nothing here casts a direction; these are non-voting inputs to a learned
model and explanatory evidence, exactly the role the policy already permits them.
"""

from __future__ import annotations

import argparse
import gzip
import json
from bisect import bisect_right
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent

DEFAULT_MACRO = ROOT / ".cache" / "foundation" / "macro_rebuild" / "macro-sessions.jsonl.gz"
DEFAULT_DATASET = ROOT / ".cache" / "foundation" / "dataset_full"
EVENTS = ROOT / "data" / "foundation" / "events" / "events.json"
PRESS = ROOT / "data" / "foundation" / "events" / "press_evidence.jsonl"
REACTIONS = ROOT / "data" / "foundation" / "events" / "reactions.jsonl.gz"
OUT_DIR = ROOT / "data" / "foundation" / "dataset"

VERSION = "context-features-v2"

#: The macro and rate series carried into features, in a fixed order because a model's feature
#: vector is positional. Ten of the artifact's thirty-one: the curve and policy rate, the
#: inflation expectation, two risk gauges, the dollar and oil, and the one weekly labour series
#: with a real publication lag. The rest are monthly or quarterly and move too rarely to inform a
#: twenty-session decision without mostly measuring their own staleness.
SERIES = ("DGS10", "T10Y2Y", "T10Y3M", "DFF", "T10YIE",
          "VIXCLS", "NFCI", "DTWEXBGS", "DCOILWTICO", "ICSA")

#: A series contributes `chg` and `age`, never `v`. See the module docstring: a level is a proxy
#: for the date. `age` is kept because a fresh print and a stale one are different evidence.
PER_SERIES = ("chg", "age")

#: Lookback for the count features.
WINDOW_DAYS = 90

#: The corpus's name for a market-wide record.
MARKET_WIDE = "MKT"

#: Context-corpus names that are real instruments under a different spelling in the universe.
ALIASES = {"BTC": "btc-bitcoin", "ETH": "eth-ethereum", "OIL": "CL=F"}

#: Names that scope to a whole market rather than to one instrument, mapped to the dataset's
#: `market` code. `PSX` is the Pakistan Stock Exchange here and Phillips 66's ticker in the
#: universe; see the module docstring. Anything added here must be a market, not a company.
MARKET_SCOPED = {"PSX": "PK"}

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

SCOPE_MARKET, SCOPE_OWN, SCOPE_UNRESOLVED = "market", "own", "unresolved"

_ONE_DAY = timedelta(days=1)


def _d(s: str) -> date:
    return date.fromisoformat(s[:10])


def _median(xs: list[float]) -> float | None:
    if not xs:
        return None
    xs = sorted(xs)
    n = len(xs)
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2


def resolve_scope(name: str | None, universe: set[str] | None = None) -> tuple[str, str | None]:
    """Where a context record applies: market-wide, one instrument, or nowhere we can establish.

    Returns `(scope, key)`:

      * `("market", None)`   -- every row
      * `("market", "PK")`   -- every row of that market code
      * `("own", "AAPL")`    -- that symbol's rows and no others
      * `("unresolved", name)` -- counted, and contributed to neither scope

    `universe` is the set of symbols the dataset actually holds. Without it a named record is
    taken at its word, which cannot mis-attribute (an unknown symbol simply matches no row) but
    also cannot be counted honestly; `assemble.py` passes the real set so that it can.
    """
    if not name:
        return SCOPE_UNRESOLVED, None
    if name == MARKET_WIDE:
        return SCOPE_MARKET, None
    if name in MARKET_SCOPED:
        return SCOPE_MARKET, MARKET_SCOPED[name]
    sym = ALIASES.get(name, name)
    if universe is not None and sym not in universe:
        return SCOPE_UNRESOLVED, name
    return SCOPE_OWN, sym


class ContextSource:
    """Every context artifact, indexed once, answering by date, instrument and market.

    Built with `load()`. Holding the indexes on an instance rather than in module globals is what
    lets a test construct one from fixtures, and lets a dataset build hold exactly one copy across
    a million rows.
    """

    def __init__(self, macro_dates, macro_rows, mkt_events, own_events,
                 mkt_press, own_press, unresolved, reactions, provenance,
                 events_loaded=True, press_loaded=True):
        self.macro_dates = macro_dates        # sorted list[date]
        self.macro_rows = macro_rows          # parallel list[dict]
        self.mkt_events = mkt_events          # market code or None -> sorted list[date]
        self.own_events = own_events          # symbol -> sorted list[date]
        self.mkt_press = mkt_press            # market code or None -> sorted list[date]
        self.own_press = own_press            # symbol -> sorted list[date]
        self.unresolved = unresolved          # sorted list[date] of records we could not place
        self.reactions = reactions            # symbol -> sorted list[(exitSession, returnPct)]
        self.provenance = provenance
        # Whether the corpus file was read at all. Not the same as whether it yielded a
        # record this row can use: a corpus whose every record was unplaceable has been
        # looked at, and 'we looked and found none' is a measurement.
        self.events_loaded = events_loaded
        self.press_loaded = press_loaded

    # -- loading ---------------------------------------------------------------------------

    @classmethod
    def load(cls, macro: Path = DEFAULT_MACRO, events: Path = EVENTS, press: Path = PRESS,
             reactions: Path = REACTIONS, universe: set[str] | None = None) -> "ContextSource":
        prov: dict = {"version": VERSION,
                      "loadedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                      "universeGiven": universe is not None,
                      "aliases": dict(ALIASES), "marketScoped": dict(MARKET_SCOPED)}

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

        mkt_ev: dict = defaultdict(list)
        own_ev: dict = defaultdict(list)
        unresolved: list[date] = []
        scopes = {SCOPE_MARKET: 0, SCOPE_OWN: 0, SCOPE_UNRESOLVED: 0}
        unplaced: dict[str, int] = defaultdict(int)
        if Path(events).exists():
            doc = json.loads(Path(events).read_text(encoding="utf-8"))
            for e in doc.get("events", []):
                if not e.get("verified"):
                    continue          # an unverified candidate is not evidence
                d = _d(e["date"])
                scope, key = resolve_scope(e.get("instrument"), universe)
                scopes[scope] += 1
                if scope == SCOPE_MARKET:
                    mkt_ev[key].append(d)
                elif scope == SCOPE_OWN:
                    own_ev[key].append(d)
                else:
                    unresolved.append(d)
                    unplaced[e.get("instrument") or "<none>"] += 1
        events_loaded = Path(events).exists()
        prov["events"] = {"path": str(events), "present": events_loaded,
                          "byScope": dict(scopes),
                          "rule": "verified events only, date strictly before as_of",
                          "neverRead": list(FORBIDDEN_KEYS)}

        mkt_pr: dict = defaultdict(list)
        own_pr: dict = defaultdict(list)
        pscopes = {SCOPE_MARKET: 0, SCOPE_OWN: 0, SCOPE_UNRESOLVED: 0}
        if Path(press).exists():
            seen: set[tuple] = set()
            for line in Path(press).read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                r = json.loads(line)
                pub = r.get("publishedAt")
                if not pub:
                    continue          # no publication time, no availability, no feature
                dedupe = (r.get("instrument"), r.get("dedupeKey") or r.get("url"), pub[:10])
                if dedupe in seen:
                    continue          # the same article under two routes is one article
                seen.add(dedupe)
                d = _d(pub)
                scope, key = resolve_scope(r.get("instrument"), universe)
                pscopes[scope] += 1
                if scope == SCOPE_MARKET:
                    mkt_pr[key].append(d)
                elif scope == SCOPE_OWN:
                    own_pr[key].append(d)
                else:
                    unresolved.append(d)
                    unplaced[r.get("instrument") or "<none>"] += 1
        press_loaded = Path(press).exists()
        prov["press"] = {"path": str(press), "present": press_loaded,
                         "byScope": dict(pscopes),
                         "rule": "publishedAt strictly before as_of; retrievedAt is never "
                                 "treated as availability"}
        prov["unresolvedInstruments"] = dict(sorted(unplaced.items(), key=lambda t: -t[1]))

        rx: dict = defaultdict(list)
        if Path(reactions).exists():
            with gzip.open(reactions, "rt", encoding="utf-8") as fh:
                for line in fh:
                    r = json.loads(line)
                    fwd = (r.get("forward") or {}).get(PRIOR_HORIZON) or {}
                    exit_session, ret = fwd.get("exitSession"), fwd.get("returnPct")
                    if not exit_session or ret is None:
                        continue      # an unclosed or unmeasured window is not a prior
                    scope, key = resolve_scope(r.get("symbol") or r.get("instrument"), universe)
                    # A reaction prior is a statement about one instrument. A market-scoped or
                    # unplaced record has no instrument to be a prior for, so it is dropped here
                    # rather than spread across a market.
                    if scope == SCOPE_OWN:
                        rx[key].append((_d(exit_session), float(ret)))
        prov["reactions"] = {"path": str(reactions), "present": bool(rx),
                             "instruments": len(rx), "rows": sum(len(v) for v in rx.values()),
                             "rule": f"forward['{PRIOR_HORIZON}'].exitSession strictly before "
                                     "as_of; an open window is not a prior; own-scope only"}
        prov["news"] = {"status": "excluded", "reason": NEWS_EXCLUSION}

        for bag in (mkt_ev, own_ev, mkt_pr, own_pr):
            for k in bag:
                bag[k].sort()
        for k in rx:
            rx[k].sort(key=lambda t: t[0])
        unresolved.sort()
        return cls(macro_dates, macro_rows, dict(mkt_ev), dict(own_ev),
                   dict(mkt_pr), dict(own_pr), unresolved, dict(rx), prov,
                   events_loaded=events_loaded, press_loaded=press_loaded)

    # -- helpers ---------------------------------------------------------------------------

    @staticmethod
    def _before(days: list[date], as_of: date) -> list[date]:
        """Every date strictly before `as_of`. The strictness is the point-in-time rule."""
        return days[:bisect_right(days, as_of - _ONE_DAY)] if days else []

    def _market_days(self, bag: dict, as_of: date, market: str | None) -> list[date]:
        """Market-wide records: the `MKT` bag always, plus this row's own market code."""
        out = list(self._before(bag.get(None, []), as_of))
        if market and market in bag:
            out += self._before(bag[market], as_of)
        return sorted(out)

    def _counts(self, days: list[date], as_of: date) -> tuple[float, float | None]:
        recent = float(sum(1 for d in days if (as_of - d).days <= WINDOW_DAYS))
        last = days[-1] if days else None
        return recent, (None if last is None else float((as_of - last).days))

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

    def events_at(self, as_of: date, instrument: str | None, market: str | None = None) -> dict:
        """Dated events before `as_of`, market-wide and own-instrument kept apart."""
        if not self.events_loaded:
            return {"status": "absent", "reason": "no event corpus loaded",
                    "f": {"ctx_mktEventsIn90d": None, "ctx_mktDaysSinceEvent": None,
                          "ctx_ownEventsIn90d": None, "ctx_ownDaysSinceEvent": None}}
        m_n, m_since = self._counts(self._market_days(self.mkt_events, as_of, market), as_of)
        own = self.own_events.get(instrument) if instrument else None
        if own is None:
            o_n, o_since = None, None     # no record for this instrument: unknown, not zero
        else:
            o_n, o_since = self._counts(self._before(own, as_of), as_of)
        return {"status": "observed",
                "f": {"ctx_mktEventsIn90d": m_n, "ctx_mktDaysSinceEvent": m_since,
                      "ctx_ownEventsIn90d": o_n, "ctx_ownDaysSinceEvent": o_since}}

    def press_at(self, as_of: date, instrument: str | None, market: str | None = None) -> dict:
        """Press and official-document records published before `as_of`, by scope."""
        if not self.press_loaded:
            return {"status": "absent", "reason": "no press corpus loaded",
                    "f": {"ctx_mktPressIn90d": None, "ctx_ownPressIn90d": None}}
        m_n, _ = self._counts(self._market_days(self.mkt_press, as_of, market), as_of)
        own = self.own_press.get(instrument) if instrument else None
        o_n = None if own is None else self._counts(self._before(own, as_of), as_of)[0]
        return {"status": "observed",
                "f": {"ctx_mktPressIn90d": m_n, "ctx_ownPressIn90d": o_n}}

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

    def quality_at(self, as_of: date) -> dict:
        """Records we could not place, counted rather than quietly spread over the market."""
        n = float(len(self._before(self.unresolved, as_of)))
        return {"status": "observed", "f": {"ctx_unresolvedScopeRecords": n}}

    def at(self, as_of: date | str, instrument: str | None = None,
           market: str | None = None) -> dict:
        """The whole context block for one asset-session. Never reads past `as_of`."""
        if isinstance(as_of, str):
            as_of = _d(as_of)
        return {
            "asOf": as_of.isoformat(),
            "instrument": instrument,
            "marketCode": market,
            "version": VERSION,
            "macro": self.macro_at(as_of),
            "events": self.events_at(as_of, instrument, market),
            "press": self.press_at(as_of, instrument, market),
            "reactionPrior": self.prior_at(as_of, instrument),
            "quality": self.quality_at(as_of),
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
        names += ["ctx_mktEventsIn90d", "ctx_mktDaysSinceEvent",
                  "ctx_ownEventsIn90d", "ctx_ownDaysSinceEvent",
                  "ctx_mktPressIn90d", "ctx_ownPressIn90d",
                  "ctx_maturedPriors", "ctx_priorMedianFwd20",
                  "ctx_unresolvedScopeRecords"]
        return names

    @staticmethod
    def vector(block: dict) -> list[float | None]:
        """`block` flattened into `feature_names()` order, **keeping None as None**.

        A missing value is handed on as missing. Turning it into 0.0 here would bury the one fact
        the consumer needs to decide anything.
        """
        flat: dict[str, float | None] = {}
        for part in ("macro", "events", "press", "reactionPrior", "quality", "news"):
            flat.update((block.get(part) or {}).get("f") or {})
        return [flat.get(n) for n in ContextSource.feature_names()]


# -- coverage ------------------------------------------------------------------------------

def coverage(src: ContextSource, sessions: list[date],
             instruments: list[tuple[str, str | None]]) -> dict:
    """How often each block actually answers, measured rather than assumed.

    `instruments` is `(symbol, market)` pairs, because market scope depends on the row's market.
    Reported per block and per feature so a thin layer cannot hide inside a healthy average.
    """
    seen = {k: 0 for k in ("macro", "events", "press", "reactionPrior")}
    nulls = {n: 0 for n in ContextSource.feature_names()}
    rows = 0
    for d in sessions:
        for sym, mkt in instruments:
            b = src.at(d, sym, mkt)
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
        "rowsMeasured": rows, "sessions": len(sessions), "instruments": len(instruments),
        "observedShareByBlock": {k: round(v / rows, 4) if rows else None for k, v in seen.items()},
        "nullShareByFeature": {k: round(v / rows, 4) if rows else None for k, v in nulls.items()},
        "featureOrder": ContextSource.feature_names(),
        "scopeRule": ("market | own | unresolved; an unplaceable record is counted in "
                      "ctx_unresolvedScopeRecords and contributes to neither scope"),
        "excluded": {"operational news feed": NEWS_EXCLUSION},
        "provenance": src.provenance,
    }


def universe_from(dataset: Path = DEFAULT_DATASET) -> dict[str, str | None]:
    """`symbol -> market` read from a built dataset, so scope resolution can be honest.

    Without it a name that belongs to nobody still resolves to own-scope and simply matches no
    row -- harmless, but it cannot then be *counted* as unplaced, and an uncounted gap is the
    kind this file exists to stop.
    """
    uni: dict[str, str | None] = {}
    # The NEWEST year, not the oldest. The universe is today's registered assets -- that is the
    # survivorship note's own definition -- and the early files hold far fewer names, so reading
    # 2018 would report most of the corpus as unplaceable and be wrong in the alarming direction.
    for f in sorted(Path(dataset).glob("examples-v3-*.jsonl.gz"), reverse=True):
        with gzip.open(f, "rt", encoding="utf-8") as fh:
            for line in fh:
                r = json.loads(line)
                uni.setdefault(r["symbol"], r.get("market"))
        if uni:
            break          # one year names the universe; reading nine would cost minutes
    return uni


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--as-of")
    ap.add_argument("--symbol")
    ap.add_argument("--market")
    ap.add_argument("--coverage", action="store_true")
    ap.add_argument("--out", default=str(OUT_DIR))
    a = ap.parse_args()

    uni = universe_from()
    src = ContextSource.load(universe=set(uni) or None)
    print(f"  universe   {len(uni)} symbols" if uni else "  universe   not found; "
          "unplaceable records cannot be counted")
    for k in ("macro", "events", "press", "reactions"):
        p = src.provenance[k]
        extra = p.get("byScope") or {"rows": p.get("rows")}
        print(f"  {k:<10} present={str(p['present']):<5} {extra}")
    print(f"  news       EXCLUDED -- {NEWS_EXCLUSION[:58]}...")

    if a.coverage:
        if not src.macro_dates:
            raise SystemExit("no macro artifact; rebuild it before measuring coverage")
        step = max(1, len(src.macro_dates) // 200)
        sessions = src.macro_dates[::step]
        named = sorted(set(list(src.own_events) + list(src.own_press) + list(src.reactions)))[:40]
        pairs = [(s, uni.get(s, "US")) for s in named] or [("MKT", "US")]
        rep = coverage(src, sessions, pairs)
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
        print(json.dumps(src.at(a.as_of, a.symbol, a.market), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
