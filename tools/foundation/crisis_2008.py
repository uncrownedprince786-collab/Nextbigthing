"""The 2008 Global Financial Crisis research package: macro, banking stress and a chronology.

    python tools/foundation/crisis_2008.py [--start 2005-01-01] [--end 2012-12-31]

Writes `data/foundation/crisis_2008/` -- one CSV per series, a bank-failure table, a dated
chronology and a manifest with per-file checksums. Free public sources only, no key, no login.

**What this is and is not.** It is a *research* package: the structured evidence needed to study
the crisis. It is **not** training data. `examples-v3` begins in 2018 and holds no instrument-level
bar before it, so nothing here can be a feature for the first task. The manifest says so on every
series, because a 2008 file sitting next to a 2018 dataset is exactly the kind of thing that later
gets mistaken for coverage.

**Three kinds of evidence, kept apart.**

  *market* -- already held in `data/foundation/benchmarks/`: `^GSPC` to 1927, `DGS10` to 1962,
  `DFF` to 1954, `DCOILWTICO` to 1986, `^VIX` to 1990. Not re-downloaded; referenced.

  *macro and banking stress* -- fetched here from FRED for the crisis window: unemployment,
  payrolls, claims, GDP, inflation, housing starts and permits, Case-Shiller house prices,
  mortgage delinquency, the TED spread, the Fed balance sheet, the yield curve and policy rates.
  Each carries its publication lag, so the series can later be made point-in-time rather than
  being quietly joined on observation date.

  *banking failures* -- the FDIC's own failure and assistance records for the window, with the
  institution, date, city and assets at failure.

**The chronology is dated by what the date means.** Every entry records whether its date is an
announcement, an effective date, a filing or a later retrospective description, with a link to an
official document. A retrospective description is evidence about the event and not evidence of
what was knowable on the day, and the two must never be read as the same thing.

**Known licensing gap, recorded rather than worked around.** FRED serves the ICE BofA credit
spreads (`BAMLH0A0HYM2`, `BAMLC0A0CM`) on a rolling three-year window only, so the 2008 credit
spread is not publicly available through it. The TED spread is fetched instead as the closest
freely available liquidity-stress measure, and the gap is reported.
"""

from __future__ import annotations

import csv
import hashlib
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
OUT = ROOT / "data" / "foundation" / "crisis_2008"
CACHE = ROOT / ".cache" / "foundation" / "crisis2008"

FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}&cosd={start}&coed={end}"
FDIC = ("https://banks.data.fdic.gov/api/failures?filters=FAILYR:%5B{a}%20TO%20{b}%5D"
        "&fields=NAME,CITYST,FAILDATE,FAILYR,QBFASSET,COST,RESTYPE,CHCLASS1&limit=2000&format=json")
UA = "NextBigThing-research/1.0 (mailto:claude.pro@thedg.group)"

# (id, title, frequency, publication lag in days, what it measures)
SERIES = [
    ("UNRATE", "Unemployment rate", "M", 7, "labour"),
    ("PAYEMS", "Nonfarm payrolls", "M", 7, "labour"),
    ("ICSA", "Initial jobless claims", "W", 5, "labour"),
    ("GDPC1", "Real GDP", "Q", 30, "activity"),
    ("INDPRO", "Industrial production", "M", 16, "activity"),
    ("CPIAUCSL", "CPI, all items", "M", 13, "inflation"),
    ("HOUST", "Housing starts", "M", 18, "housing"),
    ("PERMIT", "Building permits", "M", 18, "housing"),
    ("CSUSHPINSA", "Case-Shiller national home price index", "M", 60, "housing"),
    ("MORTGAGE30US", "30-year mortgage rate", "W", 1, "housing"),
    ("DRSFRMACBS", "Delinquency rate, single-family residential mortgages", "Q", 60, "credit"),
    ("TEDRATE", "TED spread", "D", 1, "credit and liquidity stress"),
    ("WALCL", "Federal Reserve total assets", "W", 1, "policy"),
    ("FEDFUNDS", "Effective federal funds rate, monthly", "M", 1, "policy"),
    ("DGS2", "2-year Treasury yield", "D", 1, "rates"),
    ("T10Y2Y", "10-year minus 2-year Treasury spread", "D", 1, "rates"),
    ("UMCSENT", "U Michigan consumer sentiment", "M", 1, "sentiment"),
    ("USREC", "NBER recession indicator", "M", None, "ex-post label"),
]

# Not obtainable for this window, and why.
BLOCKED = {
    "BAMLH0A0HYM2": "ICE licensing limits FRED to a rolling three-year window; the 2008 "
                    "high-yield spread is not publicly served. TEDRATE is used as the "
                    "freely available liquidity-stress measure instead.",
    "BAMLC0A0CM": "same ICE licensing limit for the investment-grade spread.",
}

# Dated chronology. `dateMeans` is the point: an announcement, an effective date, a filing and a
# later description are four different claims about time.
CHRONOLOGY = [
    ("2007-02-27", "Freddie Mac announces it will stop buying the riskiest subprime mortgages",
     "announcement", "https://www.federalreservehistory.org/essays/subprime-mortgage-crisis"),
    ("2007-08-09", "BNP Paribas suspends redemptions on three funds, citing an inability to value "
     "US subprime assets", "announcement",
     "https://www.federalreservehistory.org/essays/bnp-paribas-freezes-funds"),
    ("2007-09-18", "FOMC cuts the federal funds target by 50bp to 4.75%", "effective",
     "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"),
    ("2008-03-16", "JPMorgan Chase agrees to acquire Bear Stearns with Federal Reserve support",
     "announcement", "https://www.federalreservehistory.org/essays/bear-stearns-rescue"),
    ("2008-09-07", "FHFA places Fannie Mae and Freddie Mac into conservatorship", "effective",
     "https://www.fhfa.gov/conservatorship"),
    ("2008-09-15", "Lehman Brothers Holdings files for Chapter 11 bankruptcy", "filing",
     "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0000806085"),
    ("2008-09-16", "The Federal Reserve authorises lending to AIG", "announcement",
     "https://www.federalreservehistory.org/essays/aig-rescue"),
    ("2008-09-29", "The US House rejects the initial TARP legislation; the S&P 500 falls sharply",
     "announcement", "https://www.govinfo.gov/features/financial-crisis-inquiry-report"),
    ("2008-10-03", "The Emergency Economic Stabilization Act, creating TARP, is signed",
     "effective", "https://www.govinfo.gov/app/details/PLAW-110publ343"),
    ("2008-10-08", "Coordinated international central-bank rate cuts", "effective",
     "https://www.federalreserve.gov/newsevents/pressreleases/monetary20081008a.htm"),
    ("2008-12-16", "FOMC cuts the target to a 0-0.25% range and signals quantitative easing",
     "effective", "https://www.federalreserve.gov/newsevents/pressreleases/monetary20081216b.htm"),
    ("2009-03-09", "The S&P 500 closes at its cycle low of 676.53", "market observation",
     "data/foundation/benchmarks/GSPC.csv.gz"),
    ("2011-01-27", "The Financial Crisis Inquiry Commission delivers its final report",
     "retrospective description", "https://www.govinfo.gov/features/financial-crisis-inquiry-report"),
]


def arg(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def get(url: str, key: str) -> bytes | None:
    CACHE.mkdir(parents=True, exist_ok=True)
    p = CACHE / key
    if p.exists() and p.stat().st_size > 0:
        return p.read_bytes()
    for attempt in range(1, 4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=120) as r:
                body = r.read()
            p.write_bytes(body)
            time.sleep(0.4)
            return body
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            time.sleep(2 * attempt)
        except Exception:  # noqa: BLE001
            time.sleep(2 * attempt)
    return None


def main() -> int:
    start = arg("--start", "2005-01-01")
    end = arg("--end", "2012-12-31")
    OUT.mkdir(parents=True, exist_ok=True)

    files: dict[str, dict] = {}
    print(f"crisis window {start} .. {end}")
    for sid, title, freq, lag, what in SERIES:
        body = get(FRED.format(sid=sid, start=start, end=end), f"{sid}.csv")
        if not body:
            files[sid] = {"status": "FETCH_FAILED", "title": title}
            print(f"  {sid:<14} FAILED")
            continue
        text = body.decode("utf-8", "replace")
        lines = [ln for ln in text.splitlines() if ln.strip()]
        rows = [ln.split(",") for ln in lines[1:]]
        kept = [(r[0], r[1]) for r in rows if len(r) >= 2 and r[1] not in (".", "")]
        path = OUT / f"{sid}.csv"
        with path.open("w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["observation_date", "value"])
            w.writerows(kept)
        files[sid] = {
            "status": "COMPLETE" if kept else "EMPTY",
            "title": title, "frequency": freq, "measures": what,
            "publicationLagDays": lag,
            "rows": len(kept),
            "first": kept[0][0] if kept else None, "last": kept[-1][0] if kept else None,
            "url": FRED.format(sid=sid, start=start, end=end),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "pointInTimeReady": lag is not None,
            "pitNote": ("join on observation_date + publicationLagDays, never on observation_date "
                        "alone" if lag is not None else
                        "ex-post label: declared long after the fact, must never be a feature"),
        }
        print(f"  {sid:<14} {len(kept):>5} rows  {kept[0][0] if kept else '-'} .. "
              f"{kept[-1][0] if kept else '-'}")

    # FDIC bank failures and assistance for the window.
    body = get(FDIC.format(a=start[:4], b=end[:4]), "fdic_failures.json")
    fdic_rows = []
    if body:
        doc = json.loads(body)
        for x in doc.get("data", []):
            r = x.get("data", x)
            fdic_rows.append({
                "name": r.get("NAME"), "cityState": r.get("CITYST"),
                "failDate": r.get("FAILDATE"), "year": r.get("FAILYR"),
                "assetsAtFailureThousands": r.get("QBFASSET"),
                "estimatedCostThousands": r.get("COST"),
                "resolutionType": r.get("RESTYPE"), "charterClass": r.get("CHCLASS1"),
            })
    fp = OUT / "fdic_failures.json"
    fp.write_text(json.dumps({
        "source": "FDIC BankFind failures and assistance",
        "url": "https://banks.data.fdic.gov/bankfind-suite/failures",
        "api": FDIC.format(a=start[:4], b=end[:4]),
        "window": [start[:4], end[:4]],
        "records": len(fdic_rows), "failures": fdic_rows,
    }, indent=1), encoding="utf-8")

    cp = OUT / "chronology.json"
    cp.write_text(json.dumps({
        "note": ("every entry records what its date means. An announcement, an effective date, a "
                 "filing and a later retrospective description are four different claims about "
                 "time, and only the first three were knowable on the day"),
        "entries": [{"date": d, "event": e, "dateMeans": k, "source": u}
                    for d, e, k, u in CHRONOLOGY],
    }, indent=1), encoding="utf-8")

    manifest = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "version": "crisis-2008-v1",
        "window": [start, end],
        "purpose": "research evidence for the 2008 crisis; NOT training data",
        "trainingStatus": ("examples-v3 begins 2018-01-01 and holds no instrument bar before it, "
                           "so no series here can be a feature for the first task"),
        "marketSeriesAlreadyHeld": {
            "location": "data/foundation/benchmarks/",
            "covering": {"^GSPC": "1927", "DGS10": "1962", "DFF": "1954", "DCOILWTICO": "1986",
                         "^VIX": "1990", "DX-Y.NYB": "1971"},
            "note": "referenced, not re-downloaded",
        },
        "macroAndBankingSeries": files,
        "bankFailures": {"status": "COMPLETE" if fdic_rows else "FETCH_FAILED",
                         "records": len(fdic_rows), "file": fp.name,
                         "sha256": hashlib.sha256(fp.read_bytes()).hexdigest()},
        "chronology": {"entries": len(CHRONOLOGY), "file": cp.name,
                       "sha256": hashlib.sha256(cp.read_bytes()).hexdigest()},
        "licenseBlocked": BLOCKED,
        "psxNote": "PSX 2008 coverage is investigated separately; US index history is not "
                   "evidence about Pakistani market coverage",
    }
    mp = OUT / "manifest.json"
    mp.write_text(json.dumps(manifest, indent=1), encoding="utf-8")

    ok = sum(1 for v in files.values() if v.get("status") == "COMPLETE")
    print(f"\nseries complete : {ok} of {len(SERIES)}")
    print(f"bank failures   : {len(fdic_rows)}")
    print(f"chronology      : {len(CHRONOLOGY)} dated entries")
    print(f"license blocked : {len(BLOCKED)}")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
