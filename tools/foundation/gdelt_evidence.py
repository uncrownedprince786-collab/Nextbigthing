"""Historical press evidence for the verified event corpus, from GDELT's free archive.

    python tools/foundation/gdelt_evidence.py [--events N] [--window D] [--max M] [--sleep S]
    python tools/foundation/gdelt_evidence.py --resume      # continue a partial run

**The gap this closes, and the one it does not.** `News` holds about five weeks of headlines, and
that is not a source limit -- `jobs/retention.py` prunes the table at **70 days** because its
deepest reader clusters over 45. So operational news is short-lived *by design*, and a historical
corpus must not live there: a cleanup job would delete it. This writes a durable artifact instead,
and nothing here touches `News`.

GDELT's DOC 2.0 API serves article metadata (title, outlet, URL, publication timestamp) over a
historical window, free and unauthenticated. It does **not** serve article text, and this tool
does not fetch any: a reference whose page may since have gone is still evidence that an outlet
published something on a date, and pretending to have verified text we never read would be worse
than recording the reference.

**What is stored per record.** The URL, the outlet domain, the title, GDELT's `seendate` as the
publication time, the event date it was collected for, the retrieval time as first-seen, the
language, and a content hash over outlet+title+date so the same report arriving twice is one
record. Publication time, event time and first-seen time stay three separate fields, as they do
everywhere else in this project.

**Bounded by construction.** One request per event, a fixed record cap, a sleep between calls, and
a per-event cache on disk so a re-run costs nothing for events already collected. GDELT
rate-limits hard: a 429 is retried with backoff a few times and then recorded as a failure for
that event and the run moves on. A failed event is a recorded failure, not a silent zero, and
`--resume` picks up exactly those.

Reads no database and writes no database row.
"""

from __future__ import annotations

import hashlib
import json
import random
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent

CORPUS = ROOT / "data" / "foundation" / "events" / "events.json"
OUT_DIR = ROOT / "data" / "foundation" / "events"
CACHE = ROOT / ".cache" / "foundation" / "gdelt"

API = "https://api.gdeltproject.org/api/v2/doc/doc"

# Mutable run state, so the breaker counts across events rather than within one.
STATE = {"consecutive429": 0}
UA = "NextBigThing-research/1.0 (mailto:claude.pro@thedg.group)"

# GDELT answers 429 with the plain text "Please limit requests to one every 5 seconds".
# That sentence is the rate limit, so the pacing below is built from it rather than guessed,
# with jitter so repeated runs do not land on the same cadence.
WINDOW_DAYS = 3          # event date minus 1, plus this many days
MAX_RECORDS = 20         # per event
SLEEP = 6.0              # seconds between requests: the stated 5, plus headroom
JITTER = 1.5             # +/- seconds, so a retry storm cannot synchronise
RETRIES = 3              # on 429 / transient failure
BACKOFF = 20.0           # seconds, multiplied by the attempt and jittered

# After this many consecutive 429s the endpoint is in a penalty window, not merely busy, and
# continuing to ask is both useless and rude. The run stops cleanly, keeps every checkpoint and
# says what to do next; `--resume` picks up exactly here.
BREAKER_TRIP = 6


class Tripped(Exception):
    """The circuit breaker opened: the source is rate-limiting, not unavailable."""


LOG = ROOT / ".cache" / "foundation" / "gdelt_requests.log"


def log(line: str) -> None:
    """Append one request outcome, so the rate-limit story survives the process."""
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as fh:
        stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        fh.write(stamp + " " + line + "\n")


def arg(name: str, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def query_for(event: dict) -> str:
    """A phrase narrow enough to be about this event, not about its topic in general."""
    name = event.get("name", "").strip()
    # GDELT treats a quoted string as a phrase. Long names match nothing, so keep it short.
    words = name.split()
    return '"' + " ".join(words[:8]) + '"'


def fetch(event: dict, window: int, maxrec: int) -> tuple[list[dict] | None, str]:
    """`(articles, note)`. None means the attempt failed and should be recorded as a failure."""
    day = datetime.fromisoformat(event["date"]).replace(tzinfo=timezone.utc)
    start = (day - timedelta(days=1)).strftime("%Y%m%d%H%M%S")
    end = (day + timedelta(days=window)).strftime("%Y%m%d%H%M%S")
    url = (f"{API}?query={urllib.parse.quote(query_for(event))}&mode=artlist"
           f"&maxrecords={maxrec}&startdatetime={start}&enddatetime={end}&format=json")
    last = ""
    for attempt in range(1, RETRIES + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=90) as r:
                body = r.read().decode("utf-8", "replace")
            log(f"200 attempt={attempt} event={event['date']} bytes={len(body)}")
            STATE["consecutive429"] = 0
            if not body.strip():
                return [], "empty body"
            try:
                return json.loads(body).get("articles", []), "ok"
            except json.JSONDecodeError:
                # GDELT answers 200 with a plain-text complaint for a malformed query, and the
                # same shape for a rate-limit notice that did not come with a 429 status.
                txt = body[:160].strip()
                if "limit requests" in txt.lower():
                    STATE["consecutive429"] += 1
                    log(f"200-but-rate-limited attempt={attempt} event={event['date']}")
                    if STATE["consecutive429"] >= BREAKER_TRIP:
                        raise Tripped(txt)
                    time.sleep(BACKOFF * attempt + random.uniform(0, JITTER))
                    continue
                return [], f"non-JSON: {txt}"
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}"
            retry_after = e.headers.get("Retry-After") if e.headers else None
            log(f"{e.code} attempt={attempt} event={event['date']} retryAfter={retry_after}")
            if e.code in (429, 502, 503):
                STATE["consecutive429"] += 1
                if STATE["consecutive429"] >= BREAKER_TRIP:
                    raise Tripped(f"{BREAKER_TRIP} consecutive {e.code} responses")
                # The server's own figure wins when it gives one.
                try:
                    wait = float(retry_after) if retry_after else BACKOFF * attempt
                except ValueError:
                    wait = BACKOFF * attempt
                time.sleep(wait + random.uniform(0, JITTER))
                continue
            return None, last
        except Tripped:
            raise
        except Exception as e:  # noqa: BLE001 - one event must not end the run
            last = type(e).__name__
            log(f"ERR {last} attempt={attempt} event={event['date']}")
            time.sleep(BACKOFF * attempt + random.uniform(0, JITTER))
    return None, f"gave up after {RETRIES} attempts ({last})"


def record(event: dict, art: dict, seen_at: str) -> dict:
    url = art.get("url") or ""
    domain = art.get("domain") or ""
    title = (art.get("title") or "").strip()
    pub = art.get("seendate") or ""
    key = hashlib.sha256(f"{domain}|{title.lower()}|{pub[:8]}".encode()).hexdigest()[:20]
    return {
        "eventName": event["name"],
        "eventDate": event["date"],
        "eventCategory": event.get("category"),
        "instrument": event.get("instrument"),
        "url": url,
        "publisher": domain,
        "title": title,
        "publishedAt": pub,          # GDELT seendate: when the article was published/seen
        "firstSeenAt": seen_at,      # when THIS collector retrieved it
        "language": art.get("language"),
        "sourceCountry": art.get("sourcecountry"),
        "dedupeKey": key,
        "evidenceKind": "press reference (metadata only; article text not fetched)",
    }


def main() -> int:
    window = int(arg("--window", WINDOW_DAYS))
    maxrec = int(arg("--max", MAX_RECORDS))
    sleep_s = float(arg("--sleep", SLEEP))
    limit = int(arg("--events", 0)) or None
    resume = "--resume" in sys.argv

    doc = json.loads(CORPUS.read_text(encoding="utf-8"))
    events = [e for e in doc.get("events", []) if e.get("verified")]
    events.sort(key=lambda e: e["date"])
    if limit:
        events = events[:limit]
    CACHE.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"verified events: {len(events)}  window=-1..+{window}d  max={maxrec}  sleep={sleep_s}s")
    collected = 0
    failures: list[dict] = []
    requested = 0
    tripped = ""
    for i, e in enumerate(events, 1):
        slug = hashlib.sha256(f"{e['date']}|{e['name']}".encode()).hexdigest()[:16]
        cached = CACHE / f"{slug}.json"
        if cached.exists():
            if resume and json.loads(cached.read_text(encoding="utf-8")).get("note") == "ok":
                continue
            if not resume:
                continue
        seen_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        try:
            arts, note = fetch(e, window, maxrec)
        except Tripped as t:
            # The breaker opened. Every event collected so far is already on disk, so stop
            # cleanly, still write the artifact, and say what resumes it.
            tripped = str(t)
            print(f"\n  circuit breaker opened after {STATE['consecutive429']} "
                  f"rate-limited replies: {tripped}")
            print("  stopping cleanly; checkpoints are intact, re-run with --resume")
            break
        requested += 1
        if arts is None:
            failures.append({"event": e["name"], "date": e["date"], "reason": note})
            cached.write_text(json.dumps({"note": note, "articles": []}), encoding="utf-8")
            print(f"  {i:>3}/{len(events)} FAIL {e['date']} {e['name'][:44]} -> {note}")
        else:
            cached.write_text(json.dumps({"note": note, "articles": arts}), encoding="utf-8")
            collected += len(arts)
            print(f"  {i:>3}/{len(events)} {len(arts):>3} {e['date']} {e['name'][:48]}")
        time.sleep(sleep_s)

    # Build the durable artifact from every cached event, including earlier runs.
    records: dict[str, dict] = {}
    per_event: dict[str, int] = {}
    notes: dict[str, str] = {}
    for e in events:
        slug = hashlib.sha256(f"{e['date']}|{e['name']}".encode()).hexdigest()[:16]
        cached = CACHE / f"{slug}.json"
        if not cached.exists():
            continue
        blob = json.loads(cached.read_text(encoding="utf-8"))
        notes[e["name"]] = blob.get("note", "")
        seen_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        n = 0
        for a in blob.get("articles", []):
            r = record(e, a, seen_at)
            if not r["url"]:
                continue
            records.setdefault(r["dedupeKey"], r)
            n += 1
        per_event[e["name"]] = n

    out = OUT_DIR / "press_evidence.jsonl"
    with out.open("w", encoding="utf-8") as fh:
        for r in sorted(records.values(), key=lambda x: (x["eventDate"], x["publisher"])):
            fh.write(json.dumps(r, separators=(",", ":")) + "\n")
    digest = hashlib.sha256(out.read_bytes()).hexdigest()

    covered = sum(1 for v in per_event.values() if v)
    manifest = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "version": "press-evidence-v1",
        "source": {"name": "GDELT DOC 2.0", "endpoint": API,
                   "auth": "none", "serves": "article metadata only, not article text"},
        "whyNotInTheNewsTable": ("jobs/retention.py prunes News at 70 days for its operational "
                                 "readers; a historical corpus kept there would be deleted"),
        "eventsConsidered": len(events),
        "eventsWithEvidence": covered,
        "eventsWithNone": len(events) - covered,
        "uniqueRecords": len(records),
        "deduplication": "sha256 over publisher + lowercased title + publication day",
        "window": {"beforeDays": 1, "afterDays": window},
        "maxRecordsPerEvent": maxrec,
        "requestsThisRun": requested,
        "circuitBreaker": {"tripAfterConsecutiveRateLimits": BREAKER_TRIP,
                           "openedThisRun": bool(tripped), "reason": tripped or None},
        "pacing": {"secondsBetweenRequests": SLEEP, "jitterSeconds": JITTER,
                   "honoursRetryAfter": True,
                   "statedSourceLimit": "one request every 5 seconds (GDELT 429 body)"},
        "requestLog": str(LOG.relative_to(ROOT)).replace("\\", "/"),
        "failures": failures,
        "timeFields": {"publishedAt": "GDELT seendate", "firstSeenAt": "retrieval time by this "
                       "collector", "eventDate": "the corpus event date"},
        "file": out.name,
        "bytes": out.stat().st_size,
        "sha256": digest,
    }
    (OUT_DIR / "press_evidence_manifest.json").write_text(
        json.dumps(manifest, indent=1), encoding="utf-8")

    print(f"\nevents with evidence : {covered} of {len(events)}")
    print(f"unique records       : {len(records):,}")
    print(f"failures             : {len(failures)}")
    print(f"wrote {out} ({out.stat().st_size:,} bytes, sha256 {digest[:16]})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
