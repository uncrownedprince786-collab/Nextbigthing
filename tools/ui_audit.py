"""Check the live site against the display rules a reader relies on, and fail loudly if one breaks.

    python tools/ui_audit.py                  checks https://nextbigthing-nu.vercel.app
    SITE_URL=http://localhost:3000 python tools/ui_audit.py

Every rule here was asked for and built (brain.md rules 74, 78, 79 and 80); this is the check that
they still hold on the pages people actually read, not just in the code that renders them. It reads the
rendered HTML of the home page and every market page and checks, row by row:

  1. one price per line: when a row leads with a last trade, the trade's own time is the line under
     it and the close the decision reads comes after, labelled -- the headline is never the close;
  2. no badge contradicts its call: no Falling Star on a LONG, no Rising Star on a SHORT, and a
     change badge always ends in the verdict the row shows;
  3. no placeholder cell: "none stored", "not stored", "not applicable", "N/A", "N waiting";
  4. the held-back list is folded away on every page that has one.

Exit 0 when every check passes, 1 when any fails (with the row that failed), 2 when the site cannot be
read. Read-only: it fetches pages and changes nothing.
"""

from __future__ import annotations

import os
import re
import sys
import urllib.request

PAGES = ["/", "/stocks", "/crypto", "/psx", "/forex", "/commodities"]
BANNED = re.compile(r"(?i)none stored|not stored|not applicable|\bN/A\b|\b\d+ waiting\b")
TAG = re.compile(r"<[^>]+>")


def text_of(html: str) -> str:
    return re.sub(r"\s+", " ", TAG.sub(" ", html.replace("<!-- -->", ""))).strip()


def rows_of(html: str) -> list[str]:
    """The text of every decision row on a page: list items that carry an Action cell."""
    return [t for t in (text_of(li) for li in re.findall(r"<li[^>]*>(.*?)</li>", html, re.S)) if " Action " in f" {t} "]


def action_of(row: str) -> str | None:
    m = re.search(r"\bAction (LONG|SHORT|WAIT)\b", row)
    return m.group(1) if m else None


def check_price(row: str) -> str | None:
    cell = row.split("Price & time", 1)[-1].split("Entry zone", 1)[0]
    if "last trade," not in cell:
        return None
    head = cell.index("last trade,")
    # The headline is the first price in the cell and it sits before the trade's time line.
    if not re.search(r"[$€£¥₨Rs]*\s?[\d,]+\.\d+", cell[:head]):
        return "a last trade's time is printed with no price above it"
    if "close" in cell[:head].lower():
        return "the close is printed above the last trade, as if it were the headline"
    if not re.search(r"\bclose\b", cell[head:]):
        return "a last trade is the headline but the close the decision reads is not labelled under it"
    return None


def check_badges(row: str) -> str | None:
    action = action_of(row)
    if action == "LONG" and "FALLING STAR" in row:
        return "Falling Star on a LONG"
    if action == "SHORT" and "RISING STAR" in row:
        return "Rising Star on a SHORT"
    for kind, to in re.findall(r"\b(REVERSED|INVALIDATED|OVERRIDDEN|WITHDRAWN|NEW CALL): \w+ ➔ (\w+)", row):
        if action and to != action:
            return f"{kind} badge ends in {to} on a {action} row"
    return None


def folded(html: str, summary_start: str) -> bool | None:
    """True if the <details> whose summary starts with `summary_start` is closed, None if absent."""
    for m in re.finditer(r"<details([^>]*)>(.*?)</details>", html, re.S):
        if summary_start in text_of(m.group(2))[: len(summary_start) + 40]:
            return " open" not in m.group(1)
    return None


def audit(site: str, fetch=None) -> tuple[list[str], dict[str, int]]:
    fetch = fetch or (lambda url: urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "nbt-ui-audit"}), timeout=60).read().decode("utf-8", "replace"))
    failures: list[str] = []
    counts = {"rows": 0, "price_cells_with_trade": 0, "stars": 0, "changes": 0}
    for page in PAGES:
        html = fetch(site + page)
        for row in rows_of(html):
            counts["rows"] += 1
            counts["price_cells_with_trade"] += "last trade," in row
            counts["stars"] += len(re.findall(r"(RISING|FALLING) STAR", row))
            counts["changes"] += len(re.findall(r"\b(REVERSED|INVALIDATED|OVERRIDDEN|WITHDRAWN|NEW CALL):", row))
            for check in (check_price, check_badges):
                why = check(row)
                if why:
                    failures.append(f"{page}: {why}: {row[:120]}")
        page_text = text_of(html)
        for hit in sorted(set(BANNED.findall(page_text))):
            failures.append(f"{page}: placeholder text '{hit}'")
        for summary in ("Held back:", "No direction:"):
            state = folded(html, summary)
            if state is False:
                failures.append(f"{page}: the '{summary}' list is open on load")
    return failures, counts


def main() -> int:
    site = (os.environ.get("SITE_URL") or "https://nextbigthing-nu.vercel.app").rstrip("/")
    try:
        failures, counts = audit(site)
    except Exception as e:  # noqa: BLE001 - an unreadable site is its own answer
        print(f"ui audit: could not read {site} ({type(e).__name__})")
        return 2
    print(
        f"ui audit: {counts['rows']} rows on {len(PAGES)} pages, {counts['price_cells_with_trade']} led by a last trade, "
        f"{counts['stars']} star markers, {counts['changes']} change badges"
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
