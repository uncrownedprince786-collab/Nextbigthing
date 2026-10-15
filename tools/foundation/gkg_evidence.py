"""Historical press references from GDELT's bulk GKG archive, when the DOC API is rate-limited.

    python tools/foundation/gkg_evidence.py [--dates N] [--per-event K] [--keep-zip]

**Why a second route exists.** `gdelt_evidence.py` asks the DOC API one event at a time. That API
answers `429 Please limit requests to one every 5 seconds` and, once a host has tripped it, keeps
answering 429 well beyond five seconds -- measured here across spaced probes over ten minutes of
near-idle. The archive at `data.gdeltproject.org` is plain static files with no such limit, so the
same evidence is reachable by a different door. Neither route bypasses anything: one is an API
with a quota, the other is a published download.

**The shape of the archive, measured rather than assumed.** A v1 GKG daily file
(`http://data.gdeltproject.org/gkg/YYYYMMDD.gkg.csv.zip`) is about **31.6 MB** compressed, holds
roughly **77,000 rows**, and downloads in about nine seconds. Columns: DATE, NUMARTS, COUNTS,
THEMES, LOCATIONS, PERSONS, ORGANIZATIONS, TONE, CAMEOEVENTIDS, SOURCES, SOURCEURLS. A row is an
aggregation over one source for one day, and `SOURCEURLS` carries the article links.

The corpus needs **158 distinct dates**, so this is a targeted fetch of 158 named files, not a
mirror of the archive. Each file is streamed, filtered, reduced to the best `--per-event`
references and then **deleted**, so peak disk is one file rather than five gigabytes.

**Relevance is keyword matching, and it is reported as such.** An event's name supplies the terms;
a row matches when its themes, people, organisations, locations or article URL carry enough of
them. That finds references *about* the event; it does not prove the article says what the corpus
says. These are references, not verified quotations, and the disposition records which.

Caches one small JSON per date, so an interrupted run resumes and a completed date is never
re-fetched. Reads no database and writes no database row.
"""

from __future__ import annotations

import csv
import io
import json
import re
import sys
import urllib.error
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent

CORPUS = ROOT / "data" / "foundation" / "events" / "events.json"
CACHE = ROOT / ".cache" / "foundation" / "gkg"
TMP = CACHE / "_tmp"
BASE = "http://data.gdeltproject.org/gkg/{ymd}.gkg.csv.zip"
UA = "NextBigThing-research/1.0 (mailto:claude.pro@thedg.group)"

PER_EVENT = 12
# Words that match everything and therefore identify nothing.
STOP = {"the", "a", "an", "of", "in", "on", "to", "and", "for", "its", "is", "at", "by", "with",
        "from", "as", "after", "over", "into", "new", "first", "us", "u.s.", "says", "amid"}

csv.field_size_limit(10 ** 9)


def arg(name: str, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def terms(event: dict) -> list[str]:
    """The words that make this event itself rather than its topic."""
    raw = re.split(r"[^A-Za-z0-9.]+", event.get("name", ""))
    out = [w.lower() for w in raw if len(w) > 2 and w.lower() not in STOP]
    ins = (event.get("instrument") or "").lower()
    if ins and ins not in ("mkt", "psx") and ins not in out:
        out.append(ins)
    return out[:8]


def score(row: dict, words: list[str], url: str) -> tuple[int, int]:
    """`(terms in the article URL, terms anywhere in the row)`.

    The two are kept apart because they are not equally good evidence. A news URL carries a
    slug -- `/trump-issuing-order-to-ground-all-max-jets/` -- so a term found there is a term the
    headline itself used. A term found only in GKG's themes or locations says the row is about
    that *topic*, which a Hawaii legislature story can be while matching "attack" and "india".
    Requiring the URL to carry the event's words is what separates a reference from a coincidence.
    """
    meta = " ".join((row.get(c) or "") for c in
                    ("THEMES", "LOCATIONS", "PERSONS", "ORGANIZATIONS")).lower()
    u = url.lower()
    return sum(1 for w in words if w in u), sum(1 for w in words if w in u or w in meta)


def fetch_day(ymd: str, keep: bool) -> Path | None:
    TMP.mkdir(parents=True, exist_ok=True)
    dest = TMP / f"{ymd}.zip"
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    try:
        req = urllib.request.Request(BASE.format(ymd=ymd), headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=300) as r:
            dest.write_bytes(r.read())
        return dest
    except urllib.error.HTTPError as e:
        print(f"    {ymd}: HTTP {e.code}")
        return None
    except Exception as e:  # noqa: BLE001
        print(f"    {ymd}: {type(e).__name__}")
        return None


def main() -> int:
    doc = json.loads(CORPUS.read_text(encoding="utf-8"))
    events = [e for e in doc.get("events", []) if e.get("verified")]
    per_event = int(arg("--per-event", PER_EVENT))
    keep = "--keep-zip" in sys.argv

    by_date: dict[str, list[dict]] = {}
    for e in events:
        by_date.setdefault(e["date"], []).append(e)
    dates = sorted(by_date)
    limit = int(arg("--dates", 0)) or None
    if limit:
        dates = dates[:limit]
    CACHE.mkdir(parents=True, exist_ok=True)

    print(f"corpus dates: {len(by_date)}  processing: {len(dates)}  per-event cap: {per_event}")
    done = skipped = 0
    for i, d in enumerate(dates, 1):
        ymd = d.replace("-", "")
        out = CACHE / f"{ymd}.json"
        if out.exists():
            skipped += 1
            continue
        z = fetch_day(ymd, keep)
        if z is None:
            out.write_text(json.dumps({"date": d, "note": "archive unavailable", "events": {}}),
                           encoding="utf-8")
            continue
        found: dict[str, list[dict]] = {}
        try:
            with zipfile.ZipFile(z) as zf:
                name = zf.namelist()[0]
                with zf.open(name) as fh:
                    rd = csv.DictReader(io.TextIOWrapper(fh, encoding="utf-8", errors="replace"),
                                        delimiter="\t")
                    best: dict[str, list[tuple]] = {e["name"]: [] for e in by_date[d]}
                    words = {e["name"]: terms(e) for e in by_date[d]}
                    for row in rd:
                        urls = [u for u in (row.get("SOURCEURLS") or "").split("<UDIV>") if u]
                        if not urls:
                            continue
                        for ev in by_date[d]:
                            w = words[ev["name"]]
                            if len(w) < 2:
                                continue
                            in_url, total = score(row, w, urls[0])
                            # Two of the event's own words in the article URL, or most of them
                            # across the row with at least one in the URL. Anything looser
                            # collects stories that merely share a topic.
                            keep_it = in_url >= 2 or (in_url >= 1 and total >= max(3, len(w) - 1))
                            if not keep_it:
                                continue
                            best[ev["name"]].append(
                                (in_url * 10 + total, int(row.get("NUMARTS") or 0),
                                 (row.get("SOURCES") or "").split(";")[0], urls[0], in_url, total))
                    for k, v in best.items():
                        v.sort(key=lambda t: (-t[0], -t[1]))
                        found[k] = [{"rank": s, "numArts": n, "publisher": src,
                                     "url": u, "termsInUrl": iu, "termsTotal": tt}
                                    for s, n, src, u, iu, tt in v[:per_event]]
        except Exception as e:  # noqa: BLE001
            found = {}
            print(f"    {ymd}: parse failed {type(e).__name__}")
        out.write_text(json.dumps({"date": d, "note": "ok", "events": found}), encoding="utf-8")
        if not keep:
            z.unlink(missing_ok=True)
        hits = sum(len(v) for v in found.values())
        done += 1
        print(f"  {i:>3}/{len(dates)} {d} -> {hits:>3} references across "
              f"{len(by_date[d])} event(s)", flush=True)

    print(f"\ndates processed this run: {done}  already cached: {skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
