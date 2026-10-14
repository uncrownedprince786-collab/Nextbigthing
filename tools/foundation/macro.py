"""Macroeconomic series with an explicit availability time, from FRED and ALFRED (no key).

    python tools/foundation/macro.py history            # every series, latest values
    python tools/foundation/macro.py vintages [SERIES]  # ALFRED snapshots, resumable
    python tools/foundation/macro.py report             # what the dataset does and does not cover

Why the availability column exists
----------------------------------
A macro value belongs to the period it measures, but a decision on that date can only use what had
been published. Every row therefore carries `availableAt`: the earliest date a value for that
period could have been known. Two kinds, kept apart and labelled:

* `lag` -- a fixed, deliberately conservative publication lag after the period ends (the real
  release is usually earlier, never later). Safe against look-ahead; says nothing about revisions.
* `vintage` -- the first ALFRED snapshot in which the observation appeared, with every later
  revision of its value. Snapshots are taken twice a month, so the date is an upper bound on the
  real release (at most ~14 days late), again the safe direction.

`USREC` is the NBER recession flag, declared months after the fact. It is stored as an ex-post
label and carries no `availableAt`; using it as a feature would be look-ahead by construction.

Everything is public statistical data. Nothing here touches a database.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
OUT = ROOT / "data" / "foundation" / "macro"
UA = "NextBigThing-research/1.0 (contact claude.pro@thedg.group)"
START = "2010-01-01"

# id, title, frequency, kind of lag, lag in days after the period end, tracked for revisions
# freq: D daily, W weekly, M monthly, Q quarterly
SERIES = [
    ("DGS10", "10-year Treasury yield", "D", "lag", 1, False),
    ("DGS2", "2-year Treasury yield", "D", "lag", 1, False),
    ("DGS3MO", "3-month Treasury yield", "D", "lag", 1, False),
    ("T10Y2Y", "10y minus 2y Treasury spread", "D", "lag", 1, False),
    ("T10Y3M", "10y minus 3m Treasury spread", "D", "lag", 1, False),
    ("DFF", "Effective federal funds rate", "D", "lag", 1, False),
    ("T10YIE", "10-year breakeven inflation", "D", "lag", 1, False),
    ("VIXCLS", "CBOE volatility index", "D", "lag", 1, False),
    ("DCOILWTICO", "WTI crude oil spot", "D", "lag", 8, False),
    ("DTWEXBGS", "Broad trade-weighted dollar index", "D", "lag", 7, False),
    ("DEXUSEU", "USD per EUR", "D", "lag", 7, False),
    ("DEXJPUS", "JPY per USD", "D", "lag", 7, False),
    ("MORTGAGE30US", "30-year mortgage rate (Freddie Mac)", "W", "lag", 1, False),
    ("WALCL", "Federal Reserve total assets", "W", "lag", 1, False),
    ("ICSA", "Initial jobless claims", "W", "lag", 5, False),
    ("NFCI", "Chicago Fed financial conditions index", "W", "lag", 5, True),
    ("CPIAUCSL", "CPI all items", "M", "lag", 16, True),
    ("CPILFESL", "CPI ex food and energy", "M", "lag", 16, False),
    ("PCEPILFE", "PCE price index ex food and energy", "M", "lag", 31, True),
    ("PPIACO", "PPI all commodities", "M", "lag", 16, False),
    ("UNRATE", "Unemployment rate", "M", "lag", 10, True),
    ("PAYEMS", "Nonfarm payrolls", "M", "lag", 10, True),
    ("INDPRO", "Industrial production", "M", "lag", 18, True),
    ("RSAFS", "Advance retail sales", "M", "lag", 17, True),
    ("HOUST", "Housing starts", "M", "lag", 20, True),
    ("PERMIT", "Building permits", "M", "lag", 20, False),
    ("UMCSENT", "U Michigan consumer sentiment", "M", "lag", 31, False),
    ("M2SL", "M2 money stock", "M", "lag", 25, True),
    ("CFNAI", "Chicago Fed national activity index", "M", "lag", 30, False),
    ("TCU", "Capacity utilisation", "M", "lag", 18, False),
    ("GDPC1", "Real GDP", "Q", "lag", 30, True),
    ("USREC", "NBER recession indicator (ex-post label)", "M", "none", 0, False),
]
# Public series that exist but are shorter than 15 years, kept out of the count and reported.
SHORT = {"BAMLH0A0HYM2": "ICE BofA high-yield spread", "BAMLC0A0CM": "ICE BofA investment-grade spread"}


def get(url: str, tries: int = 4) -> bytes:
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=40) as r:
                return r.read()
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            if i == tries - 1:
                raise
            time.sleep(2 * (i + 1))
    raise RuntimeError("unreachable")


def period_end(freq: str, d: date) -> date:
    """The last day of the period an observation dated `d` describes."""
    if freq in ("D", "W"):
        return d
    if freq == "M":
        nxt = date(d.year + (d.month == 12), d.month % 12 + 1, 1)
        return nxt - timedelta(days=1)
    q_end_month = ((d.month - 1) // 3 + 1) * 3
    nxt = date(d.year + (q_end_month == 12), q_end_month % 12 + 1, 1)
    return nxt - timedelta(days=1)


def history() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = {"retrievedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "source": "https://fred.stlouisfed.org/graph/fredgraph.csv", "series": {}}
    for sid, title, freq, kind, lag, tracked in SERIES:
        url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}&cosd={START}"
        raw = get(url)
        rows = list(csv.reader(io.StringIO(raw.decode("utf-8"))))
        head, body = rows[0], rows[1:]
        out = []
        for d, v in body:
            if v in ("", "."):
                continue
            od = date.fromisoformat(d)
            avail = "" if kind == "none" else (period_end(freq, od) + timedelta(days=lag)).isoformat()
            out.append((d, v, avail))
        with open(OUT / f"{sid}.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["observation_date", "value", "availableAt"])
            w.writerows(out)
        manifest["series"][sid] = {
            "title": title, "frequency": freq, "availability": kind if kind == "none" else f"lag+{lag}d",
            "revisionTracked": tracked, "rows": len(out), "first": out[0][0], "last": out[-1][0],
            "sha256": hashlib.sha256(raw).hexdigest(), "url": url,
        }
        print(f"{sid:14} {len(out):5} rows {out[0][0]} .. {out[-1][0]}")
        time.sleep(0.4)
    for sid, title in SHORT.items():
        raw = get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}&cosd={START}")
        rows = [r for r in csv.reader(io.StringIO(raw.decode()))][1:]
        rows = [r for r in rows if r[1] not in ("", ".")]
        manifest.setdefault("shorterThan15Years", {})[sid] = {
            "title": title, "rows": len(rows), "first": rows[0][0], "last": rows[-1][0],
            "reason": "ICE licensing limits FRED to a rolling three years"}
        time.sleep(0.4)
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")


def grid(first: date, last: date) -> list[date]:
    """Two snapshots a month, on the 14th and the 28th."""
    out, y, m = [], first.year, first.month
    while date(y, m, 1) <= last:
        for dd in (14, 28):
            d = date(y, m, dd)
            if first <= d <= last:
                out.append(d)
        y, m = y + (m == 12), m % 12 + 1
    return out


def vintages(only: str | None = None) -> None:
    vdir = OUT / "vintages"
    vdir.mkdir(parents=True, exist_ok=True)
    today = date.today()
    for sid, title, freq, kind, lag, tracked in SERIES:
        if not tracked or (only and sid != only):
            continue
        state_path = vdir / f"{sid}.state.json"
        state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {
            "done": [], "obs": {}, "errors": []}
        done = set(state["done"])
        todo = [d for d in grid(date(2010, 2, 14), today - timedelta(days=1)) if d.isoformat() not in done]
        print(f"{sid}: {len(done)} snapshots done, {len(todo)} to go", flush=True)
        for n, d in enumerate(todo, 1):
            url = (f"https://alfred.stlouisfed.org/graph/alfredgraph.csv?id={sid}"
                   f"&cosd={START}&vintage_date={d.isoformat()}")
            try:
                rows = list(csv.reader(io.StringIO(get(url).decode("utf-8"))))[1:]
            except Exception as e:  # noqa: BLE001
                state["errors"].append({"vintage": d.isoformat(), "error": type(e).__name__})
                continue
            for od, v in rows:
                if v in ("", "."):
                    continue
                hist = state["obs"].setdefault(od, [])
                if not hist or hist[-1][1] != v:
                    hist.append([d.isoformat(), v])
            state["done"].append(d.isoformat())
            if n % 25 == 0:
                state_path.write_text(json.dumps(state), encoding="utf-8")
                print(f"  {sid} {n}/{len(todo)} (to {d})", flush=True)
            time.sleep(0.5)
        state_path.write_text(json.dumps(state), encoding="utf-8")
        with open(vdir / f"{sid}.jsonl", "w", encoding="utf-8") as f:
            for od in sorted(state["obs"]):
                h = state["obs"][od]
                f.write(json.dumps({"obs": od, "firstSeen": h[0][0], "firstValue": h[0][1],
                                    "latestValue": h[-1][1], "revisions": len(h) - 1,
                                    "history": h}) + "\n")
        print(f"{sid}: wrote {len(state['obs'])} observations, {len(state['errors'])} failed snapshots", flush=True)


def report() -> None:
    m = json.loads((OUT / "manifest.json").read_text(encoding="utf-8"))
    full = {k: v for k, v in m["series"].items()}
    fifteen = [k for k, v in full.items()
               if (date.fromisoformat(v["last"]) - date.fromisoformat(v["first"])).days >= 15 * 365]
    vint = {p.stem: sum(1 for _ in open(p, encoding="utf-8")) for p in (OUT / "vintages").glob("*.jsonl")}
    print(f"series with data: {len(full)}; with at least 15 years: {len(fifteen)}")
    print(f"revision-tracked with vintage files: {sorted(vint)}")
    print("shorter than 15y:", m.get("shorterThan15Years", {}))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "history"
    {"history": history, "report": report}.get(cmd, lambda: vintages(sys.argv[2] if len(sys.argv) > 2 else None))()
