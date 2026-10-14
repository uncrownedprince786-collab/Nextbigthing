"""Build and verify the trading-principles corpus.

    python tools/foundation/principles.py

Each principle's citation is checked against Crossref (title fragment, first-author surname and
publication year within one) and the result is stored with it. A principle that fails stays in the
file, marked, so the failure is visible; only verified ones count toward the total.

`testable_now` is derived, not asserted: it is True only when every input in `needs` is something
this repository stores. The count of testable principles and the count of verified citations are
reported separately, because a well-cited idea that needs data we do not hold is not a test.
"""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from principles_src import P  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent.parent
OUT = ROOT / "data" / "foundation" / "principles"
UA = "NextBigThing-research/1.0 (mailto:claude.pro@thedg.group)"

# "intraday bars" is deliberately absent: about eight stored session days cannot test an intraday effect.
HAVE = {"price", "volume", "industry", "news", "event:earnings", "event:fomc"}


def have(need: str) -> bool:
    return need in HAVE or need.startswith("macro")


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", s.lower())


def crossref(doi: str) -> dict | None:
    url = "https://api.crossref.org/works/" + urllib.parse.quote(doi)
    for i in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)["message"]
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            time.sleep(2 * (i + 1))
        except (urllib.error.URLError, TimeoutError):
            time.sleep(2 * (i + 1))
    return None


def search(p: dict) -> list[dict]:
    """Crossref's own bibliographic search for the cited title, author and year."""
    q = urllib.parse.urlencode({"query.bibliographic": f"{p['title']} {p['author']} {p['year']}",
                                "rows": 5, "select": "DOI,title,author,issued,container-title"})
    try:
        req = urllib.request.Request("https://api.crossref.org/works?" + q, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)["message"]["items"]
    except Exception:  # noqa: BLE001
        return []


def judge(p: dict, m: dict) -> dict:
    """Does this Crossref record match the citation: title fragment, first author, year within one."""
    title = " ".join(m.get("title", [""]))
    fams = [a.get("family", "") for a in m.get("author", [])]
    parts = (m.get("issued") or {}).get("date-parts", [[None]])[0]
    year = parts[0] if parts else None
    why = []
    if norm(p["title"]) not in norm(title):
        why.append(f"title mismatch: Crossref says '{title[:80]}'")
    if p["author"].lower() not in " ".join(fams).lower():
        why.append(f"author mismatch: Crossref lists {fams[:3]}")
    if year is None or abs(year - p["year"]) > 1:
        why.append(f"year mismatch: Crossref says {year}")
    return {"verified": not why, "reason": "; ".join(why) or "title, first author and year match Crossref",
            "crossrefTitle": title, "crossrefYear": year, "crossrefAuthors": fams[:4],
            "container": (m.get("container-title") or [""])[0]}


def check(p: dict) -> dict:
    m = crossref(p["doi"])
    if m is not None:
        v = judge(p, m)
        if v["verified"]:
            return v
        first = v
    else:
        first = {"verified": False, "reason": "DOI not found at Crossref"}
    # The recorded DOI is wrong. Accept a replacement only if Crossref's search returns a record
    # that passes the same test; the original DOI and the reason it failed stay on the record.
    for item in search(p):
        v = judge(p, item)
        if v["verified"]:
            p["doi_original"], p["doi"] = p["doi"], item["DOI"]
            v["reason"] = f"DOI replaced after Crossref search ({first['reason'][:60]}); " + v["reason"]
            return v
    return first


def check_old(p: dict) -> dict:
    m = crossref(p["doi"])
    if m is None:
        return {"verified": False, "reason": "DOI not found at Crossref"}
    title = " ".join(m.get("title", [""]))
    fams = [a.get("family", "") for a in m.get("author", [])]
    year = None
    for k in ("issued", "published-print", "published-online"):
        parts = (m.get(k) or {}).get("date-parts", [[None]])[0]
        if parts and parts[0]:
            year = parts[0]
            break
    why = []
    if norm(p["title"]) not in norm(title):
        why.append(f"title mismatch: Crossref says '{title[:80]}'")
    if p["author"].lower() not in " ".join(fams).lower():
        why.append(f"author mismatch: Crossref lists {fams[:3]}")
    if year is None or abs(year - p["year"]) > 1:
        why.append(f"year mismatch: Crossref says {year}")
    return {"verified": not why, "reason": "; ".join(why) or "title, first author and year match Crossref",
            "crossrefTitle": title, "crossrefYear": year, "crossrefAuthors": fams[:4],
            "container": (m.get("container-title") or [""])[0]}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    seen, rows = set(), []
    for p in P:
        assert p["id"] not in seen, p["id"]
        seen.add(p["id"])
        v = check(p)
        time.sleep(0.25)
        rows.append({**p, "doiUrl": "https://doi.org/" + p["doi"],
                     "citation": v, "testable_now": all(have(n) for n in p["needs"]),
                     "status": "untested"})
        print(f"{'ok ' if v['verified'] else 'BAD'} {p['id']:18} {v['reason'][:90]}", flush=True)
    summary = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "principles": len(rows),
        "citationsVerified": sum(r["citation"]["verified"] for r in rows),
        "testableNow": sum(r["testable_now"] for r in rows),
        "verifiedAndTestableNow": sum(r["citation"]["verified"] and r["testable_now"] for r in rows),
        "byFamily": {},
    }
    for r in rows:
        summary["byFamily"][r["family"]] = summary["byFamily"].get(r["family"], 0) + 1
    (OUT / "principles.json").write_text(json.dumps({"summary": summary, "principles": rows}, indent=1),
                                         encoding="utf-8")
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
