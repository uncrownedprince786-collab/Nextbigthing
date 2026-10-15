"""Load the verified historical event corpus into `Event` and link each one to its instrument.

    python tools/foundation/events_load.py              # report only, writes nothing
    python tools/foundation/events_load.py --apply      # upsert Event and EventLink

**Why this exists.** `tools/foundation/events.py` built a corpus of 240 candidate events and
verified 168 of them against Wikipedia, Wikidata and a measured market move, with the result in
`data/foundation/events/events.json`. None of it reached the database. `jobs/events.py` seeds a
hand-written list of eight events instead, so the site and every downstream reader have seen eight
historical events since the corpus was built. This loads the verified ones.

**What it does not do.** It does not detect events, re-verify them, or fetch anything. The
corpus is the evidence and this is a loader. It writes only events the corpus marks `verified`,
which means two independent evidence groups or a tier-A source, and it carries the tier and the
evidence groups onto the row so a reader can tell a well-sourced event from a thin one.

**Linkage is the corpus's own, not a guess.** Each verified event names one `instrument` that was
checked for a move at verification time. That is an explicit, traceable link and it becomes one
`EventLink` row. `MKT` and `PSX` are index proxies rather than stored assets and are recorded in
the event's note instead of forced onto an arbitrary ticker; the reaction corpus resolves them to
the acquired benchmark series. An instrument absent from the universe (`GME`) is reported and
skipped rather than dropped silently.

**Idempotent.** `Event.slug` and `EventLink (eventId, targetRef)` are unique, both writes are
upserts, and a second run reports the same counts and changes nothing. `discoveredAt` is set from
the corpus generation time on insert and never updated, because when the system first knew a date
is evidence and must not drift to the time of the last reload.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "jobs"))

CORPUS = ROOT / "data" / "foundation" / "events" / "events.json"

# Corpus instrument -> the symbol the universe stores it under.
ALIAS = {"OIL": "CL=F", "GOLD": "GC=F", "BTC": "btc-bitcoin", "ETH": "eth-ethereum"}
# Instruments that are a market rather than a tradable row in `Asset`.
PROXIES = {"MKT", "PSX"}

SOURCE = "foundation event corpus (Wikipedia/Wikidata verified)"


def arg(name: str, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def slugify(name: str, when: str) -> str:
    keep = [c.lower() if c.isalnum() else "-" for c in name]
    base = "".join(keep)
    while "--" in base:
        base = base.replace("--", "-")
    return f"{base.strip('-')[:60]}-{when}"


def verified_events(doc: dict) -> list[dict]:
    return [e for e in doc.get("events", []) if e.get("verified")]


def row_for(e: dict, sort: int, discovered: str) -> dict:
    """One Event row's fields, with the provenance the corpus carries."""
    wiki = e.get("wikipedia") or {}
    official = e.get("official") or []
    url = wiki.get("url") or (official[0].get("url") if official and isinstance(official[0], dict)
                              else "")
    groups = e.get("evidenceGroups") or []
    market = e.get("market") or {}
    notes = [f"tier {e.get('tier')}", f"evidence: {', '.join(groups) or 'none recorded'}"]
    if e.get("instrument") in PROXIES:
        notes.append(f"instrument {e['instrument']} is a market proxy, not a stored asset")
    if market.get("checked"):
        notes.append("verification measured a move in " + str(e.get("instrument"))
                     if market.get("moved") else
                     "verification measured no move in " + str(e.get("instrument")))
    return {
        "slug": slugify(e["name"], e["date"]),
        "name": e["name"],
        "summary": e.get("summary") or f"{e['name']}, dated {e['date']} in the public record.",
        "date": e["date"],
        "category": e.get("category") or "market",
        "source": SOURCE,
        "sourceUrl": url,
        "sort": sort,
        "notes": "; ".join(notes),
        "discoveredAt": discovered,
        "instrument": e.get("instrument"),
    }


UPSERT_EVENT = '''
INSERT INTO "Event" (slug, name, summary, date, category, source, "sourceUrl", sort,
                     notes, scheduled, lifecycle, "discoveredAt")
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, false, 'historical', %s)
ON CONFLICT (slug) DO UPDATE
SET name = EXCLUDED.name, summary = EXCLUDED.summary, date = EXCLUDED.date,
    category = EXCLUDED.category, source = EXCLUDED.source,
    "sourceUrl" = EXCLUDED."sourceUrl", sort = EXCLUDED.sort, notes = EXCLUDED.notes
RETURNING id, (xmax = 0) AS inserted'''

UPSERT_LINK = '''
INSERT INTO "EventLink" ("eventId", "assetId", "targetRef", relation)
VALUES (%s, %s, %s, %s)
ON CONFLICT ("eventId", "targetRef") DO UPDATE SET relation = EXCLUDED.relation'''


def main() -> int:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    from nbt import db, rows

    apply = "--apply" in sys.argv
    path = Path(arg("--corpus", CORPUS))
    if not path.exists():
        print(f"no corpus at {path}")
        return 1
    doc = json.loads(path.read_text(encoding="utf-8"))
    events = verified_events(doc)
    discovered = doc.get("summary", {}).get("generatedAt") or datetime.now(
        timezone.utc).isoformat(timespec="seconds")
    print(f"corpus: {len(doc.get('events', []))} candidates, {len(events)} verified")

    conn = db()
    cur = conn.cursor()
    try:
        assets = {r["symbol"]: r["id"] for r in rows(cur, 'SELECT symbol, id FROM "Asset"')}
        before = rows(cur, 'SELECT count(*) AS n FROM "Event"')[0]["n"]
        links_before = rows(cur, 'SELECT count(*) AS n FROM "EventLink"')[0]["n"]

        planned, unmapped, proxied = [], [], []
        for sort, e in enumerate(sorted(events, key=lambda x: x["date"]), 1):
            r = row_for(e, sort, discovered)
            ins = r["instrument"]
            if ins in PROXIES:
                proxied.append((r, ins))
            elif ALIAS.get(ins, ins) in assets:
                planned.append((r, ALIAS.get(ins, ins)))
            else:
                unmapped.append((r, ins))

        print(f"  linkable to a stored asset : {len(planned)}")
        print(f"  market proxies (MKT/PSX)   : {len(proxied)}")
        print(f"  instrument not in universe : {len(unmapped)}"
              + (f" -> {sorted({i for _, i in unmapped})}" if unmapped else ""))

        if not apply:
            print("\nreport only. Re-run with --apply to write.")
            return 0

        inserted = updated = linked = 0
        for r, sym in [(r, s) for r, s in planned] + [(r, None) for r, _ in proxied] + \
                      [(r, None) for r, _ in unmapped]:
            got = rows(cur, UPSERT_EVENT, (
                r["slug"], r["name"], r["summary"], r["date"], r["category"],
                r["source"], r["sourceUrl"], r["sort"], r["notes"], r["discoveredAt"]))[0]
            inserted += 1 if got["inserted"] else 0
            updated += 0 if got["inserted"] else 1
            if sym:
                cur.execute(UPSERT_LINK, (
                    got["id"], assets[sym], assets[sym],
                    f"the corpus verified this event against {sym}'s price series"))
                linked += 1
        conn.commit()

        after = rows(cur, 'SELECT count(*) AS n FROM "Event"')[0]["n"]
        links_after = rows(cur, 'SELECT count(*) AS n FROM "EventLink"')[0]["n"]
        print(f"\n  Event     {before} -> {after}  ({inserted} inserted, {updated} updated)")
        print(f"  EventLink {links_before} -> {links_after}  ({linked} upserted)")
        return 0
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
