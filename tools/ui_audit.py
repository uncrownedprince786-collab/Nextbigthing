"""Check the live site against the display rules a reader relies on, and fail loudly if one breaks.

    python tools/ui_audit.py                  checks https://nextbigthing-nu.vercel.app
    SITE_URL=http://localhost:3000 python tools/ui_audit.py

Every rule here was asked for and built (brain.md rules 74, 78, 79, 80, 85 and 86); this is the check that
they still hold on the pages people actually read, not just in the code that renders them. It reads the
rendered HTML of the home page and every market page and checks, row by row:

  1. the price alone: the price cell holds one price and nothing under it -- no "Last trade" line,
     no "Oct 9 close" line, no UTC time (the time is a tooltip);
  2. nothing contradicts its call: no Falling Star on a LONG, no Rising Star on a SHORT, and a
     change sentence ("Switched from Short to Long on Oct 10: ...") always ends in the row's verdict;
  3. no badges: no WAIT pill, and no change badge ("REVERSED: SHORT ➔ LONG") anywhere in a row;
     and a "Held back" row prints its reason and no levels -- no entry zone, stop, exit or reward
     beside a name the rule table made no call on (brain.md rule 93, which withdrew rule 86's
     "every priced name resolves to LONG or SHORT");
  4. no placeholder cell: "none stored", "not stored", "not applicable", "N/A", "N waiting";
  5. the held-back list is folded away on every page that has one;
  6. pool parity: every asset the database holds is listed on one of the market pages;
  7. one snapshot: every market page and `/api/health` report the same data stamp (rule 93).

Before reading, it asks `/api/revalidate` to bring the caches onto the database's current snapshot --
a call that does nothing when they are already there. It changes no data. Exit 0 when every check
passes, 1 when any fails (with the row that failed), 2 when the site cannot be read.
"""

from __future__ import annotations

import os
import re
import sys
import urllib.request

PAGES = ["/", "/stocks", "/crypto", "/psx", "/forex", "/commodities"]
CLASS_PAGES = ["/stocks", "/crypto", "/psx", "/forex", "/commodities"]
# A price, including the compact sub-cent form "$0.0₅4036" (subscript count of zeros).
PRICE = r"[$€£¥]?(?:Rs\.?)?\s?-?[\d,]+\.\d+(?:[₀-₉]+\d+)?"
BANNED = re.compile(r"(?i)none stored|not stored|not applicable|\bN/A\b|\b\d+ waiting\b")
TAG = re.compile(r"<[^>]+>")
# The level cells of a held-back row: each must say there is no call, never print a price (rule 93).
HELD_BACK_LEVELS = re.compile(
    r"\bEntry zone (?:no call|none: the call ended) Stop loss (?:no call|none: the call ended) "
    r"Measured exit (?:no call|none: the call ended) Reward:risk (?:no call|none: the call ended)\b"
)


def text_of(html: str) -> str:
    return re.sub(r"\s+", " ", TAG.sub(" ", html.replace("<!-- -->", ""))).strip()


def rows_of(html: str) -> list[str]:
    """The text of every decision row on a page: list items that carry an Action cell.

    `<li` followed by whitespace or `>` only: a bare `<li[^>]*>` also matches `<link ...>` in the
    page head, and once read every market page as one giant "row" -- a false failure, caught on its
    first run against the live pages."""
    return [t for t in (text_of(li) for li in re.findall(r"<li(?:\s[^>]*)?>(.*?)</li>", html, re.S)) if " Action " in f" {t} "]


def action_of(row: str) -> str | None:
    m = re.search(r"\bAction (LONG|SHORT|WAIT|Held back)\b", row)
    return m.group(1) if m else None


def check_price(row: str) -> str | None:
    m = re.search(r"\bPrice (.*?) Entry zone\b", row)
    if not m:
        return "no price cell"
    cell = m.group(1).strip()
    if cell == "no close yet":
        return None
    if not re.fullmatch(PRICE, cell):
        return f"the price cell is not a price alone: '{cell[:60]}'"
    return None


def check_badges(row: str) -> str | None:
    action = action_of(row)
    if action == "WAIT":
        return "a WAIT pill in the action cell"
    if action == "Held back" and "Why no call" not in row:
        return "a held-back row with no reason"
    if action == "Held back" and not HELD_BACK_LEVELS.search(row):
        return "a held-back row printing levels: an entry, stop or exit beside a name with no call"
    if re.search(r"\b(?:REVERSED|INVALIDATED|OVERRIDDEN|WITHDRAWN|NEW CALL):|➔", row):
        return "a change badge in the row"
    if action == "LONG" and "FALLING STAR" in row:
        return "Falling Star on a LONG"
    if action == "SHORT" and "RISING STAR" in row:
        return "Rising Star on a SHORT"
    for to in re.findall(r"\bSwitched from \w+ to (\w+) on ", row):
        if action and to.upper() != action:
            return f"a change sentence ends in {to} on a {action} row"
    return None


def folded(html: str, summary_start: str) -> bool | None:
    """True if the <details> whose summary starts with `summary_start` is closed, None if absent."""
    for m in re.finditer(r"<details([^>]*)>(.*?)</details>", html, re.S):
        if summary_start in text_of(m.group(2))[: len(summary_start) + 40]:
            return " open" not in m.group(1)
    return None


def align(site: str) -> str:
    """Ask the site to bring its caches onto the database's snapshot; the reply, for the log."""
    req = urllib.request.Request(site + "/api/revalidate", data=b"", method="POST", headers={"User-Agent": "nbt-ui-audit"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.read().decode("utf-8", "replace")[:200]
    except Exception as e:  # noqa: BLE001 - the audit still runs; a skew it then finds is reported
        return f"could not align ({type(e).__name__})"


def audit(site: str, fetch=None) -> tuple[list[str], dict[str, int]]:
    if fetch is None:
        align(site)
    fetch = fetch or (lambda url: urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "nbt-ui-audit"}), timeout=60).read().decode("utf-8", "replace"))
    failures: list[str] = []
    counts = {"rows": 0, "stars": 0, "changes": 0, "listed": 0, "pool": 0}
    listed: set[str] = set()
    stamps: dict[str, str] = {}
    for page in PAGES:
        html = fetch(site + page)
        if page in CLASS_PAGES:
            listed.update(re.findall(r'href="/asset/([^"#?]+)"', html))
            m = re.search(r'data-snapshot="([^"]*)"', html)
            if m:
                stamps[page] = m.group(1)
        for row in rows_of(html):
            counts["rows"] += 1
            counts["stars"] += len(re.findall(r"(RISING|FALLING) STAR", row))
            counts["changes"] += len(re.findall(r"\bSwitched from ", row))
            for check in (check_price, check_badges):
                why = check(row)
                if why:
                    failures.append(f"{page}: {why}: {row[:120]}")
        page_text = text_of(html)
        for hit in sorted(set(BANNED.findall(page_text))):
            failures.append(f"{page}: placeholder text '{hit}'")
        for summary in ("Held back:", "No direction:", "Not published:"):
            state = folded(html, summary)
            if state is False:
                failures.append(f"{page}: the '{summary}' list is open on load")
    # Pool parity: every asset the database holds appears on one of the market pages.
    import json

    health = json.loads(fetch(site + "/api/health"))
    pool = health.get("pool")
    counts["listed"], counts["pool"] = len(listed), pool or 0
    if isinstance(pool, int) and len(listed) != pool:
        failures.append(f"pool parity: the market pages list {len(listed)} assets, the database holds {pool}")
    # One snapshot: every market page and the health endpoint read the same cached rows (rule 93).
    snap = health.get("snapshot")
    if snap is not None or stamps:
        differing = sorted({v for v in stamps.values()} | ({snap} if snap is not None else set()))
        if len(differing) > 1:
            failures.append(f"snapshot skew: the pages and /api/health serve {len(differing)} different snapshots: {differing[:3]}")
    return failures, counts


def main() -> int:
    site = (os.environ.get("SITE_URL") or "https://nextbigthing-nu.vercel.app").rstrip("/")
    try:
        failures, counts = audit(site)
    except Exception as e:  # noqa: BLE001 - an unreadable site is its own answer
        print(f"ui audit: could not read {site} ({type(e).__name__})")
        return 2
    print(
        f"ui audit: {counts['rows']} rows on {len(PAGES)} pages, every price cell checked, "
        f"{counts['stars']} star markers, {counts['changes']} change sentences, "
        f"{counts['listed']} of {counts['pool']} assets listed on the market pages"
    )
    if failures:
        print(f"ui audit: {len(failures)} FAILED")
        for f in failures[:40]:
            print("  " + f)
        return 1
    print("ui audit: every check passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
