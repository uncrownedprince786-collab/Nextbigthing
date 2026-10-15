"""Acquire the frozen target's missing series, and stage them where they can be checked.

    python tools/foundation/acquire.py benchmarks     S&P 500, VIX and the ICE dollar index
    python tools/foundation/acquire.py btc            Bitcoin daily before the stored history
    python tools/foundation/acquire.py psx-archive    the exchange's own files for the Yahoo-404 names
    python tools/foundation/acquire.py withheld       the basis-conflicting PSX bars, marked as such
    python tools/foundation/acquire.py observations   KSE-100, the SBP policy rate and KIBOR, as of today
    python tools/foundation/acquire.py manifest       one disposition per series, written to data/

Staged, not integrated
----------------------
Nothing here writes to `PriceSnapshot`. Three of these series are index levels with no `Asset`
row, one is a deliberately basis-conflicting set that must not sit beside the exchange's own
numbers, and the storage budget is 126 MB. Staging keeps the acquisition verifiable and leaves
the integration decision where it belongs, which is after the cleaning milestone.

What "valid" means here, and the one rule that does not transfer
---------------------------------------------------------------
`psx_backfill.validate` rejects a bar whose open, high, low and close are equal with zero volume,
because that is how Yahoo pads a session the Karachi exchange did not hold. **That rule must not
be applied to an index.** `^VIX` publishes zero volume on every single session -- it is a
calculated level, not something traded -- so the padding rule would reject the entire series. The
checks that do transfer are: a close must exist and be positive, the high must not be below the
low, and no date may repeat.
"""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "jobs"))

STAGE = ROOT / ".cache" / "acquire"
OUT = ROOT / "data" / "foundation" / "acquisition"
BROWSER = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
           "Chrome/120.0 Safari/537.36")

# The frozen benchmark series this task is allowed to acquire, and what each one actually is.
# The distinction is the point: a price index is not a total-return index, a continuous future is
# not spot, and the broad dollar index is not DXY.
BENCHMARKS = {
    "^GSPC": {"name": "S&P 500 index", "basis": "price index (not total return)",
              "source": "Yahoo Finance chart API", "exchange": "SNP"},
    "^SP500TR": {"name": "S&P 500 total return index",
                 "basis": "total return (dividends reinvested) -- a different series from ^GSPC, "
                          "kept separate and never substituted for it",
                 "source": "Yahoo Finance chart API", "exchange": "SNP"},
    "^VIX": {"name": "CBOE volatility index", "basis": "calculated index level, volume always 0",
             "source": "Yahoo Finance chart API", "exchange": "CXI"},
    "DX-Y.NYB": {"name": "ICE US Dollar Index (DXY)",
                 "basis": "price index against six currencies; NOT the Federal Reserve's broad "
                          "trade-weighted index (DTWEXBGS), which is held separately",
                 "source": "Yahoo Finance chart API", "exchange": "NYB"},
    "GC=F": {"name": "Gold continuous future", "basis": "continuous front-month future, not spot",
             "source": "Yahoo Finance chart API", "exchange": "CMX"},
    "BZ=F": {"name": "Brent crude continuous future",
             "basis": "continuous front-month future, not spot",
             "source": "Yahoo Finance chart API", "exchange": "NYM"},
}
# The provider's own floor, not the project's: ask from before any of these series began and let
# the first bar returned be the evidence of where the history actually starts.
FROM = date(1900, 1, 1)


def arg(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def dump(path: Path, obj) -> None:
    """Write through a temporary file and rename over the target.

    The ledger is what makes this resumable, and `write_text` truncates before it writes: a crash
    or a kill in that window leaves an empty file and the run restarts from nothing. A rename on
    the same filesystem is atomic, so the old ledger survives until the new one is complete.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=1, default=str), encoding="utf-8")
    tmp.replace(path)


def load(path: Path, default=None):
    return json.loads(path.read_text("utf-8")) if path.exists() else default


def browser_get(url: str) -> tuple[int | str, bytes]:
    """One direct request with a browser agent. Returns (status, body); never raises."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": BROWSER, "Accept": "*/*"})
        with urllib.request.urlopen(req, timeout=40) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, b""
    except Exception as e:  # noqa: BLE001
        return type(e).__name__, b""


def validate_index(bars: list[dict]) -> tuple[list[dict], dict]:
    """Index-level validation: the padding rule in psx_backfill does not apply here (see module doc)."""
    why: dict[str, int] = defaultdict(int)
    seen: set[str] = set()
    out = []
    today = date.today().isoformat()
    for b in bars:
        c = b["c"]
        if c is None:
            why["noClose"] += 1
            continue
        c = float(c)
        if c <= 0:
            why["nonPositiveClose"] += 1
            continue
        o, h, l = b["o"], b["h"], b["l"]
        if None not in (o, h, l):
            o, h, l = float(o), float(h), float(l)
            if h < l or h < max(o, c) - 1e-6 or l > min(o, c) + 1e-6:
                # Not corruption, and not a reason to lose the day. On thin early futures
                # sessions Yahoo reports open=high=low as an indicative snapshot while the close
                # is the exchange's settlement, so the close sits outside its own range: GC=F
                # 2003-04-29 prints 333/333/333 against a 333.70 settlement. The close is a real
                # price and the range is not, so the close is kept and the impossible range is
                # dropped rather than stored or used to throw the observation away.
                why["ohlcInconsistentWithCloseKeptCloseOnly"] += 1
                o = h = l = None
        else:
            why["closeOnlyBarKept"] += 1
        if not (FROM.isoformat() <= b["d"] <= today):
            why["dateOutOfRange"] += 1
            continue
        if b["d"] in seen:
            why["duplicateDate"] += 1
            continue
        seen.add(b["d"])
        out.append({"d": b["d"], "o": o, "h": h, "l": l, "c": c, "v": b.get("v")})
    return out, dict(why)


# ------------------------------------------------------------------ benchmarks


def cmd_benchmarks() -> None:
    from nbt import get_json
    report = {}
    for sym, meta in BENCHMARKS.items():
        # Computed rather than taken from datetime.timestamp(): a pre-1970 instant is a negative
        # epoch and Windows raises on it, which would have silently capped every series at 1970.
        p1 = (FROM - date(1970, 1, 1)).days * 86400
        url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(sym)}"
               f"?period1={p1}&period2={int(time.time())}&interval=1d")
        # The range belongs in the cache key. Without it, widening `FROM` returns the narrower
        # payload a previous run cached and the series looks as though the provider starts there.
        j = get_json(url, ttl=24 * 3600, headers={"User-Agent": BROWSER}, timeout=40,
                     cache_key=f"acquire:{sym}:{FROM.isoformat()}")
        res = (j or {}).get("chart", {}).get("result")
        if not res:
            report[sym] = {**meta, "acquired": False, "reason": "the provider returned no result"}
            print(f"  {sym:10} NOT ACQUIRED")
            continue
        r = res[0]
        m = r.get("meta") or {}
        off = int(m.get("gmtoffset") or 0)
        q = ((r.get("indicators") or {}).get("quote") or [{}])[0]

        def at(key, i):
            seq = q.get(key) or []
            return seq[i] if i < len(seq) else None

        # Arithmetic, not fromtimestamp: ^GSPC reaches back to 1927 and a pre-1970 epoch is
        # negative, which raises OSError on Windows rather than returning the date.
        epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
        bars = [{"d": (epoch + timedelta(seconds=t + off)).date().isoformat(),
                 "o": at("open", i), "h": at("high", i), "l": at("low", i),
                 "c": at("close", i), "v": at("volume", i)}
                for i, t in enumerate(r.get("timestamp") or [])]
        good, why = validate_index(bars)
        dump(STAGE / "benchmarks" / f"{sym.replace('^', '').replace('=', '_')}.json",
             {"symbol": sym, **meta, "currency": m.get("currency"),
              "instrumentType": m.get("instrumentType"),
              "fetchedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "bars": good})
        report[sym] = {**meta, "acquired": True, "currency": m.get("currency"),
                       "instrumentType": m.get("instrumentType"),
                       "served": len(bars), "valid": len(good), "rejected": why,
                       "first": good[0]["d"] if good else None,
                       "last": good[-1]["d"] if good else None}
        print(f"  {sym:10} {len(good):5} valid of {len(bars):5} served   {good[0]['d']} .. {good[-1]['d']}")
    dump(STAGE / "benchmarks" / "_report.json", report)


# ------------------------------------------------------------------ bitcoin


def cmd_btc() -> None:
    """Daily BTC-USD from Coinbase before the earliest stored bar, in 300-candle pages."""
    from nbt import get_json
    earliest_stored = date(2018, 11, 4)          # measured in the inventory, source Coinbase
    got: dict[str, dict] = {}
    end = earliest_stored
    pages = 0
    while pages < 12:
        start = end - timedelta(days=295)
        url = ("https://api.exchange.coinbase.com/products/BTC-USD/candles"
               f"?granularity=86400&start={start.isoformat()}&end={end.isoformat()}")
        j = get_json(url, ttl=7 * 24 * 3600, timeout=40, cache_key=f"acquire:btc:{end}")
        pages += 1
        if not j:
            print(f"  page {pages}: no answer for {start} .. {end}")
            break
        # [ time, low, high, open, close, volume ]
        for row in j:
            d = datetime.fromtimestamp(row[0], timezone.utc).date()
            if d >= earliest_stored:
                continue
            got[d.isoformat()] = {"d": d.isoformat(), "o": row[3], "h": row[2], "l": row[1],
                                  "c": row[4], "v": row[5]}
        print(f"  page {pages}: {start} .. {end} -> {len(j)} candles, {len(got)} kept so far",
              flush=True)
        if not j:
            break
        end = start
        if end < date(2014, 1, 1):
            break
    bars = [got[k] for k in sorted(got)]
    dump(STAGE / "btc_pre_2018.json",
         {"product": "BTC-USD", "source": "Coinbase Exchange API",
          "basis": "exchange traded spot pair, raw", "earliestStoredBar": earliest_stored.isoformat(),
          "fetchedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"), "bars": bars})
    print(f"btc: {len(bars)} daily bars before {earliest_stored}"
          + (f", {bars[0]['d']} .. {bars[-1]['d']}" if bars else ""))


# ------------------------------------------------------------------ PSX archive


def psx_targets() -> tuple[dict[str, set], list[str]]:
    """{symbol: missing dates} for the names Yahoo does not serve, and the dates to fetch."""
    stored = load(ROOT / ".cache" / "psx_backfill" / "stored.json")["series"]
    plan = load(ROOT / ".cache" / "psx_backfill" / "plan_full.json")
    state = load(ROOT / ".cache" / "psx_backfill" / "fetch_state.json")
    cal = set()
    for v in stored.values():
        cal |= set(v["bars"])
    for v in plan.values():
        cal |= {b["d"] for b in v["writable"]}
    cal = sorted(cal)
    need: dict[str, set] = {}
    dates: set[str] = set()
    for sym in state["notServed"]:
        have = set(stored[sym]["bars"])
        lo, hi = min(have), max(have)
        miss = {d for d in cal if lo <= d <= hi and d not in have}
        need[sym] = miss
        dates |= miss
    return need, sorted(dates)


def cmd_psx_archive() -> None:
    """The exchange's own closing file is the alternative source for the names Yahoo 404s.

    It is also the raw-basis source, so nothing acquired here can conflict with what is stored.
    Every archive carries the whole market, so the same download that fills these names also
    records which symbols existed on that date and are absent from the universe today.
    """
    import psx
    need, dates = psx_targets()
    limit = int(arg("--limit") or 0) or None
    if limit:
        dates = dates[:limit]
    today = date.today()
    ledger_path = STAGE / "psx_archive_ledger.json"
    ledger = load(ledger_path, {"days": {}, "bars": {}, "seenSymbols": {}})
    print(f"psx-archive: {len(dates)} dates to read for {sum(1 for v in need.values() if v)} names",
          flush=True)
    for i, d in enumerate(dates, 1):
        if d in ledger["days"]:
            continue
        day = date.fromisoformat(d)
        rows = psx.read_day(day, today, keep=None)
        if rows is None:
            ledger["days"][d] = {"published": False}
            continue
        ledger["days"][d] = {"published": True, "symbols": len(rows)}
        for sym in rows:
            ledger["seenSymbols"].setdefault(sym, [None, None])
            lo, hi = ledger["seenSymbols"][sym]
            ledger["seenSymbols"][sym] = [min(lo or d, d), max(hi or d, d)]
        for sym, want in need.items():
            if d in want and sym in rows:
                r = rows[sym]
                ledger["bars"].setdefault(sym, {})[d] = {
                    "d": d, "o": r.get("open"), "h": r.get("high"), "l": r.get("low"),
                    "c": r.get("close"), "v": r.get("volume")}
        if i % 25 == 0 or i == len(dates):
            dump(ledger_path, ledger)
            print(f"  {i}/{len(dates)} days read, "
                  f"{sum(len(v) for v in ledger['bars'].values())} bars staged", flush=True)
    dump(ledger_path, ledger)
    print(f"psx-archive done: {sum(len(v) for v in ledger['bars'].values())} bars for "
          f"{len(ledger['bars'])} names across {len(ledger['days'])} days")


# ------------------------------------------------------------------ withheld


def cmd_withheld() -> None:
    """Re-derive the basis-conflicting bars and stage them where nothing can mistake them for clean."""
    from psx_backfill import TOL, reconcile, validate
    stored = load(ROOT / ".cache" / "psx_backfill" / "stored.json")["series"]
    staged_dir = ROOT / ".cache" / "psx_backfill" / "staged"
    out: dict[str, dict] = {}
    totals: dict[str, int] = defaultdict(int)
    inrange = outrange = 0
    for p in sorted(staged_dir.glob("*.json")):
        g = load(p)
        sym = g["symbol"]
        s = stored.get(sym) or {"bars": {}}
        good, _ = validate(g["bars"])
        rec = reconcile(good, s["bars"], g["splits"])
        if not rec["held"]:
            continue
        yq = {b["d"]: b for b in good}
        have = set(s["bars"])
        lo, hi = (min(have), max(have)) if have else ("9999", "0000")
        rows = []
        for reason, days in rec["held"].items():
            totals[reason] += len(days)
            for d in days:
                within = lo <= d <= hi
                inrange += within
                outrange += not within
                rows.append({**yq[d], "reason": reason, "insideStoredRange": within})
        out[sym] = {"anchors": rec["anchors"], "anchorsAgreeing": rec["anchorsAgreeing"],
                    "medianRatio": rec["medianRatio"], "splits": g["splits"],
                    "storedRange": [lo, hi], "bars": sorted(rows, key=lambda r: r["d"])}
    dump(STAGE / "psx_withheld.json",
         {"generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
          "whatThisIs": ("PSX daily bars the provider served and this project refused to write, "
                         "because the nearest stored anchor on one side prices that stretch of "
                         f"history on a different basis (tolerance {TOL:.1%}). Adjustment-sensitive: "
                         "it must not be written to PriceSnapshot without a sourced factor."),
          "symbols": len(out), "bars": sum(len(v["bars"]) for v in out.values()),
          "byReason": dict(totals), "insideAStoredRange": inrange, "outsideAStoredRange": outrange,
          "series": out})
    print(f"withheld staged: {sum(len(v['bars']) for v in out.values())} bars across {len(out)} symbols")
    print(f"  by reason: {dict(totals)}")
    print(f"  inside a stored range: {inrange}   outside it: {outrange}")


# ------------------------------------------------------------------ single observations


def cmd_observations() -> None:
    """KSE-100, the SBP policy rate and KIBOR as published today, with the page they came from.

    One observation each. These three publish a current value on a server-rendered page and keep
    their history somewhere this task could not reach; that is recorded in the manifest rather
    than smoothed over.
    """
    got = {"capturedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"), "series": {}}

    st, body = browser_get("https://dps.psx.com.pk/indices")
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body.decode("utf-8", "replace")))
    for name in ("KSE100", "KSE30", "ALLSHR", "KMI30"):
        m = re.search(rf"\b{name}\s+([\d,]+\.\d+)", text)
        if m:
            got["series"][name] = {
                "value": float(m.group(1).replace(",", "")),
                "source": "Pakistan Stock Exchange, dps.psx.com.pk/indices",
                "basis": "index level, current session", "status": st,
                "historyAvailable": False}

    st, body = browser_get("https://www.sbp.org.pk/our-operations/monetary-policy")
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body.decode("utf-8", "replace")))
    for label, key in (("SBP Policy Rate", "SBP_POLICY_RATE"),
                       ("SBP Overnight Reverse Repo \\(Ceiling Rate\\)", "SBP_CEILING"),
                       ("SBP Overnight Repo Rate \\(Floor\\) Rate", "SBP_FLOOR")):
        m = re.search(rf"{label}\s+([\d.]+)%", text)
        if m:
            got["series"][key] = {
                "value": float(m.group(1)), "unit": "percent per annum",
                "source": "State Bank of Pakistan, /our-operations/monetary-policy",
                "basis": "policy rate, not an interbank rate", "status": st,
                "historyAvailable": False}

    st, body = browser_get("https://www.sbp.org.pk/ecodata/kibor_index.asp")
    text = body.decode("utf-8", "replace")
    asof = re.search(r"KIBOR As on ([\d\- A-Za-z]+)</h5>", text)
    rows = re.findall(r"<td[^>]*>\s*([\d\w\- ]+?)\s*</td>\s*<td[^>]*>\s*([\d.]+)\s*</td>\s*"
                      r"<td[^>]*>\s*([\d.]+)\s*</td>", text)
    if rows:
        got["series"]["KIBOR"] = {
            "asOf": (asof.group(1).strip() if asof else None),
            "tenors": [{"tenor": a.strip(), "bid": float(b), "offer": float(c)} for a, b, c in rows[:12]],
            "source": "State Bank of Pakistan, /ecodata/kibor_index.asp",
            "basis": "interbank offered rate, not the policy rate", "status": st,
            "historyAvailable": False}
    dump(STAGE / "observations.json", got)
    print(json.dumps(got, indent=1)[:1400])


def cmd_btc_early() -> None:
    """Bitcoin daily before Coinbase's floor, from Bitstamp -- a venue this project already uses.

    Coinbase's own earliest BTC-USD daily candle is 2015-07-20: the walk backwards returned 24
    candles on its fifth page and nothing on its sixth, so that is the venue's floor and not a
    budget's. Bitstamp has quoted the pair since 2011 and is already declared in `nbt.HOST_DELAY`,
    which makes it the one permitted place to ask for the earlier history.

    Kept in its own file under its own source. Two venues' prints for the same day are two
    observations, not one, and merging them is a cleaning decision for the next milestone.
    """
    from nbt import get_json
    floor = date(2015, 7, 20)
    got: dict[str, dict] = {}
    end = floor
    for page in range(1, 20):
        start = end - timedelta(days=950)
        url = ("https://www.bitstamp.net/api/v2/ohlc/btcusd/?step=86400&limit=1000"
               f"&start={(start - date(1970, 1, 1)).days * 86400}")
        j = get_json(url, ttl=7 * 24 * 3600, timeout=40, cache_key=f"acquire:btcstamp:{start}")
        rows = ((j or {}).get("data") or {}).get("ohlc") or []
        if not rows:
            print(f"  page {page}: no answer for {start} .. {end}")
            break
        kept = 0
        for r in rows:
            d = (datetime(1970, 1, 1, tzinfo=timezone.utc)
                 + timedelta(seconds=int(r["timestamp"]))).date()
            if d >= floor:
                continue
            if float(r["close"]) <= 0:
                continue
            got[d.isoformat()] = {"d": d.isoformat(), "o": float(r["open"]), "h": float(r["high"]),
                                  "l": float(r["low"]), "c": float(r["close"]),
                                  "v": float(r["volume"])}
            kept += 1
        print(f"  page {page}: {start} .. {end} -> {len(rows)} candles, {kept} before the floor",
              flush=True)
        if kept == 0:
            break
        end = start
    bars = [got[k] for k in sorted(got)]
    dump(STAGE / "btc_pre_2015_bitstamp.json",
         {"product": "BTC/USD", "source": "Bitstamp API v2 ohlc",
          "basis": "exchange traded spot pair, raw",
          "coinbaseFloor": floor.isoformat(),
          "fetchedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"), "bars": bars})
    print(f"btc-early: {len(bars)} daily bars before {floor}"
          + (f", {bars[0]['d']} .. {bars[-1]['d']}" if bars else ""))


def cmd_fred() -> None:
    """Re-pull the named FRED benchmarks from the series' own first observation, not from 2010.

    The macro files were collected with `cosd=2010-01-01`, which is a choice the project made and
    not the series' extent. The frozen target names the 10-year yield, so it is pulled from FRED's
    own floor and staged beside -- not over -- the existing file.
    """
    from nbt import get
    wanted = {"DGS10": "10-year Treasury yield", "VIXCLS": "CBOE volatility index",
              "DTWEXBGS": "Broad trade-weighted US dollar index (NOT DXY)",
              "DFF": "Effective federal funds rate", "DCOILWTICO": "WTI crude oil spot"}
    out = {}
    for sid, title in wanted.items():
        url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}&cosd=1900-01-01"
        raw = get(url, ttl=24 * 3600, timeout=60, cache_key=f"acquire:fred:{sid}")
        if not raw:
            out[sid] = {"title": title, "acquired": False, "reason": "no answer from FRED"}
            print(f"  {sid:12} NO ANSWER")
            continue
        lines = raw.decode("utf-8", "replace").splitlines()
        rows = []
        for line in lines[1:]:
            parts = line.split(",")
            if len(parts) < 2 or parts[1].strip() in ("", "."):
                continue
            try:
                rows.append({"d": parts[0].strip(), "v": float(parts[1])})
            except ValueError:
                continue
        dump(STAGE / "fred" / f"{sid}.json",
             {"series": sid, "title": title, "source": url,
              "fetchedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "observations": rows})
        out[sid] = {"title": title, "acquired": True, "observations": len(rows),
                    "first": rows[0]["d"] if rows else None,
                    "last": rows[-1]["d"] if rows else None, "source": url}
        print(f"  {sid:12} {len(rows):6} observations  {rows[0]['d']} .. {rows[-1]['d']}")
    dump(STAGE / "fred" / "_report.json", out)


def cmd_psx_sweep() -> None:
    """Every PSX session since 2018, from the exchange's own archive, with a durable per-date status.

    The targeted run before this read 272 dates chosen for 23 symbols. That was the wrong shape for
    the question: the exchange's file carries the whole market on every date, so one pass over the
    calendar answers the Yahoo-404 names, the pad-rejected gaps, the 2018 history that predates the
    stored series, the delisted names and the basis-divergent dates at once -- and at the raw basis
    the stored series already uses, which is the one basis that needs no adjudication.

    Nothing is parsed into a second copy here. `nbt.get` caches each archive on disk for a year and
    `psx.read_day` reads through that same cache key, so the download is the persistence and every
    later pass over it is free. What this writes is the ledger: for each date, whether the exchange
    published a file, how many symbols traded, or why no answer came back.

    A holiday and a refusal both arrive as "no answer". They are told apart by how many come in a
    row: a closed market gives a short run, a rate limit gives an unbroken one, and after
    `STOP_AFTER` consecutive silences the run makes one direct status request and stops if the host
    is refusing -- leaving the checkpoint exactly where the next run should resume.
    """
    import psx
    from nbt import get
    STOP_AFTER = 20
    start = date.fromisoformat(arg("--from") or "2018-01-01")
    end = date.fromisoformat(arg("--to")) if arg("--to") else date.today()
    limit = int(arg("--limit") or 0) or None

    path = STAGE / "psx_sweep_ledger.json"
    ledger = load(path, {"dates": {}, "startedAt": None})
    ledger["startedAt"] = ledger["startedAt"] or datetime.now(timezone.utc).isoformat(timespec="seconds")

    days = []
    d = start
    while d <= end:
        if d.weekday() < 5 and ledger["dates"].get(d.isoformat(), {}).get("status") not in (
                "published", "notPublished"):
            days.append(d)
        d += timedelta(days=1)
    if limit:
        days = days[:limit]
    print(f"psx-sweep: {start} .. {end}, {len(days)} dates to read "
          f"({len(ledger['dates'])} already settled)", flush=True)

    silent = 0
    for i, day in enumerate(days, 1):
        key = day.isoformat()
        raw = get(psx.file_url(day), cache_key=f"psx-{key}", ttl=psx.ttl_for(day, date.today()))
        if raw is None:
            silent += 1
            ledger["dates"][key] = {"status": "noAnswer", "consecutive": silent}
            if silent >= STOP_AFTER:
                code = status(psx.file_url(day))
                if code != 404:
                    ledger["stoppedAt"] = {"date": key, "httpStatus": code,
                                           "reason": "the host stopped answering; resume from here"}
                    dump(path, ledger)
                    print(f"  STOPPED at {key}: {STOP_AFTER} silent dates and a direct request "
                          f"returned {code}. Checkpoint saved.", flush=True)
                    return
                silent = 0          # a long closure, confirmed by a real 404
            continue
        silent = 0
        text = psx.unpack(raw)
        if text is None:
            ledger["dates"][key] = {"status": "notAnArchive", "bytes": len(raw)}
            continue
        rows = psx.read_day(day, date.today(), keep=None) or {}
        ledger["dates"][key] = {"status": "published" if rows else "publishedButEmpty",
                                "symbols": len(rows)}
        if i % 25 == 0 or i == len(days):
            dump(path, ledger)
            done = sum(1 for v in ledger["dates"].values() if v["status"] == "published")
            print(f"  {i}/{len(days)} read, {done} published days in the ledger", flush=True)
    dump(path, ledger)
    by = Counter(v["status"] for v in ledger["dates"].values())
    print(f"psx-sweep done: {dict(by)}")


COMMANDS = {"benchmarks": cmd_benchmarks, "btc": cmd_btc, "btc-early": cmd_btc_early,
            "fred": cmd_fred, "psx-archive": cmd_psx_archive, "psx-sweep": cmd_psx_sweep,
            "withheld": cmd_withheld, "observations": cmd_observations}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        raise SystemExit(2)
    COMMANDS[sys.argv[1]]()
