"""Year-wise coverage, and whether the crashes and bull runs are actually in the training data.

    python tools/foundation/regime_coverage.py [--dataset DIR] [--out DIR]

Writes `data/foundation/dataset/regime_coverage.json`. Reads the database (read-only), the
committed benchmark files and the durable `examples-v3` copy. Writes no database row and fetches
nothing.

**Why the price table is not the answer.** A crash can sit in `PriceSnapshot` and still be absent
from the assembled examples -- a session is only an example when it has features and a matured
label, and the quality flags can exclude it afterwards. So every episode found here is then
counted *in the dataset*, with its flagged and immature rows separated out.

**Episode definitions, because the project had none.** No crash, bull-run or regime definition
existed in this repository, so these are stated here rather than inherited:

  *drawdown episode* -- from a running peak to the lowest close before that peak is regained.
  It counts when the fall reaches the threshold. Recovery is the first session back at the peak;
  an episode whose peak is never regained inside the data is reported as unrecovered rather than
  given an invented end.

  *advance episode* -- from a trough to the highest close before the next qualifying drawdown.
  Reported with its deepest interim pullback, so a sustained advance can be told from a sharp
  rally that gave most of it back.

**Thresholds are shown as a sensitivity, not a verdict.** -10%, -15%, -20% and -30% are all
reported. One cutoff cannot be right for equities, crypto, FX, PSX and commodities at once:
crypto routinely falls further in a week than FX does in a decade.

**Future prices are used here and must not leak.** Identifying a peak requires knowing what came
after it. That is legitimate for a retrospective inventory and illegitimate as a feature, so
nothing this tool computes is written back into the dataset -- it only counts examples that
already exist.

PSX before 2021-10-15 has no public index: `KSE100.csv` starts there, and the earlier segment is
the private Karandaaz file, which no committed artifact may derive from. The equal-weighted return
across stored PKR assets is used instead, and the switch is recorded.
"""

from __future__ import annotations

import gzip
import json
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "jobs"))

BENCH = ROOT / "data" / "foundation" / "benchmarks"
KSE = ROOT / "data" / "foundation" / "psx_index" / "KSE100.csv"
DEFAULT_DS = Path(r"C:\Users\NEW TECH\nbt-private\dataset"
                  r"\examples-v3-2026-10-15-run38735767762\dataset")
OUT_DIR = ROOT / "data" / "foundation" / "dataset"

THRESHOLDS = (0.10, 0.15, 0.20, 0.30)
PRIMARY = 0.20          # the headline cutoff; the others are the sensitivity
START = date(2018, 1, 1)
LABEL_HORIZON = 20      # for the effective-independent-window figure


def arg(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def read_series(path: Path, date_col="date", close_col="close") -> list[tuple[date, float]]:
    opener = gzip.open if path.suffix == ".gz" else open
    out = []
    with opener(path, "rt", encoding="utf-8") as fh:
        head = fh.readline().strip().split(",")
        di, ci = head.index(date_col), head.index(close_col)
        for line in fh:
            f = line.rstrip("\n").split(",")
            try:
                d = date.fromisoformat(f[di])
                v = float(f[ci])
            except (ValueError, IndexError):
                continue
            if v > 0 and d >= START:
                out.append((d, v))
    return sorted(out)


def episodes(series: list[tuple[date, float]], threshold: float) -> list[dict]:
    """Peak-to-trough falls of at least `threshold`, with recovery where it happens."""
    if not series:
        return []
    out = []
    peak_d, peak_v = series[0]
    trough_d, trough_v = series[0]
    in_ep = False
    for d, v in series:
        if v >= peak_v:
            if in_ep:
                out.append({"peakDate": peak_d.isoformat(), "peakClose": round(peak_v, 4),
                            "troughDate": trough_d.isoformat(), "troughClose": round(trough_v, 4),
                            "drawdownPct": round((trough_v / peak_v - 1) * 100, 2),
                            "sessionsToTrough": None, "recoveryDate": d.isoformat(),
                            "recovered": True})
                in_ep = False
            peak_d, peak_v = d, v
            trough_d, trough_v = d, v
            continue
        if v < trough_v:
            trough_d, trough_v = d, v
        if not in_ep and (trough_v / peak_v - 1) <= -threshold:
            in_ep = True
    if in_ep:
        out.append({"peakDate": peak_d.isoformat(), "peakClose": round(peak_v, 4),
                    "troughDate": trough_d.isoformat(), "troughClose": round(trough_v, 4),
                    "drawdownPct": round((trough_v / peak_v - 1) * 100, 2),
                    "sessionsToTrough": None, "recoveryDate": None, "recovered": False})
    idx = {d: i for i, (d, _) in enumerate(series)}
    for e in out:
        a, b = idx.get(date.fromisoformat(e["peakDate"])), idx.get(
            date.fromisoformat(e["troughDate"]))
        if a is not None and b is not None:
            e["sessionsToTrough"] = b - a
        if e["recoveryDate"]:
            c = idx.get(date.fromisoformat(e["recoveryDate"]))
            if c is not None and b is not None:
                e["sessionsTroughToRecovery"] = c - b
    return out


def advances(series: list[tuple[date, float]], eps: list[dict]) -> list[dict]:
    """Trough-to-peak advances between drawdown episodes, with the deepest interim pullback."""
    if not series:
        return []
    marks = [date.fromisoformat(e["troughDate"]) for e in eps]
    idx = {d: i for i, (d, _) in enumerate(series)}
    out = []
    for i, t in enumerate(marks):
        a = idx.get(t)
        if a is None:
            continue
        end = len(series) - 1
        for nxt in marks[i + 1:]:
            j = idx.get(nxt)
            if j and j > a:
                end = j
                break
        seg = series[a:end + 1]
        if len(seg) < 2:
            continue
        hi_i = max(range(len(seg)), key=lambda k: seg[k][1])
        start_v, hi_d, hi_v = seg[0][1], seg[hi_i][0], seg[hi_i][1]
        if hi_v / start_v - 1 <= 0:
            continue
        run = seg[:hi_i + 1]
        peak = run[0][1]
        worst = 0.0
        for _, v in run:
            peak = max(peak, v)
            worst = min(worst, v / peak - 1)
        out.append({"startDate": seg[0][0].isoformat(), "startClose": round(start_v, 4),
                    "peakDate": hi_d.isoformat(), "peakClose": round(hi_v, 4),
                    "gainPct": round((hi_v / start_v - 1) * 100, 2),
                    "sessions": hi_i,
                    "deepestPullbackPct": round(worst * 100, 2)})
    return out


def main() -> int:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    from nbt import db, rows
    from sessions import session_bar

    ds = Path(arg("--dataset", DEFAULT_DS))
    out_dir = Path(arg("--out", OUT_DIR))
    out_dir.mkdir(parents=True, exist_ok=True)

    # ---- 1. year-wise coverage, from the database, within each asset's own listed range -------
    conn = db()
    conn.rollback()
    conn.read_only = True
    cur = conn.cursor()
    cur.execute("SET statement_timeout='900s'")
    try:
        yearly = rows(cur, f"""
        WITH m AS (SELECT a.id, CASE WHEN a.currency='PKR' THEN 'PSX'
                    WHEN a."assetType"::text IN ('stock','etf') THEN 'US'
                    ELSE a."assetType"::text END AS market FROM "Asset" a),
        b AS (SELECT m.market, p."assetId", p.date,
                     (p.high IS NULL OR p.low IS NULL) AS no_range
              FROM "PriceSnapshot" p JOIN m ON m.id=p."assetId" WHERE {session_bar("p")}),
        cal AS (SELECT DISTINCT market, date FROM b),
        rng AS (SELECT market, "assetId", min(date) lo, max(date) hi FROM b GROUP BY 1,2),
        expd AS (SELECT r.market, EXTRACT(year FROM c.date)::int yr, count(*) AS expected
                 FROM rng r JOIN cal c ON c.market=r.market AND c.date BETWEEN r.lo AND r.hi
                 GROUP BY 1,2),
        got AS (SELECT market, EXTRACT(year FROM date)::int yr, count(*) AS observed,
                       count(DISTINCT "assetId") AS instruments,
                       count(*) FILTER (WHERE no_range) AS without_range
                FROM b GROUP BY 1,2)
        SELECT g.market, g.yr, g.observed, g.instruments, g.without_range, e.expected
        FROM got g JOIN expd e ON e.market=g.market AND e.yr=g.yr
        ORDER BY g.market, g.yr""")
        # The literal % in a LIKE pattern collides with psycopg's placeholder parsing, so the
        # pattern travels as a parameter rather than inside the statement.
        quarantined = rows(cur, """
        SELECT EXTRACT(year FROM date)::int yr, count(*) n FROM "PriceSnapshot"
        WHERE source LIKE %s AND high IS NOT NULL AND low IS NOT NULL
          AND high<>low AND (close>high OR close<low) GROUP BY 1 ORDER BY 1""", ("Pakistan%",))
        # The committed BTC benchmark files are the pre-2018 backfill and stop at 2018-11-03;
        # the live series lives in the database. Using the file alone silently reduced crypto to
        # ten months and made it look like one drawdown episode.
        btc = rows(cur, """SELECT p.date, p.close FROM "PriceSnapshot" p
            JOIN "Asset" a ON a.id=p."assetId" WHERE a.symbol='btc-bitcoin'
              AND p.close IS NOT NULL ORDER BY p.date""")
        psx_eq = rows(cur, """SELECT date, avg(r) r FROM (
            SELECT p.date, p.close / lag(p.close) OVER (PARTITION BY p."assetId" ORDER BY p.date)
                   - 1 AS r
            FROM "PriceSnapshot" p JOIN "Asset" a ON a.id=p."assetId" WHERE a.currency='PKR') x
            WHERE r IS NOT NULL AND abs(r) < 0.4 GROUP BY 1 ORDER BY 1""")
    finally:
        cur.close()
        conn.close()

    coverage = defaultdict(dict)
    for r in yearly:
        exp, obs = int(r["expected"]), int(r["observed"])
        coverage[r["market"]][r["yr"]] = {
            "observed": obs, "expectedWithinListedRanges": exp,
            "missing": exp - obs,
            "coverage": round(obs / exp, 4) if exp else None,
            "instruments": int(r["instruments"]),
            "barsWithoutARange": int(r["without_range"]),
        }
    quar_by_year = {int(r["yr"]): int(r["n"]) for r in quarantined}

    # ---- 2. benchmark series, one per market group --------------------------------------------
    level, pdates = 100.0, []
    for r in psx_eq:
        level *= (1.0 + float(r["r"]))
        pdates.append((r["date"], level))
    psx_series = [(d, v) for d, v in pdates if d >= START]
    kse = read_series(KSE) if KSE.exists() else []

    series_map = {
        "US": ("^GSPC", read_series(BENCH / "GSPC.csv.gz")),
        "crypto": ("btc-bitcoin (stored series, Coinbase)",
                   sorted(set([(d, v) for d, v in
                               [(x["date"], float(x["close"])) for x in btc] if d >= START]
                              + [(d, v) for d, v in
                                 read_series(BENCH / "BTC-USD_coinbase.csv")]))),
        "forex": ("DX-Y.NYB", read_series(BENCH / "DX-Y.NYB.csv.gz")),
        "commodity": ("GC=F", read_series(BENCH / "GC_F.csv.gz")),
        "PSX": ("PSX equal-weighted (stored PKR assets)", psx_series),
    }

    # ---- 3. episodes, with a sensitivity across thresholds ------------------------------------
    inv = {}
    for market, (name, ser) in series_map.items():
        if not ser:
            inv[market] = {"benchmark": name, "note": "no usable series"}
            continue
        sens = {f"{int(t*100)}%": len(episodes(ser, t)) for t in THRESHOLDS}
        eps = episodes(ser, PRIMARY)
        inv[market] = {
            "benchmark": name,
            "range": [ser[0][0].isoformat(), ser[-1][0].isoformat()],
            "observations": len(ser),
            "episodeCountByThreshold": sens,
            "primaryThresholdPct": PRIMARY * 100,
            "drawdownEpisodes": eps,
            "advanceEpisodes": advances(ser, eps),
        }

    # ---- 4. training-example representation per episode ---------------------------------------
    # Counted by asset class, not by the dataset's `market` field: that field puts crypto and
    # commodities inside "US", so a crypto drawdown would otherwise be credited with every US
    # equity example in the same weeks.
    by_group_date: dict[str, Counter] = defaultdict(Counter)
    flagged: dict[str, Counter] = defaultdict(Counter)
    immature: dict[str, Counter] = defaultdict(Counter)
    for f in sorted(ds.glob("examples-v3-*.jsonl.gz")):
        with gzip.open(f, "rt", encoding="utf-8") as fh:
            for line in fh:
                r = json.loads(line)
                cls = r["assetType"]
                grp = ("PSX" if r.get("market") == "PK"
                       else "forex" if cls == "forex"
                       else "crypto" if cls == "crypto"
                       else "commodity" if cls == "commodity"
                       else "US")
                by_group_date[grp][r["asOf"]] += 1
                if any((r.get("dataQuality") or {}).values()):
                    flagged[grp][r["asOf"]] += 1
                if not ((r.get("outcome") or {}).get("mature20")):
                    immature[grp][r["asOf"]] += 1

    def count_window(mk: str, a: str, b: str) -> tuple[int, int, int]:
        tot = sum(n for d, n in by_group_date.get(mk, {}).items() if a <= d <= b)
        fl = sum(n for d, n in flagged.get(mk, {}).items() if a <= d <= b)
        im = sum(n for d, n in immature.get(mk, {}).items() if a <= d <= b)
        return tot, fl, im

    for market, blob in inv.items():
        for group in ("drawdownEpisodes", "advanceEpisodes"):
            for e in blob.get(group, []):
                # A drawdown runs peak -> trough (or recovery, when it recovered). An advance
                # runs start -> peak. Taking `peakDate` as the window start for an advance makes
                # both ends the same day and counts one session instead of several hundred.
                if group == "drawdownEpisodes":
                    a = e["peakDate"]
                    b = e.get("recoveryDate") or e["troughDate"]
                else:
                    a = e["startDate"]
                    b = e["peakDate"]
                n, fl, im = count_window(market, a, b)
                e["trainingExamplesInWindow"] = n
                e["ofWhichQualityFlagged"] = fl
                e["ofWhichImmatureLabel"] = im
                e["effectiveIndependentWindows"] = round(n / LABEL_HORIZON)
                e["datasetNote"] = ("counted by asset class, so this is the episode's own "
                                    "instruments and not the whole market code")

    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "version": "regime-coverage-v1",
        "method": {
            "coverageDenominator": "sessions inside each asset's own first-to-last stored range, "
                                   "on its market's calendar, so a listing or delisting date is "
                                   "never counted as missing",
            "drawdownEpisode": "running peak to the lowest close before that peak is regained, "
                               "counted when the fall reaches the threshold",
            "advanceEpisode": "trough to the highest close before the next qualifying drawdown, "
                              "reported with its deepest interim pullback",
            "thresholds": [f"{int(t*100)}%" for t in THRESHOLDS],
            "primary": f"{int(PRIMARY*100)}%",
            "lookAhead": "future prices identify a peak retrospectively; nothing computed here "
                         "is written back into the dataset or used as a feature",
            "psxIndex": "KSE100 starts 2021-10-15; before that the equal-weighted return across "
                        "stored PKR assets is used, because the earlier index segment is private",
            "quarantine": "PSX bars whose close falls outside their own range are excluded from "
                          "any range-dependent calculation; this tool uses closes only",
        },
        "yearlyCoverage": {k: dict(sorted(v.items())) for k, v in sorted(coverage.items())},
        "psxQuarantinedByYear": quar_by_year,
        "kse100Available": {"from": kse[0][0].isoformat() if kse else None,
                            "observations": len(kse)},
        "episodes": inv,
    }
    out = out_dir / "regime_coverage.json"
    out.write_text(json.dumps(payload, indent=1), encoding="utf-8")

    print("year-wise coverage (observed / expected within listed ranges):")
    for mk, years in payload["yearlyCoverage"].items():
        print(f"  {mk}")
        for yr, v in years.items():
            print(f"     {yr}  {v['observed']:>7,} / {v['expectedWithinListedRanges']:>7,}"
                  f"  = {v['coverage']:.4f}  instruments {v['instruments']:>3}"
                  f"  missing {v['missing']:>5,}")
    print("\nepisode counts by threshold:")
    for mk, b in inv.items():
        if "episodeCountByThreshold" in b:
            print(f"  {mk:<10} {b['benchmark'][:34]:<36} {b['episodeCountByThreshold']}")
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
