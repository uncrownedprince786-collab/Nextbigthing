"""Fill the PSX daily history gap from the Karachi listing, and never across a change of basis.

    python tools/foundation/psx_backfill.py stored               one query: the PSX series as stored today
    python tools/foundation/psx_backfill.py fetch [--limit N]    Yahoo .KA -> staged bars, resumable
    python tools/foundation/psx_backfill.py plan                 validate, reconcile the basis, decide
    python tools/foundation/psx_backfill.py integrate --write    additive inserts, in bounded batches
    python tools/foundation/psx_backfill.py verify               re-read and prove nothing else moved

What this is for
----------------
`tools/foundation/psx_recovery.py` measured the hole: the exchange's own daily closing file holds
about twelve dates a year before 2024, and Yahoo's Karachi listing would serve 275,812 daily bars
this database does not have, across 203 of 226 stored symbols. Measuring it is not filling it.
This fills it.

The one thing that can quietly ruin it
--------------------------------------
The two providers do not quote the same number. The exchange file is raw: a 2-for-1 split appears
in it as a 50% fall, which is why `data/foundation/price_verification/unadjusted_actions.json`
holds 173 PSX candidates. Yahoo back-adjusts its OHLC for splits, so before a split its history is
the raw price divided by the factor. Inserting Yahoo's pre-split bars beside the exchange's
pre-split bars would build a series that steps between two bases -- a fabricated move, written by
the repair rather than inherited from the source, and indistinguishable afterwards from a real one.

So no bar is written on the strength of the provider alone. Every stored date that Yahoo also
serves is an anchor, and the ratio of the two closes there says whether the bases agree on that
date. A missing date is written only when the nearest stored anchor on each side agrees with Yahoo
to within `TOL`, and no split event falls between those anchors. Anything else is reported with its
exact symbol and date range and left in the ground. The before-first-anchor and after-last-anchor
edges are decided the same way, against the one anchor that exists.

What it will not do
-------------------
  * **It never updates a stored row.** The write is `ON CONFLICT DO NOTHING`, so a date this
    database already holds keeps the exchange's own number whatever Yahoo says about it. The
    repair can only add dates; it cannot restate one.
  * **It never invents a bar.** A bar missing an OHLC field is dropped, not filled from the close.
    A flat zero-volume bar -- Yahoo's filler for a session the exchange did not hold -- is dropped
    rather than stored as a day that did not move.
  * **It is resumable and idempotent.** Each symbol's fetch is staged to its own file and skipped
    when it is already there; each integrate appends the keys it wrote to a ledger, and running it
    twice writes nothing the second time.
  * **It carries its own provenance.** The rows go in under `SOURCE`, which no other lane writes,
    so they can be counted, audited and -- if the owner ever wants them gone -- deleted again
    without touching a single bar the exchange supplied.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.parse
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "jobs"))

STAGE = ROOT / ".cache" / "psx_backfill"
STAGED = STAGE / "staged"
OUT = ROOT / "data" / "foundation" / "psx_backfill"

# The label these rows carry in PriceSnapshot.source. Distinct from "Pakistan Stock Exchange daily
# closing file" on purpose: provenance per row, and a single predicate that selects every row this
# tool ever wrote.
SOURCE = "Yahoo Finance Karachi listing"

BROWSER = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
           "Chrome/120.0 Safari/537.36")
FROM = date(2019, 1, 1)
# How far two providers' closes may differ on the same date and still be called the same basis.
# A split factor is 1.5 or more; a rounding difference is well under a tenth of a percent.
TOL = 0.005
BATCH = 500


def arg(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def load(path: Path, default=None):
    return json.loads(path.read_text("utf-8")) if path.exists() else default


def dump(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=1, default=str), encoding="utf-8")


# ------------------------------------------------------------------ stored


def cmd_stored() -> None:
    """One read of the database, kept on disk so the fetch and the plan need no connection."""
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    from nbt import db, rows
    conn = db()
    cur = conn.cursor()
    try:
        got = rows(cur, 'SELECT a.id, a.symbol, p.date::text AS d, p.close '
                        'FROM "PriceSnapshot" p JOIN "Asset" a ON a.id = p."assetId" '
                        'WHERE p.source LIKE %s ORDER BY a.symbol, p.date', ("Pakistan%",))
    finally:
        cur.close()
        conn.close()
    by: dict[str, dict] = {}
    for r in got:
        s = by.setdefault(r["symbol"], {"assetId": r["id"], "bars": {}})
        s["bars"][r["d"]] = float(r["close"])
    dump(STAGE / "stored.json", {"takenAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                 "symbols": len(by), "bars": len(got), "series": by})
    print(f"stored: {len(by)} PSX symbols, {len(got)} bars")


# ------------------------------------------------------------------ fetch


class NotServed(LookupError):
    """The provider answered, and does not list this symbol in Karachi."""


def status(url: str) -> int | None:
    """The HTTP status of one direct request, or None when the request itself failed."""
    import urllib.error
    import urllib.request
    try:
        with urllib.request.urlopen(
                urllib.request.Request(url, headers={"User-Agent": BROWSER}), timeout=30) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:  # noqa: BLE001
        return None


def chart(symbol: str) -> dict:
    """Yahoo's Karachi listing for `symbol`.

    Raises `NotServed` when the provider answered and has nothing, and `ConnectionError` when it
    did not answer at all. They are not the same fact and must not land in the same bucket: a run
    that calls a network failure an absent listing writes a symbol off for good on the strength of
    one bad minute. The first pass over these 226 symbols did exactly that to eighteen of them.
    """
    from nbt import get_json
    p1 = int(datetime(FROM.year, FROM.month, FROM.day, tzinfo=timezone.utc).timestamp())
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}.KA"
           f"?period1={p1}&period2={int(time.time())}&interval=1d&events=split%7Cdiv"
           f"&includeAdjustedClose=true")
    j = get_json(url, ttl=7 * 24 * 3600, headers={"User-Agent": BROWSER}, timeout=40,
                 cache_key=f"psx-backfill:{symbol}")
    if j is None:
        # `nbt.get` returns None for a 404 and for a dropped connection alike, and here those are
        # opposite answers: one says the listing does not exist, the other says the question was
        # never asked. One direct request settles which, and only that.
        raise (NotServed(f"{symbol}: HTTP 404 from the provider") if status(url) == 404
               else ConnectionError(f"{symbol}: the provider did not answer"))
    res = (j or {}).get("chart", {}).get("result")
    if not res:
        raise NotServed(symbol)
    r = res[0]
    meta = r.get("meta") or {}
    if meta.get("currency") != "PKR":
        raise NotServed(f"{symbol}: quoted in {meta.get('currency')!r}, not PKR")
    # The exchange's own day, not the runner's: a daily timestamp is the session's opening instant,
    # and reading it in UTC would move a session across midnight for any exchange east of it.
    off = int(meta.get("gmtoffset") or 0)
    quotes = (r.get("indicators") or {}).get("quote") or [{}]
    q = quotes[0]

    def at(key, i):
        seq = q.get(key) or []
        return seq[i] if i < len(seq) else None

    bars = []
    for i, t in enumerate(r.get("timestamp") or []):
        bars.append({"d": datetime.fromtimestamp(t + off, timezone.utc).date().isoformat(),
                     "o": at("open", i), "h": at("high", i), "l": at("low", i),
                     "c": at("close", i), "v": at("volume", i)})
    events = r.get("events") or {}
    splits = [{"date": datetime.fromtimestamp(int(s["date"]) + off, timezone.utc).date().isoformat(),
               "ratio": s.get("splitRatio"), "numerator": s.get("numerator"),
               "denominator": s.get("denominator")}
              for s in (events.get("splits") or {}).values()]
    return {"symbol": symbol, "instrumentType": meta.get("instrumentType"),
            "exchange": meta.get("exchangeName"), "currency": meta.get("currency"),
            "fetchedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "bars": bars, "splits": sorted(splits, key=lambda s: s["date"]),
            "dividends": len(events.get("dividends") or {})}


def cmd_fetch() -> None:
    stored = load(STAGE / "stored.json")
    if not stored:
        print("run `stored` first")
        raise SystemExit(2)
    STAGED.mkdir(parents=True, exist_ok=True)
    limit = int(arg("--limit") or 0) or None
    symbols = sorted(stored["series"])[:limit] if limit else sorted(stored["series"])
    state = load(STAGE / "fetch_state.json", {"served": [], "notServed": [], "failed": []})
    done = {p.stem for p in STAGED.glob("*.json")}
    todo = [s for s in symbols if s not in done and s not in state["notServed"]]
    print(f"fetch: {len(symbols)} symbols, {len(done)} already staged, {len(todo)} to go", flush=True)
    for i, sym in enumerate(todo, 1):
        try:
            got = chart(sym)
        except NotServed as e:
            got = None
            if sym not in state["notServed"]:
                state["notServed"].append(sym)
            if sym in state["failed"]:
                state["failed"].remove(sym)
            print(f"  {sym}: not served -- {e}", flush=True)
        except Exception as e:  # noqa: BLE001
            got = None
            if sym not in state["failed"]:
                state["failed"].append(sym)
            print(f"  {sym}: {type(e).__name__} {e}", flush=True)
        if got is not None:
            dump(STAGED / f"{sym}.json", got)
            if sym not in state["served"]:
                state["served"].append(sym)
            if sym in state["failed"]:
                state["failed"].remove(sym)
            if sym in state["notServed"]:
                state["notServed"].remove(sym)
        if i % 20 == 0 or i == len(todo):
            dump(STAGE / "fetch_state.json", state)
            print(f"  {i}/{len(todo)} fetched, {len(state['served'])} served, "
                  f"{len(state['notServed'])} not served", flush=True)
    dump(STAGE / "fetch_state.json", state)
    print(f"fetch done: {len(state['served'])} served, {len(state['notServed'])} not served, "
          f"{len(state['failed'])} failed")


# ------------------------------------------------------------------ validate and plan


def validate(bars: list[dict]) -> tuple[list[dict], dict]:
    """The bars a provider actually served, and a count of every one it did not."""
    why: dict[str, int] = defaultdict(int)
    seen: set[str] = set()
    out = []
    today = date.today().isoformat()
    for b in bars:
        o, h, l, c, v = b["o"], b["h"], b["l"], b["c"], b["v"]
        if c is None or o is None or h is None or l is None or v is None:
            why["incompleteBar"] += 1
            continue
        o, h, l, c, v = float(o), float(h), float(l), float(c), float(v)
        if min(o, h, l, c) <= 0:
            why["nonPositivePrice"] += 1
            continue
        if v < 0:
            why["negativeVolume"] += 1
            continue
        if h < l or h < max(o, c) - 1e-9 or l > min(o, c) + 1e-9:
            why["ohlcOutOfOrder"] += 1
            continue
        if not (FROM.isoformat() <= b["d"] <= today):
            why["dateOutOfRange"] += 1
            continue
        if b["d"] in seen:
            why["duplicateDate"] += 1
            continue
        if o == h == l == c and v == 0:
            # Yahoo serves one of these for a day the exchange did not hold. Stored, it would read
            # as a session that opened, traded nothing and closed unchanged.
            why["flatZeroVolumeFiller"] += 1
            continue
        seen.add(b["d"])
        out.append({"d": b["d"], "o": o, "h": h, "l": l, "c": c, "v": v})
    return out, dict(why)


def reconcile(staged: list[dict], stored: dict[str, float], splits: list[dict]) -> dict:
    """Which of the provider's dates may be written, decided anchor by anchor."""
    served = {b["d"] for b in staged}
    anchors = sorted(d for d in stored if d in served)
    yq = {b["d"]: b for b in staged}
    agree: dict[str, bool] = {}
    ratios = []
    for d in anchors:
        y = yq[d]["c"]
        r = (stored[d] / y) if y else 0.0
        ratios.append(r)
        agree[d] = abs(r - 1.0) <= TOL
    split_dates = sorted(s["date"] for s in splits)

    def split_between(lo: str, hi: str) -> bool:
        return any(lo < s <= hi for s in split_dates)

    ok: list[dict] = []
    held: dict[str, list[str]] = defaultdict(list)
    for b in staged:
        d = b["d"]
        if d in stored:
            continue  # the exchange's own number stands; this tool never restates one
        prev = next((a for a in reversed(anchors) if a < d), None)
        nxt = next((a for a in anchors if a > d), None)
        if prev is None and nxt is None:
            held["noAnchorAnywhere"].append(d)
            continue
        sides = [a for a in (prev, nxt) if a is not None]
        if not all(agree[a] for a in sides):
            held["basisDivergedAtAnchor"].append(d)
            continue
        lo, hi = (prev or d), (nxt or d)
        if split_between(min(lo, d), max(hi, d)):
            held["splitBetweenAnchors"].append(d)
            continue
        ok.append(b)
    return {"anchors": len(anchors), "anchorsAgreeing": sum(agree.values()),
            "medianRatio": sorted(ratios)[len(ratios) // 2] if ratios else None,
            "writable": ok, "held": dict(held)}


def cmd_plan() -> None:
    stored_all = load(STAGE / "stored.json")
    files = sorted(STAGED.glob("*.json"))
    plan: dict[str, dict] = {}
    totals: dict[str, int] = defaultdict(int)
    drops: dict[str, int] = defaultdict(int)
    held_total: dict[str, int] = defaultdict(int)
    for p in files:
        g = load(p)
        sym = g["symbol"]
        s = stored_all["series"].get(sym) or {"assetId": None, "bars": {}}
        good, why = validate(g["bars"])
        for k, n in why.items():
            drops[k] += n
        rec = reconcile(good, s["bars"], g["splits"])
        totals["symbols"] += 1
        totals["providerBars"] += len(g["bars"])
        totals["validBars"] += len(good)
        totals["storedBars"] += len(s["bars"])
        totals["writable"] += len(rec["writable"])
        for k, v in rec["held"].items():
            held_total[k] += len(v)
        plan[sym] = {"assetId": s["assetId"], "anchors": rec["anchors"],
                     "anchorsAgreeing": rec["anchorsAgreeing"], "medianRatio": rec["medianRatio"],
                     "splits": g["splits"], "validBars": len(good), "storedBars": len(s["bars"]),
                     "writable": rec["writable"],
                     "held": {k: {"n": len(v), "from": min(v), "to": max(v)}
                              for k, v in rec["held"].items()}}
    dump(STAGE / "plan_full.json", plan)
    by_year: dict[str, int] = defaultdict(int)
    for sym, v in plan.items():
        for b in v["writable"]:
            by_year[b["d"][:4]] += 1
    summary = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "symbolsStaged": totals["symbols"],
        "providerBars": totals["providerBars"],
        "validBars": totals["validBars"],
        "droppedByValidation": dict(drops),
        "storedBarsAtPlanTime": totals["storedBars"],
        "writableBars": totals["writable"],
        "writableByYear": dict(sorted(by_year.items())),
        "heldBack": dict(held_total),
        "symbolsFullyHeld": sorted(s for s, v in plan.items() if not v["writable"]),
        "rule": (f"a date is writable only when the nearest stored anchor on each side quotes the "
                 f"same basis to within {TOL:.1%} and no split falls between them"),
    }
    dump(OUT / "plan.json", summary)
    print(json.dumps({k: v for k, v in summary.items() if k != "symbolsFullyHeld"}, indent=1))
    print(f"fully held symbols: {len(summary['symbolsFullyHeld'])}")


# ------------------------------------------------------------------ integrate


def cmd_integrate() -> None:
    write = "--write" in sys.argv
    plan = load(STAGE / "plan_full.json")
    if not plan:
        print("run `plan` first")
        raise SystemExit(2)
    ledger = STAGE / "integrated.jsonl"
    already = set()
    if ledger.exists():
        for line in ledger.read_text("utf-8").splitlines():
            if line.strip():
                already.add(json.loads(line)["symbol"])
    todo = [(s, v) for s, v in sorted(plan.items()) if v["writable"] and s not in already]
    total = sum(len(v["writable"]) for _, v in todo)
    print(f"integrate: {len(todo)} symbols, {total} bars"
          + ("" if write else "  (dry run -- pass --write)"), flush=True)
    if not write:
        return
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    from nbt import db
    conn = db()
    cur = conn.cursor()
    inserted = 0
    try:
        for i, (sym, v) in enumerate(todo, 1):
            rows_in = 0
            bars = v["writable"]
            for k in range(0, len(bars), BATCH):
                chunk = bars[k:k + BATCH]
                cur.executemany(
                    'INSERT INTO "PriceSnapshot" ("assetId", date, open, high, low, close, volume, source)'
                    ' VALUES (%s, %s, %s, %s, %s, %s, %s, %s)'
                    ' ON CONFLICT ("assetId", date) DO NOTHING',
                    [(v["assetId"], b["d"], b["o"], b["h"], b["l"], b["c"], b["v"], SOURCE)
                     for b in chunk])
                rows_in += cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
            conn.commit()
            inserted += rows_in
            with ledger.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({"symbol": sym, "assetId": v["assetId"], "offered": len(bars),
                                     "inserted": rows_in, "from": bars[0]["d"], "to": bars[-1]["d"],
                                     "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}) + "\n")
            if i % 20 == 0 or i == len(todo):
                print(f"  {i}/{len(todo)} symbols, {inserted} rows inserted", flush=True)
    finally:
        cur.close()
        conn.close()
    print(f"integrate done: {inserted} rows inserted under source {SOURCE!r}")


# ------------------------------------------------------------------ verify


def cmd_verify() -> None:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    from nbt import db, rows
    before = load(STAGE / "stored.json")
    conn = db()
    cur = conn.cursor()
    try:
        counts = rows(cur, 'SELECT source, count(*) n, min(date)::text lo, max(date)::text hi '
                           'FROM "PriceSnapshot" GROUP BY 1 ORDER BY 2 DESC')
        psx_now = rows(cur, 'SELECT a.symbol, p.date::text d, p.close '
                            'FROM "PriceSnapshot" p JOIN "Asset" a ON a.id = p."assetId" '
                            'WHERE p.source LIKE %s', ("Pakistan%",))
        by_year = rows(cur, 'SELECT extract(year from p.date)::int y, p.source, count(*) n '
                            'FROM "PriceSnapshot" p JOIN "Asset" a ON a.id = p."assetId" '
                            'WHERE a.symbol = ANY(%s) GROUP BY 1, 2 ORDER BY 1, 2',
                       (sorted(before["series"]),))
        size = rows(cur, "SELECT pg_size_pretty(pg_database_size(current_database())) s")[0]["s"]
    finally:
        cur.close()
        conn.close()
    now: dict[str, dict[str, float]] = defaultdict(dict)
    for r in psx_now:
        now[r["symbol"]][r["d"]] = float(r["close"])
    lost, changed = [], []
    for sym, s in before["series"].items():
        for d, c in s["bars"].items():
            if d not in now.get(sym, {}):
                lost.append(f"{sym} {d}")
            elif abs(now[sym][d] - c) > 1e-9:
                changed.append(f"{sym} {d}")
    report = {"verifiedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "sourceCounts": counts, "databaseSize": size,
              "exchangeBarsBefore": before["bars"], "exchangeBarsNow": len(psx_now),
              "exchangeBarsLost": len(lost), "exchangeClosesChanged": len(changed),
              "examplesLost": lost[:5], "examplesChanged": changed[:5]}
    print(json.dumps(report, indent=1, default=str))
    dump(OUT / "integration_verified.json", {**report, "psxSymbolBarsByYearAndSource": by_year})
    if lost or changed:
        print("FAILED: the repair altered rows it was not allowed to touch")
        raise SystemExit(1)
    print("integrity check passed: every pre-existing exchange bar is present and unchanged")


def cmd_actions() -> None:
    """What the provider's own split calendar says about each PSX candidate the scan found.

    `split_check.py` infers an unadjusted action from the shape of a one-day move: a ratio close to
    a simple fraction, no reversal, far outside the asset's usual range. That is an inference. The
    Karachi listing fetched for the backfill carries Yahoo's split events for the same symbols --
    the date and the factor, as the provider records them -- so the inference can be put next to a
    source. A candidate with a split on its date is an established action with a known factor; one
    without is a candidate still, and is reported as one rather than quietly promoted.
    """
    doc = json.loads((ROOT / "data" / "foundation" / "price_verification" /
                      "unadjusted_actions.json").read_text(encoding="utf-8"))
    staged = {p.stem: load(p) for p in STAGED.glob("*.json")}
    out = []
    for c in doc.get("candidatesList", []):
        if not c["source"].startswith("Pakistan"):
            continue
        g = staged.get(c["symbol"])
        row = {"symbol": c["symbol"], "date": c["date"], "observedRatio": c["ratio"],
               "nearestSimpleFactor": c["nearestFactor"], "providerListed": g is not None}
        best = None
        for s in (g or {}).get("splits", []):
            gap = abs((date.fromisoformat(s["date"]) - date.fromisoformat(c["date"])).days)
            if gap <= 5 and (best is None or gap < best[0]):
                best = (gap, s)
        if best:
            gap, s = best
            num, den = float(s["numerator"] or 0), float(s["denominator"] or 0)
            # A split quoted num:den multiplies the price by den/num -- a 5:1 takes it to a fifth.
            # The scan's `ratio` is that same price multiple as the stored series actually moved,
            # so the two are compared directly; comparing their product against 1 asks whether one
            # is the other's inverse, which is a different and wrong question.
            expect = (den / num) if num else None
            row |= {"providerSplit": {"date": s["date"], "ratio": s["ratio"], "dayGap": gap},
                    "providerPriceFactor": expect,
                    "agreesWithObserved": bool(expect and abs(c["ratio"] / expect - 1.0) <= 0.05)}
        out.append(row)
    confirmed = [r for r in out if r.get("agreesWithObserved")]
    listed_no_split = [r for r in out if r["providerListed"] and "providerSplit" not in r]
    report = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "psxCandidates": len(out),
        "symbolsTheProviderLists": sum(r["providerListed"] for r in out),
        "confirmedByAProviderSplit": len(confirmed),
        "providerListsTheSymbolButNoSplitOnThatDate": len(listed_no_split),
        "providerDoesNotListTheSymbol": sum(not r["providerListed"] for r in out),
        "disagreedOnFactor": sum(1 for r in out if "providerSplit" in r
                                 and not r.get("agreesWithObserved")),
        "rule": ("a provider split within five days of the candidate date whose price factor "
                 "reproduces the observed one-day ratio to within 5%"),
        "candidates": out,
    }
    dump(ROOT / "data" / "foundation" / "price_verification" / "psx_action_factors.json", report)
    print(json.dumps({k: v for k, v in report.items() if k != "candidates"}, indent=1))


def cmd_seams() -> None:
    """Measure the joins between the two providers' bars, where a basis error would show.

    `recovery-manifest.json`, under `psx-pre-2024-monthly-grid`, requires that the two series are
    never mixed for one asset, because appending an adjusted history to a raw one "would create a
    price jump that never happened". The anchor rule is an argument that no such jump can occur
    here: a gap is filled only between two stored dates where both providers quote the same number,
    and an action inside that gap would have made the earlier one disagree.

    An argument is not a measurement. This finds every seam -- a consecutive pair of stored bars
    whose `source` differs -- and reports the one-day return across it against the asset's own
    typical move, which is how `split_check.py` recognises a fabricated step in the first place.
    """
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    from nbt import db, rows
    conn = db()
    cur = conn.cursor()
    try:
        got = rows(cur, 'SELECT a.symbol, p.date::text d, p.close, p.source '
                        'FROM "PriceSnapshot" p JOIN "Asset" a ON a.id = p."assetId" '
                        'WHERE a.currency = %s AND p.close IS NOT NULL '
                        'ORDER BY a.symbol, p.date', ("PKR",))
    finally:
        cur.close()
        conn.close()
    series: dict[str, list[dict]] = defaultdict(list)
    for r in got:
        series[r["symbol"]].append(r)
    seams, worst, moves_all = 0, [], []
    for sym, bars in series.items():
        rets = [abs(float(b["close"]) / float(a["close"]) - 1.0)
                for a, b in zip(bars, bars[1:]) if float(a["close"]) > 0]
        typical = sorted(rets)[len(rets) // 2] if rets else 0.0
        for a, b in zip(bars, bars[1:]):
            if a["source"] == b["source"] or not float(a["close"]):
                continue
            seams += 1
            move = float(b["close"]) / float(a["close"]) - 1.0
            moves_all.append(abs(move))
            worst.append({"symbol": sym, "from": a["d"], "at": b["d"],
                          "movePct": round(move * 100, 2),
                          "timesTypicalMove": round(abs(move) / typical, 1) if typical else None,
                          "fromSource": a["source"], "toSource": b["source"]})
    # The size of a seam's move does not decide anything on its own. These are sub-rupee stocks:
    # JATM, HIRAT and PASL each make six to twelve one-day moves beyond 30% *within a single
    # source*, so a 30% threshold flags the market's own behaviour and calls it a basis error. What
    # a basis error actually looks like is the two providers disagreeing about the same date, and
    # that can be measured instead of inferred.
    # Validated bars, not raw ones: a bar rejected as the provider's synthetic filler cannot then
    # be quoted as the provider's opinion of that date. Comparing against the raw array called 341
    # seams a disagreement, and every one of them was a flat zero-volume pad this tool had already
    # thrown away.
    staged = {p.stem: {b["d"]: b for b in validate(load(p)["bars"])[0]}
              for p in STAGED.glob("*.json")}
    worst.sort(key=lambda x: -abs(x["movePct"]))
    unverifiable, disagreed = [], []
    for w in worst:
        exch = w["at"] if w["toSource"].startswith("Pakistan") else w["from"]
        y = staged.get(w["symbol"], {}).get(exch)
        stored_close = next((float(r["close"]) for r in series[w["symbol"]] if r["d"] == exch), None)
        if y is None or stored_close is None:
            w["providersAgreeOnTheSeamDate"] = None
            unverifiable.append(w)
            continue
        ratio = stored_close / float(y["c"])
        w["providersAgreeOnTheSeamDate"] = abs(ratio - 1.0) <= TOL
        w["seamDateRatio"] = round(ratio, 5)
        if not w["providersAgreeOnTheSeamDate"]:
            disagreed.append(w)

    moves_all.sort()
    report = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "seams": seams,
        "medianAbsMovePct": round(moves_all[len(moves_all) // 2] * 100, 3) if moves_all else None,
        "p99AbsMovePct": round(moves_all[int(len(moves_all) * 0.99)] * 100, 3) if moves_all else None,
        "seamsMovingOver30Pct": sum(1 for w in worst if abs(w["movePct"]) > 30),
        "seamsWhereTheProvidersDisagreeOnTheDate": len(disagreed),
        "seamsTheProviderCannotConfirm": len(unverifiable),
        "test": ("a seam fails when the two providers quote different closes for the exchange bar "
                 "it joins to, not when the market moved a long way that day"),
        "worstTen": worst[:10],
        "disagreements": disagreed[:20],
    }
    dump(OUT / "seams.json", report)
    print(json.dumps({k: v for k, v in report.items()
                      if k not in ("worstTen", "disagreements")}, indent=1))
    for w in worst[:5]:
        agree = w.get("providersAgreeOnTheSeamDate")
        print(f"  {w['symbol']:8} {w['at']}  {w['movePct']:+8.2f}%  providers agree on the date: "
              f"{'yes' if agree else ('not served' if agree is None else 'NO')}")
    if disagreed:
        print(f"FAILED: {len(disagreed)} seams join to a bar the two providers price differently")
        raise SystemExit(1)
    print("every seam joins to a bar both providers price the same: no fabricated step was created")


COMMANDS = {"stored": cmd_stored, "fetch": cmd_fetch, "plan": cmd_plan,
            "integrate": cmd_integrate, "verify": cmd_verify, "actions": cmd_actions,
            "seams": cmd_seams}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        raise SystemExit(2)
    COMMANDS[sys.argv[1]]()
