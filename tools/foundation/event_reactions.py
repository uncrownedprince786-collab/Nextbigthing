"""What the market did around each verified event, measured without seeing the future.

    python tools/foundation/event_reactions.py [--out DIR] [--horizons 1,5,20,60]

Writes `data/foundation/events/reactions.jsonl.gz` and `reactions_manifest.json`. One row per
(event, instrument). Reads the database and two committed benchmark files; writes no database row.

**The separation this file exists to keep.** An event is not a signal. So each row holds three
things that are never merged:

  `before`   the asset's state from bars dated **strictly before** the event date. This is the
             only part a model may use as an input feature.
  `day0`     the move on the event's own session. This is reaction evidence and a classification
             label -- it is *not* actionable, because the information arrived during that session
             and the close is already after it.
  `forward`  returns measured from the session **after** day0, over each horizon. This is what a
             decision taken on the evidence could actually have earned, and it is the only part
             fit to be an outcome label.

Mixing `day0` into the features is the leak this layout makes hard to write by accident, and
mixing it into the outcome is the overstatement that makes every event study look profitable.

**Benchmark.** Each instrument is adjusted by the market it trades in: `^GSPC` from
`data/foundation/benchmarks/GSPC.csv.gz` for US and global instruments, and an equal-weighted
return across PKR-quoted assets for PSX. Crypto and FX are reported raw and flagged
`benchmarkApplies: false` rather than being adjusted by an equity index they have no beta to.

The PSX benchmark is computed from the database's own PKR series -- the exchange file plus the
recovered Karachi listing -- and never from the private Karandaaz index segment. That file is
permitted for internal research only, and a committed artifact derived from it would carry its
values out of the boundary it was given.

**Coverage is reported, never filled.** A horizon that extends past the stored history, or an
event before an instrument's first bar, produces `null` with a stated reason. No outcome is
interpolated, and an event whose window has not closed is marked rather than shortened.
"""

from __future__ import annotations

import gzip
import json
import statistics
import sys
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "jobs"))

CORPUS = ROOT / "data" / "foundation" / "events" / "events.json"
GSPC = ROOT / "data" / "foundation" / "benchmarks" / "GSPC.csv.gz"

ALIAS = {"OIL": "CL=F", "GOLD": "GC=F", "BTC": "btc-bitcoin", "ETH": "eth-ethereum"}
PROXIES = {"MKT", "PSX"}
DEFAULT_HORIZONS = (1, 5, 20, 60)
# Trailing windows for the before-state. 20 sessions is the project's standard factor window.
BEFORE_WINDOWS = (5, 20, 60)
# Asset classes an equity index is not a sensible benchmark for.
NO_BENCHMARK = {"crypto", "forex", "commodity"}


def arg(name: str, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def pct(a: float, b: float) -> float | None:
    """Percent change from a to b, or None when the base cannot carry one."""
    return None if not a or a <= 0 else (b / a - 1.0) * 100.0


def realized_vol(closes: list[float]) -> float | None:
    """Standard deviation of session returns, in percent. None below three closes."""
    rets = [(b / a - 1.0) * 100.0 for a, b in zip(closes, closes[1:]) if a and a > 0]
    return round(statistics.pstdev(rets), 4) if len(rets) >= 2 else None


def index_on_or_after(dates: list[date], target: date) -> int | None:
    lo, hi = 0, len(dates)
    while lo < hi:
        mid = (lo + hi) // 2
        if dates[mid] < target:
            lo = mid + 1
        else:
            hi = mid
    return lo if lo < len(dates) else None


def before_state(dates, closes, vols, i0: int) -> dict:
    """The asset as it stood using only bars strictly before the event session.

    `i0` is the index of the event session, so every slice here ends at `i0 - 1`. That bound is
    the whole point: it is what makes these fields usable as model inputs.
    """
    out: dict = {"sessionsAvailable": i0}
    if i0 <= 0:
        return out
    prior = closes[:i0]
    out["lastClose"] = round(prior[-1], 6)
    out["lastSession"] = dates[i0 - 1].isoformat()
    for w in BEFORE_WINDOWS:
        key = f"return{w}d"
        out[key] = (None if len(prior) < w + 1
                    else round(pct(prior[-1 - w], prior[-1]) or 0.0, 4))
    out["volatility20d"] = realized_vol(prior[-21:]) if len(prior) >= 21 else None
    recent = [v for v in vols[max(0, i0 - 20):i0] if v]
    out["avgVolume20d"] = round(sum(recent) / len(recent), 2) if recent else None
    if len(prior) >= 252:
        year = prior[-252:]
        out["pctFrom52wHigh"] = round(pct(max(year), prior[-1]) or 0.0, 4)
        out["pctFrom52wLow"] = round(pct(min(year), prior[-1]) or 0.0, 4)
    return out


def forward_block(dates, closes, i_entry: int, horizon: int) -> dict | None:
    """Return, excursions and drawdown over `horizon` sessions from the entry session.

    None when the stored history does not reach the end of the window -- a shorter window
    reported under a longer label is the quiet way an event study invents an outcome.
    """
    if i_entry <= 0 or i_entry >= len(closes):
        return None
    end = i_entry + horizon
    if end >= len(closes):
        return None
    entry = closes[i_entry]
    if not entry or entry <= 0:
        return None
    path = closes[i_entry:end + 1]
    peak = max(path)
    trough = min(path)
    # Max drawdown inside the window: the worst fall from a running peak, which is a different
    # question from the worst level reached.
    run, dd = path[0], 0.0
    for c in path:
        run = max(run, c)
        dd = min(dd, (c / run - 1.0) * 100.0 if run else 0.0)
    ret = pct(entry, closes[end])
    return {
        "entrySession": dates[i_entry].isoformat(),
        "exitSession": dates[end].isoformat(),
        "returnPct": None if ret is None else round(ret, 4),
        "maxFavourablePct": round(pct(entry, peak) or 0.0, 4),
        "maxAdversePct": round(pct(entry, trough) or 0.0, 4),
        "maxDrawdownPct": round(dd, 4),
        "volatilityPct": realized_vol(path),
        "sessionsToPeak": path.index(peak),
        "sessionsToTrough": path.index(trough),
    }


def load_benchmark_csv(path: Path) -> dict[date, float]:
    opener = gzip.open if path.suffix == ".gz" else open
    out: dict[date, float] = {}
    with opener(path, "rt", encoding="utf-8") as fh:
        header = fh.readline().strip().split(",")
        ci = header.index("close")
        di = header.index("date")
        for line in fh:
            f = line.rstrip("\n").split(",")
            try:
                out[date.fromisoformat(f[di])] = float(f[ci])
            except (ValueError, IndexError):
                continue
    return out


def main() -> int:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    from nbt import db, rows

    horizons = tuple(int(x) for x in str(arg("--horizons", "")).split(",") if x) or DEFAULT_HORIZONS
    out_dir = Path(arg("--out", ROOT / "data" / "foundation" / "events"))
    out_dir.mkdir(parents=True, exist_ok=True)

    doc = json.loads(CORPUS.read_text(encoding="utf-8"))
    events = [e for e in doc.get("events", []) if e.get("verified")]
    wanted = {ALIAS.get(e["instrument"], e["instrument"]) for e in events
              if e.get("instrument") and e["instrument"] not in PROXIES}

    conn = db()
    conn.rollback()
    conn.read_only = True
    cur = conn.cursor()
    try:
        got = rows(cur,
                   'SELECT a.symbol, a."assetType"::text AS kind, p.date, p.close, p.volume '
                   'FROM "PriceSnapshot" p JOIN "Asset" a ON a.id = p."assetId" '
                   'WHERE a.symbol = ANY(%s) AND p.close IS NOT NULL '
                   'ORDER BY a.symbol, p.date', (sorted(wanted),))
        # The PSX proxy: an equal-weighted return across every PKR-quoted asset, from the stored
        # series only. Never the private index segment.
        psx = rows(cur, '''SELECT date, avg(r) AS r FROM (
            SELECT p.date, p.close / lag(p.close) OVER (PARTITION BY p."assetId" ORDER BY p.date)
                   - 1 AS r
            FROM "PriceSnapshot" p JOIN "Asset" a ON a.id = p."assetId"
            WHERE a.currency = 'PKR') x
            WHERE r IS NOT NULL AND abs(r) < 0.4 GROUP BY date ORDER BY date''')
    finally:
        cur.close()
        conn.close()

    series: dict[str, dict] = defaultdict(lambda: {"dates": [], "closes": [], "vols": [],
                                                   "kind": None})
    for r in got:
        s = series[r["symbol"]]
        s["kind"] = r["kind"]
        s["dates"].append(r["date"])
        s["closes"].append(float(r["close"]))
        s["vols"].append(float(r["volume"]) if r["volume"] is not None else None)

    # The two market proxies, rebuilt as index levels so the same maths applies to them.
    gspc = load_benchmark_csv(GSPC)
    gs_dates = sorted(gspc)
    series["MKT"] = {"dates": gs_dates, "closes": [gspc[d] for d in gs_dates],
                     "vols": [None] * len(gs_dates), "kind": "index"}
    level, pdates, pcloses = 100.0, [], []
    for r in psx:
        level *= (1.0 + float(r["r"]))
        pdates.append(r["date"])
        pcloses.append(level)
    series["PSX"] = {"dates": pdates, "closes": pcloses, "vols": [None] * len(pdates),
                     "kind": "index"}

    bench = series["MKT"]
    bench_idx = {d: i for i, d in enumerate(bench["dates"])}

    written = 0
    stats: dict[str, int] = defaultdict(int)
    horizon_cov: dict[int, int] = defaultdict(int)
    path = out_dir / "reactions.jsonl.gz"
    with gzip.open(path, "wt", encoding="utf-8", compresslevel=6) as fh:
        for e in sorted(events, key=lambda x: x["date"]):
            ins = e.get("instrument")
            sym = ALIAS.get(ins, ins)
            key = ins if ins in PROXIES else sym
            s = series.get(key)
            when = date.fromisoformat(e["date"])
            if not s or not s["dates"]:
                stats["noInstrumentSeries"] += 1
                continue
            i0 = index_on_or_after(s["dates"], when)
            if i0 is None:
                stats["eventAfterStoredHistory"] += 1
                continue
            if i0 == 0:
                stats["eventBeforeInstrumentHistory"] += 1
                continue

            day0 = {
                "session": s["dates"][i0].isoformat(),
                "sessionIsEventDate": s["dates"][i0] == when,
                "returnPct": round(pct(s["closes"][i0 - 1], s["closes"][i0]) or 0.0, 4),
            }
            # An instrument cannot be its own benchmark: MKT *is* ^GSPC, so an excess return
            # against it is 0 by construction and would read as "no abnormal move" rather than
            # "the question does not apply".
            applies = s["kind"] not in NO_BENCHMARK and key != "MKT"
            row = {
                "eventDate": e["date"],
                "name": e["name"],
                "category": e.get("category"),
                "cluster": e.get("cluster"),
                "tier": e.get("tier"),
                "evidenceGroups": e.get("evidenceGroups") or [],
                "instrument": ins,
                "symbol": key,
                "assetClass": s["kind"],
                "benchmark": ("PSX equal-weighted" if key == "PSX" and applies
                              else "^GSPC" if applies else None),
                "isBenchmarkItself": key == "MKT",
                "benchmarkApplies": applies,
                "before": before_state(s["dates"], s["closes"], s["vols"], i0),
                "day0": day0,
                "forward": {},
            }
            for h in horizons:
                blk = forward_block(s["dates"], s["closes"], i0 + 1, h)
                if blk and applies and key != "PSX":
                    bi = bench_idx.get(s["dates"][i0 + 1])
                    bj = bench_idx.get(date.fromisoformat(blk["exitSession"]))
                    if bi is not None and bj is not None and bj > bi:
                        br = pct(bench["closes"][bi], bench["closes"][bj])
                        blk["benchmarkReturnPct"] = None if br is None else round(br, 4)
                        if blk["returnPct"] is not None and br is not None:
                            blk["excessReturnPct"] = round(blk["returnPct"] - br, 4)
                if blk:
                    blk["direction"] = ("up" if (blk["returnPct"] or 0) > 0 else
                                        "down" if (blk["returnPct"] or 0) < 0 else "flat")
                    blk["continuation"] = (
                        None if not day0["returnPct"] or blk["returnPct"] is None
                        else (day0["returnPct"] > 0) == (blk["returnPct"] > 0))
                    horizon_cov[h] += 1
                else:
                    stats[f"windowOpen:{h}"] += 1
                row["forward"][str(h)] = blk
            fh.write(json.dumps(row, separators=(",", ":")) + "\n")
            written += 1

    manifest = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "version": "event-reactions-v1",
        "corpus": str(CORPUS.relative_to(ROOT)).replace("\\", "/"),
        "verifiedEventsInCorpus": len(events),
        "rowsWritten": written,
        "horizons": list(horizons),
        "horizonCoverage": {str(h): horizon_cov[h] for h in horizons},
        "skipped": dict(stats),
        "benchmarks": {"global": "^GSPC from data/foundation/benchmarks/GSPC.csv.gz",
                       "psx": "equal-weighted return across PKR-quoted stored assets",
                       "notBenchmarked": sorted(NO_BENCHMARK)},
        "pointInTime": {
            "beforeUses": "bars dated strictly before the event session",
            "day0": "the event session's own move; evidence, never an input feature",
            "forwardStartsAt": "the session after day0, so no outcome overlaps its own evidence",
            "incompleteWindows": "reported as null, never shortened",
        },
        "privateData": ("the Karandaaz KSE-100 segment was not read; the PSX benchmark is the "
                        "stored PKR series"),
        "bytes": path.stat().st_size,
    }
    (out_dir / "reactions_manifest.json").write_text(
        json.dumps(manifest, indent=1), encoding="utf-8")

    print(f"verified events        : {len(events)}")
    print(f"reaction rows written  : {written}")
    for h in horizons:
        print(f"  horizon {h:>3}d coverage : {horizon_cov[h]:>3} of {written}")
    if stats:
        print(f"  skipped/incomplete   : {dict(stats)}")
    print(f"wrote {path} ({path.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
