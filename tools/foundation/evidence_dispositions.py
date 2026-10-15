"""One honest disposition per event, merged from every evidence route that was tried.

    python tools/foundation/evidence_dispositions.py

Writes `data/foundation/events/press_evidence.jsonl` (the references) and
`press_evidence_manifest.json` (the dispositions and the search record). Idempotent: it reads only
the caches the collectors wrote, so running it twice produces the same artifact.

**Every event ends in exactly one state**, and the states are about *what was searched*, never
about what exists in the world:

  `PRESS_EVIDENCE_FOUND`  at least one dated, relevant press reference was recovered and linked.
  `OFFICIAL_SOURCE_ONLY`  the corpus verified this event against a primary source -- a Wikipedia
                          article with the date in its body, a Wikidata claim, an official
                          document -- but no press reference was recovered.
  `SEARCHED_NO_MATCH`     the searches ran to completion and returned nothing relevant. This is a
                          fact about the searches, with their scope recorded, and not a claim
                          that no article was ever published.
  `SOURCE_LIMITED`        a named access limit stopped the search: the DOC API's rate limit, or
                          an archive file the server does not hold for that date.
  `PENDING`               a concrete acquisition step is still outstanding. The acquisition is not
                          closed while any event is here.

**Two routes, recorded separately.** `gdelt_evidence.py` queries the DOC API; `gkg_evidence.py`
reads the bulk GKG archive. They have different failure modes -- the API rate-limits, the archive
occasionally lacks a day -- so the manifest keeps each route's outcome per event rather than
merging them into one unexplained number.

A reference is a reference. Nothing here fetches article text, so no record claims the page was
read, and `accessStatus` says exactly that.
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent

CORPUS = ROOT / "data" / "foundation" / "events" / "events.json"
DOC_CACHE = ROOT / ".cache" / "foundation" / "gdelt"
GKG_CACHE = ROOT / ".cache" / "foundation" / "gkg"
OUT_DIR = ROOT / "data" / "foundation" / "events"
FILINGS = OUT_DIR / "official_filings.json"

FOUND = "PRESS_EVIDENCE_FOUND"
OFFICIAL = "OFFICIAL_SOURCE_ONLY"
NO_MATCH = "SEARCHED_NO_MATCH"
LIMITED = "SOURCE_LIMITED"
PENDING = "PENDING"


def cached_at(path: Path) -> str:
    """When this evidence was collected, taken from its checkpoint file.

    Not `now`: a rebuild of the artifact is not a retrieval, and stamping it as one would change
    every record's timestamp -- and so the file's checksum -- on every run, which makes the
    artifact impossible to pin.
    """
    return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(
        timespec="seconds")


def event_id(e: dict) -> str:
    return hashlib.sha256(f"{e['date']}|{e['name']}".encode()).hexdigest()[:16]


def official_evidence(e: dict) -> dict | None:
    """What the corpus already verified this event against, if anything."""
    w = e.get("wikipedia") or {}
    off = [o for o in (e.get("official") or []) if isinstance(o, dict) and o.get("dateInDocument")]
    wd = e.get("wikidata") or {}
    if off:
        return {"kind": "official document", "url": off[0].get("url"),
                "sha256": off[0].get("sha256")}
    if w.get("url"):
        return {"kind": "encyclopedia article with the date in its body", "url": w.get("url"),
                "revid": w.get("revid"), "textSha256": w.get("textSha256")}
    if wd.get("match"):
        return {"kind": "structured date claim", "properties": wd.get("properties")}
    return None


def main() -> int:
    doc = json.loads(CORPUS.read_text(encoding="utf-8"))
    events = [e for e in doc.get("events", []) if e.get("verified")]
    events.sort(key=lambda e: e["date"])

    # Route 1: the DOC API cache, keyed by the same slug the collector used.
    doc_by_event: dict[str, dict] = {}
    doc_when: dict[str, str] = {}
    for e in events:
        p = DOC_CACHE / f"{event_id(e)}.json"
        if p.exists():
            doc_by_event[e["name"]] = json.loads(p.read_text(encoding="utf-8"))
            doc_when[e["name"]] = cached_at(p)

    # Route 2: the GKG archive cache, keyed by date.
    gkg_by_date: dict[str, dict] = {}
    gkg_when: dict[str, str] = {}
    for p in sorted(GKG_CACHE.glob("*.json")):
        blob = json.loads(p.read_text(encoding="utf-8"))
        if blob.get("date"):
            gkg_by_date[blob["date"]] = blob
            gkg_when[blob["date"]] = cached_at(p)

    # Official filings recovered for events that ended with no press reference. An 8-K filed by
    # the registrant on the earnings date is the announcement itself, so it upgrades the
    # disposition -- to OFFICIAL_SOURCE_ONLY, never to PRESS_EVIDENCE_FOUND.
    filings = {}
    if FILINGS.exists():
        filings = json.loads(FILINGS.read_text(encoding="utf-8")).get("filings", {})

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    records: dict[str, dict] = {}
    dispositions: list[dict] = []

    for e in events:
        eid = event_id(e)
        refs: list[dict] = []
        routes: dict[str, str] = {}

        d = doc_by_event.get(e["name"])
        if d is None:
            routes["gdeltDocApi"] = "not attempted"
        elif d.get("note") == "ok":
            routes["gdeltDocApi"] = f"searched, {len(d.get('articles', []))} returned"
            for a in d.get("articles", []):
                if not a.get("url"):
                    continue
                key = hashlib.sha256(
                    f"{a.get('domain','')}|{(a.get('title') or '').lower()}|"
                    f"{(a.get('seendate') or '')[:8]}".encode()).hexdigest()[:20]
                refs.append({"dedupeKey": key, "route": "gdelt-doc-api",
                             "publisher": a.get("domain"), "title": (a.get("title") or "").strip(),
                             "url": a["url"], "publishedAt": a.get("seendate"),
                             "language": a.get("language"),
                             "sourceCountry": a.get("sourcecountry")})
        else:
            routes["gdeltDocApi"] = f"blocked: {d.get('note')}"

        g = gkg_by_date.get(e["date"])
        if g is None:
            routes["gdeltGkgArchive"] = "not attempted"
        elif g.get("note") != "ok":
            routes["gdeltGkgArchive"] = f"unavailable: {g.get('note')}"
        else:
            hits = g.get("events", {}).get(e["name"], [])
            routes["gdeltGkgArchive"] = f"searched, {len(hits)} matched"
            for h in hits:
                key = hashlib.sha256(
                    f"{h.get('publisher','')}|{h.get('url','')}".encode()).hexdigest()[:20]
                refs.append({"dedupeKey": key, "route": "gdelt-gkg-archive",
                             "publisher": h.get("publisher"), "title": None,
                             "url": h.get("url"), "publishedAt": e["date"],
                             "termsInUrl": h.get("termsInUrl"),
                             "articlesBehindRow": h.get("numArts")})

        seen: set[str] = set()
        kept = []
        for r in refs:
            if r["dedupeKey"] in seen:
                continue
            seen.add(r["dedupeKey"])
            kept.append(r)

        off = official_evidence(e)
        filed = filings.get(e["name"])
        if filed:
            routes["secEdgarFilings"] = (f"{filed['form']} filed {filed['filingDate']} "
                                         f"(+{filed['daysFromEvent']}d)")
            off = {"kind": f"official filing ({filed['form']}) by the registrant",
                   "url": filed["url"], "accession": filed["accession"],
                   "filingDate": filed["filingDate"], "registrant": filed.get("registrant")}
        if kept:
            state = FOUND
        elif any(v.startswith("blocked") or v.startswith("unavailable")
                 for v in routes.values()):
            state = LIMITED
        elif filed:
            state = OFFICIAL
        elif all(v == "not attempted" for v in routes.values()):
            state = PENDING
        elif off:
            state = OFFICIAL
        else:
            state = NO_MATCH

        for r in kept:
            when = (doc_when.get(e["name"]) if r["route"] == "gdelt-doc-api"
                    else gkg_when.get(e["date"])) or now
            rec = {"eventId": eid, "eventName": e["name"], "eventDate": e["date"],
                   "eventCategory": e.get("category"), "instrument": e.get("instrument"),
                   "retrievedAt": when,
                   "accessStatus": "reference only; article text was not fetched", **r}
            records.setdefault(f"{eid}|{r['dedupeKey']}", rec)

        dispositions.append({
            "eventId": eid, "name": e["name"], "date": e["date"],
            "category": e.get("category"), "instrument": e.get("instrument"),
            "tier": e.get("tier"), "disposition": state,
            "pressReferences": len(kept),
            "independentPublishers": len({r.get("publisher") for r in kept if r.get("publisher")}),
            "routes": routes,
            "officialEvidence": off,
        })

    out = OUT_DIR / "press_evidence.jsonl"
    with out.open("w", encoding="utf-8") as fh:
        for r in sorted(records.values(), key=lambda x: (x["eventDate"], x["publisher"] or "")):
            fh.write(json.dumps(r, separators=(",", ":")) + "\n")
    digest = hashlib.sha256(out.read_bytes()).hexdigest()

    counts: dict[str, int] = {}
    for d_ in dispositions:
        counts[d_["disposition"]] = counts.get(d_["disposition"], 0) + 1

    manifest = {
        "generatedAt": now,
        "version": "press-evidence-v2",
        "events": len(events),
        "dispositionCounts": counts,
        "pressReferenceRecords": len(records),
        "eventsWithPressEvidence": counts.get(FOUND, 0),
        "distinctPublishers": len({r.get("publisher") for r in records.values()
                                   if r.get("publisher")}),
        "routes": {
            "gdeltDocApi": {"endpoint": "https://api.gdeltproject.org/api/v2/doc/doc",
                            "limit": "one request per 5 seconds, stated in its own 429 body",
                            "note": "host entered a persistent penalty window; see "
                                    ".cache/foundation/gdelt_requests.log"},
            "gdeltGkgArchive": {"endpoint": "http://data.gdeltproject.org/gkg/YYYYMMDD.gkg.csv.zip",
                                "perFileBytes": 31639392,
                                "note": "static files, no rate limit; one file per corpus date, "
                                        "streamed, filtered and deleted"},
        },
        "relevanceRule": ("two of the event's own words in the article URL, or one in the URL and "
                          "most across the row's themes, people, organisations and locations"),
        "whatAReferenceIs": ("a dated link published by an outlet, recovered from an index. No "
                             "article text was fetched, so no record asserts the page was read"),
        "zeroResultMeaning": ("SEARCHED_NO_MATCH records that the listed searches completed and "
                              "returned nothing relevant; it is not a claim about world coverage"),
        "file": out.name, "bytes": out.stat().st_size, "sha256": digest,
        "dispositions": dispositions,
    }
    (OUT_DIR / "press_evidence_manifest.json").write_text(
        json.dumps(manifest, indent=1), encoding="utf-8")

    print(f"events            : {len(events)}")
    for k in (FOUND, OFFICIAL, NO_MATCH, LIMITED, PENDING):
        print(f"  {k:<22} {counts.get(k, 0)}")
    print(f"reference records : {len(records):,}")
    print(f"distinct publishers: {manifest['distinctPublishers']:,}")
    print(f"wrote {out} ({out.stat().st_size:,} bytes, sha256 {digest[:16]})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
