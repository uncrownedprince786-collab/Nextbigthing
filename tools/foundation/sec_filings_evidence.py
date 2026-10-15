"""Official filings for the events no press reference was recovered for.

    python tools/foundation/sec_filings_evidence.py [--days N] [--sleep S]

**Why this closes a real gap rather than papering over one.** Eighteen of the 168 verified events
ended without a press reference, and sixteen of them are US company earnings. For an earnings
event the press article was never the primary record anyway -- the company's **8-K** is. NVDA's
earnings event on 2021-02-24 has an 8-K filed by NVDA on 2021-02-24; that is the announcement
itself, not a report about it.

So this does not re-run the press search. It asks EDGAR, which has already been mapped for this
project, whether the registrant filed an earnings-bearing form within a few days of the event
date, and records the filing as **official evidence** with its accession number and document URL.
An event that gains one moves from `SEARCHED_NO_MATCH` to `OFFICIAL_SOURCE_ONLY`: better
evidence, and honestly labelled as a different kind of evidence. A filing is not a press article
and the disposition never pretends it is.

Only events that currently lack a press reference are looked at, so this cannot quietly replace
recovered journalism with a filing. Reads the cached ticker map and caches every submissions
response, so a re-run costs nothing.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent

CORPUS = ROOT / "data" / "foundation" / "events" / "events.json"
MANIFEST = ROOT / "data" / "foundation" / "events" / "press_evidence_manifest.json"
OUT = ROOT / "data" / "foundation" / "events" / "official_filings.json"
CACHE = ROOT / ".cache" / "foundation" / "sec"
TICKERS = CACHE / "company_tickers.json"

SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
DOCBASE = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc_nodash}/{doc}"
UA = "NextBigThing-research/1.0 (mailto:claude.pro@thedg.group)"

# Forms that carry an earnings announcement or the report behind it.
EARNINGS_FORMS = {"8-K", "10-Q", "10-K", "6-K", "20-F"}
WINDOW_DAYS = 3
SLEEP = 0.3

# Instruments that are markets rather than SEC registrants.
NOT_REGISTRANTS = {"MKT", "PSX", "OIL", "GOLD", "BTC", "ETH"}


def arg(name: str, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def get_json(url: str, key: str, sleep_s: float):
    CACHE.mkdir(parents=True, exist_ok=True)
    p = CACHE / f"{key}.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=60) as r:
            doc = json.loads(r.read())
        p.write_text(json.dumps(doc), encoding="utf-8")
        time.sleep(sleep_s)
        return doc
    except urllib.error.HTTPError as e:
        print(f"    HTTP {e.code} for {key}")
        return None
    except Exception as e:  # noqa: BLE001
        print(f"    {type(e).__name__} for {key}")
        return None


def main() -> int:
    days = int(arg("--days", WINDOW_DAYS))
    sleep_s = float(arg("--sleep", SLEEP))

    if not TICKERS.exists():
        print("EDGAR ticker map not cached; run sec_lifecycle.py first")
        return 1
    tmap = json.loads(TICKERS.read_text(encoding="utf-8"))
    by_ticker = {}
    for e in tmap.values():
        by_ticker.setdefault(e["ticker"].upper(), int(e["cik_str"]))

    corpus = {e["name"]: e for e in json.loads(CORPUS.read_text(encoding="utf-8"))["events"]
              if e.get("verified")}
    man = json.loads(MANIFEST.read_text(encoding="utf-8"))
    targets = [d for d in man["dispositions"] if d["pressReferences"] == 0]
    print(f"events without a press reference: {len(targets)}")

    found: dict[str, dict] = {}
    misses: list[dict] = []
    for d in targets:
        ins = (d.get("instrument") or "").upper()
        if not ins or ins in NOT_REGISTRANTS:
            misses.append({"name": d["name"], "date": d["date"],
                           "reason": f"instrument {ins or '(none)'} is not an SEC registrant"})
            continue
        cik = by_ticker.get(ins)
        if not cik:
            misses.append({"name": d["name"], "date": d["date"],
                           "reason": f"{ins} is not in EDGAR's live ticker map"})
            continue
        sub = get_json(SUBMISSIONS.format(cik=cik), f"sub_{cik}", sleep_s)
        if not sub:
            misses.append({"name": d["name"], "date": d["date"],
                           "reason": "submissions unavailable"})
            continue
        rec = sub.get("filings", {}).get("recent", {})
        when = date.fromisoformat(d["date"])
        best = None
        for form, fdate, acc, doc, items in zip(
                rec.get("form", []), rec.get("filingDate", []),
                rec.get("accessionNumber", []), rec.get("primaryDocument", []),
                rec.get("items", []) or [""] * len(rec.get("form", []))):
            if form not in EARNINGS_FORMS:
                continue
            try:
                fd = date.fromisoformat(fdate)
            except ValueError:
                continue
            gap = abs((fd - when).days)
            if gap > days:
                continue
            if best is None or gap < best["daysFromEvent"]:
                best = {"form": form, "filingDate": fdate, "accession": acc,
                        "daysFromEvent": gap, "items": items,
                        "url": DOCBASE.format(cik=cik, acc_nodash=acc.replace("-", ""), doc=doc)}
        if best:
            found[d["name"]] = {**best, "cik": cik, "ticker": ins,
                                "registrant": sub.get("name"),
                                "evidenceKind": "official filing by the registrant",
                                "retrievedAt": datetime.now(timezone.utc).isoformat(
                                    timespec="seconds")}
            print(f"  {d['date']} {ins:<6} {best['form']:<5} filed {best['filingDate']} "
                  f"(+{best['daysFromEvent']}d) {d['name'][:38]}")
        else:
            misses.append({"name": d["name"], "date": d["date"],
                           "reason": f"no {'/'.join(sorted(EARNINGS_FORMS))} within {days} days"})

    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "version": "official-filings-v1",
        "source": {"name": "SEC EDGAR submissions API", "auth": "none, contact UA required"},
        "scope": "only events that ended with zero press references; press findings untouched",
        "window": {"days": days, "forms": sorted(EARNINGS_FORMS)},
        "eventsExamined": len(targets),
        "eventsWithAnOfficialFiling": len(found),
        "eventsStillWithout": len(misses),
        "whyThisIsNotAPressArticle": ("an 8-K is the announcement itself, filed by the company. "
                                      "It is stronger evidence than a report about it and a "
                                      "different kind, so the disposition says OFFICIAL_SOURCE_ONLY"),
        "filings": found,
        "misses": misses,
    }
    OUT.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    print(f"\nofficial filings recovered: {len(found)} of {len(targets)}")
    print(f"still without evidence    : {len(misses)}")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
