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
  7. one snapshot: every market page and `/api/health` report the same data stamp (rule 93);
  8. one run state: each overview card reports the same run state, name count and published count as
     its market page, and no overview card says a market "has not been through a run" (rule 95).

Before reading, it asks `/api/revalidate` to bring the caches onto the database's current snapshot --
a call that does nothing when they are already there. It changes no data. Exit 0 when every check
passes, 1 when any fails (with the row that failed), 2 when the site cannot be read.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
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


def run_states(html: str) -> list[dict[str, str | None]]:
    """Every element that prints a run state (rule 95): the market page's status line, the overview cards."""
    out: list[dict[str, str | None]] = []
    for tag in re.findall(r"<[a-z]+\s[^>]*data-run-state=[^>]*>", html):
        def attr(name: str, tag: str = tag) -> str | None:
            m = re.search(name + r'="([^"]*)"', tag)
            return m.group(1) if m else None

        out.append({"market": attr("data-market"), "state": attr("data-run-state"), "names": attr("data-names"), "published": attr("data-published")})
    return out


def check_run_states(cards: dict[str, dict], pages: dict[str, dict]) -> list[str]:
    """The overview card for each market against that market's own page."""
    failures: list[str] = []
    if not cards or not pages:
        return failures
    for slug, page in sorted(pages.items()):
        card = cards.get(slug)
        if card is None:
            failures.append(f"run state: the overview has no card for {slug}")
            continue
        for key in ("state", "names", "published"):
            if card.get(key) != page.get(key):
                failures.append(f"run state: the overview says {key} {card.get(key)} for {slug}, /{slug} says {page.get(key)}")
    return failures


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
    fetch = fetch or (lambda url: urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "nbt-ui-audit"}), timeout=60).read().decode("utf-8", "replace"))
    failures: list[str] = []
    counts = {"rows": 0, "stars": 0, "changes": 0, "listed": 0, "pool": 0}
    listed: set[str] = set()
    stamps: dict[str, str] = {}
    cards: dict[str, dict] = {}
    states: dict[str, dict] = {}
    for page in PAGES:
        html = fetch(site + page)
        if page == "/":
            cards = {s["market"]: s for s in run_states(html) if s["market"]}
            if re.search(r"not been through a run|No stored reading yet", text_of(html)):
                failures.append("/: an overview card says a market has not been through a run")
        if page in CLASS_PAGES:
            own = [s for s in run_states(html) if not s["market"]]
            if own:
                states[page.strip("/")] = own[0]
            listed.update(re.findall(r'href="/asset/([^"#?]+)"', html))
            # Crypto names are reached at their own fast route, not at /asset. The property this
            # check protects is reachability -- every name the database holds is on a market page
            # -- and that is unchanged by which page a name's link points at, so both spellings
            # count. Counting only /asset would have read the whole crypto market as missing.
            #
            # Two populations live on /crypto now. A registry coin keeps its CoinPaprika slug and
            # has a hyphen in it (`btc-bitcoin`); a coin the venue trades and the registry has
            # never collected is addressed by its bare ticker (`1inch`). Only the first kind is a
            # database asset, so only the first kind is counted against the registry ceiling --
            # the second is counted on its own, because listing 450 coins the database does not
            # hold is the feature and must not read as the pool overflowing.
            crypto_links = set(re.findall(r'href="/crypto/([^"#?]+)"', html))
            listed.update(s for s in crypto_links if "-" in s)
            counts["venueOnly"] = counts.get("venueOnly", 0) + len(
                [s for s in crypto_links if "-" not in s])
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
    failures.extend(check_run_states(cards, states))
    # Pool parity: every asset the database holds appears on one of the market pages.
    import json

    health = json.loads(fetch(site + "/api/health"))
    # No market with names may read "never run" while a decision run exists (rule 95): live on 2026-10-11
    # an unreadable log was printed as "No decision run has logged this market yet" on every page.
    ran = (health.get("decisions") or {}).get("newest")
    if ran:
        for where, s in [*(("/", c) for c in cards.values()), *((f"/{k}", v) for k, v in states.items())]:
            if s.get("state") == "NO_READING" and (s.get("names") or "0") != "0":
                failures.append(f"run state: {where} says {s.get('market') or where.strip('/')} has never been run, and health shows a decision run of {ran}")
    # Pool parity, in both directions, against two numbers rather than one.
    #
    # Until 2026-10-21 the class pages listed exactly the active pool, so one equality covered
    # both halves of the question. They now carry a directory of the **whole registry** above the
    # lists -- without it, the ten crypto names outside the pool appeared nowhere on the site and
    # /crypto answered "no such coin" for each. So the floor is the pool (every name that can
    # carry a call is reachable) and the ceiling is the registry (nothing is listed that the
    # database does not hold).
    pool = health.get("pool")
    registry = health.get("registry")
    counts["listed"], counts["pool"] = len(listed), pool or 0
    counts["registry"] = registry or 0
    if isinstance(pool, int) and len(listed) < pool:
        failures.append(
            f"pool parity: the market pages list {len(listed)} assets, under the {pool} in the active pool")
    if isinstance(registry, int) and len(listed) > registry:
        failures.append(
            f"pool parity: the market pages list {len(listed)} assets, over the {registry} the database holds")
    # One snapshot: every market page and the health endpoint read the same cached rows (rule 93).
    snap = health.get("snapshot")
    if snap is not None or stamps:
        differing = sorted({v for v in stamps.values()} | ({snap} if snap is not None else set()))
        if len(differing) > 1:
            failures.append(f"snapshot skew: the pages and /api/health serve {len(differing)} different snapshots: {differing[:3]}")
    return failures, counts



#: How far a price printed on a trending card may sit from the venue's own quote before it is a
#: failure rather than elapsed time.
#:
#: Three percent, and the number is set by the cache rather than by the market. The page serves
#: a ticker snapshot up to twelve seconds old by design, and the cards are *chosen* for being the
#: day's biggest movers -- so the coins this check looks at are exactly the ones that travel
#: furthest in twelve seconds. A 1% bound caught BMT, up 29% on the day, moving 1.33% between the
#: render and the check: a true reading of a stale-by-design price, not a fault.
#:
#: What it still catches is the fault worth catching, which is not off by a percent: a card
#: pairing one coin's name with another coin's price, a venue mapped to the wrong instrument, or
#: a ticker collision. Those are off by multiples.
TRENDING_PRICE_TOLERANCE = 3.0


def check_trending(html: str) -> list[str]:
    """The trending cards print a real price for the coin they name.

    The cards are the most prominent numbers on the site and the most easily wrong: they are
    chosen by a ranking, drawn from a different payload than the table, and labelled by a name
    that comes from a third source. A card that pairs one coin's name with another coin's price
    is wrong in a way that no status code and no snapshot check would ever report.
    """
    import json
    import urllib.request

    out: list[str] = []
    start = html.find("Trending")
    end = html.find("All coins")
    if start == -1 or end == -1 or end <= start:
        return ["/crypto: no trending section"]
    seg = html[start:end]
    slugs = list(dict.fromkeys(re.findall(r'href="/crypto/([a-z0-9\-]+)"', seg)))
    if len(slugs) < 5:
        return [f"/crypto: the trending section shows {len(slugs)} cards"]

    path = Path(__file__).resolve().parent.parent / "data" / "foundation" / "dataset" / "crypto_universe.json"
    if not path.exists():
        return []
    uni = {a["slug"]: a for a in json.loads(path.read_text(encoding="utf-8"))["assets"]}
    text = TAG.sub(" ", seg)
    text = re.sub(r"\s+", " ", text)

    for slug in slugs[:5]:
        a = uni.get(slug)
        if not a:
            out.append(f"/crypto: trending card {slug} is not in the universe")
            continue
        m = re.search(re.escape(a["name"]) + r"\s*\$([0-9,.]+)", text)
        if not m:
            out.append(f"/crypto: trending card {slug} prints no price beside its name")
            continue
        shown = float(m.group(1).replace(",", ""))
        venue, inst = a["venue"], a["instrument"]
        try:
            if venue == "gate":
                url = f"https://api.gateio.ws/api/v4/spot/tickers?currency_pair={inst}"
                live = float(json.loads(_fetch(url))[0]["last"])
            elif venue == "mexc":
                url = f"https://api.mexc.com/api/v3/ticker/price?symbol={inst}"
                live = float(json.loads(_fetch(url))["price"])
            else:
                url = f"https://data-api.binance.vision/api/v3/ticker/price?symbol={inst}"
                live = float(json.loads(_fetch(url))["price"])
        except Exception:  # noqa: BLE001 - an unreachable venue is not a page fault
            continue
        if live <= 0:
            continue
        diff = abs(shown - live) / live * 100
        if diff > TRENDING_PRICE_TOLERANCE:
            out.append(
                f"/crypto: trending card {slug} shows {shown} where {venue} quotes {live} "
                f"({diff:.2f}% apart)")
    return out


def _fetch(url: str) -> bytes:
    import urllib.request

    return urllib.request.urlopen(
        urllib.request.Request(url, headers={"User-Agent": "nbt-ui-audit"}), timeout=20
    ).read()


#: The journey the crypto brain exists to serve, as URLs. Bitcoin is the lane that was built first
#: and is checked at every window; two other coins are checked at one each, so a fault that is
#: specific to Bitcoin's own model family is told apart from one in the shared path.
JOURNEY_COINS = ["btc-bitcoin", "eth-ethereum", "xrp-xrp"]
JOURNEY_WINDOWS = ["m5", "m15", "h1", "h4", "d1", "d5", "d20"]
#: Every state the forecast panel is allowed to render. A page that shows none of them is the
#: failure this check exists for: a blank where a direction or a named reason should be.
#: The states `components/cryptoBrain.tsx` may render, as it stamps them on the panel. Read from
#: `data-forecast=` rather than from the words on the page: the first version of this check matched
#: the sentence "which way it goes", which also appears in the note above the picker explaining
#: that a window is *not* a direction, so every page passed as a direction panel.
#:
#: There is no `quiet` state any more. Every window a lane can answer gets a direction, and how
#: much the model is saying rides on the call as `data-strength` rather than replacing it -- so a
#: panel that prints no direction is a failure again, which is what this set is for.
JOURNEY_STATES = {"direction", "refused", "no-model", "no-source", "data", "error"}

#: The style each window belongs to, mirroring `lib/tradingStyles.ts`. The audit walks the journey
#: the way a reader does -- style first, then the window inside it -- so a style that stopped
#: offering a window would fail here rather than being walked around.
STYLE_OF = {"m5": "scalp", "m15": "scalp", "h1": "intraday", "h4": "intraday",
            "d1": "swing", "d5": "swing", "d20": "position"}

#: Mirrors `lib/cryptoHorizons.ts`. Used to check the answer restates the window it is about.
HORIZON_LABEL = {"m5": "Next 5 minutes", "m15": "Next 15 minutes", "h1": "Next hour",
                 "h4": "Rest of today", "d1": "Next session", "d5": "This week",
                 "d20": "Coming month"}


def check_crypto_journey(site: str, fetch, counts: dict[str, int]) -> list[str]:
    """Home -> Crypto -> a coin -> a window -> that coin's chart and direction, walked for real.

    The defect this is built against is not a 500. It is a page that renders, carries the picker,
    and then says nothing underneath it -- which is what the old style picker did for every crypto
    name on the site, and which every status code and every snapshot check reported as healthy.

    So each check is about content: the coin list reaches the coin, the coin's page asks the
    duration question before answering it, a chosen window lands on *that* coin and reaches one of
    the six states the panel may render, and a direction is never printed without the chart and
    the window it belongs to.
    """
    out: list[str] = []
    try:
        index = fetch(site + "/crypto")
    except Exception as e:  # noqa: BLE001
        return [f"/crypto: could not be read ({type(e).__name__})"]

    # The market table links each coin at its own fast route. A price column is the reason the
    # page exists, so its absence is a failure here rather than a cosmetic difference: a table of
    # names with no prices is the old index wearing a new layout.
    linked = set(re.findall(r'href="/crypto/([^"#?]+)"', index))
    for coin in JOURNEY_COINS:
        if coin not in linked:
            out.append(f"/crypto: the market table does not link {coin}")
    # Here rather than in `audit`, which the unit tests drive with stub pages that carry no
    # trending section and should not be failed for it. This walk is only ever given the real
    # site, which is also the only place a venue can be reached to check a price against.
    out.extend(check_trending(index))
    if index.count("$") < 20:
        out.append("/crypto: the market table carries almost no prices")

    for i, coin in enumerate(JOURNEY_COINS):
        windows = JOURNEY_WINDOWS if i == 0 else JOURNEY_WINDOWS[:1]
        try:
            bare = fetch(f"{site}/crypto/{coin}")
        except Exception as e:  # noqa: BLE001
            out.append(f"/crypto/{coin}: could not be read ({type(e).__name__})")
            continue
        text = text_of(bare)
        # The question has to be asked, and nothing may be answered before it is.
        if "How are you trading it" not in text:
            out.append(f"/crypto/{coin}: the page does not ask how the reader is trading")
        if "Pick how you are trading" not in text:
            out.append(f"/crypto/{coin}: a window was answered without being chosen")
        # Every style button prints the window it resolves to, which is the whole reason a style
        # vocabulary is safe to offer at all.
        for word in ("Scalping", "Intraday", "Swing", "Position"):
            if word not in text:
                out.append(f"/crypto/{coin}: the {word} style is missing from the picker")

        for w in windows:
            url = f"{site}/crypto/{coin}?style={STYLE_OF.get(w, 'scalp')}&h={w}"
            try:
                html = fetch(url)
            except Exception as e:  # noqa: BLE001
                out.append(f"{url}: could not be read ({type(e).__name__})")
                continue
            t = text_of(html)
            counts["journey"] = counts.get("journey", 0) + 1
            # The answer must be about the coin that was asked about.
            if f"/crypto/{coin}?" not in html:
                out.append(f"{url}: the picker on this page does not point back at {coin}")
            low = t.lower()
            m = re.search(r'data-forecast="([a-z-]+)"', html)
            state = m.group(1) if m else None
            if state not in JOURNEY_STATES:
                out.append(f"{url}: the panel rendered none of its states -- a blank answer")
                continue
            if not re.search(rf'data-horizon="{w}"', html):
                out.append(f"{url}: the panel answered a window other than {w}")
            if state == "direction":
                counts["directions"] = counts.get("directions", 0) + 1
                # A direction that does not say how strong it is reads as the same claim on the
                # bar the model is surest about and on the one it is closest to even on, which is
                # the whole reason the strength rides on the call rather than gating it.
                m2 = re.search(r'data-strength="(strong|weak)"', html)
                if not m2:
                    out.append(f"{url}: a direction with no strength on it")
                else:
                    counts[m2.group(1)] = counts.get(m2.group(1), 0) + 1
                    if m2.group(1).upper() not in html:
                        out.append(f"{url}: the panel says {m2.group(1)} in its markup and does not print it")
                # Entry, stop and target, or the page is a word with no way to act on it.
                for word in ("entry", "stop", "target"):
                    if word not in low:
                        out.append(f"{url}: a direction with no {word} level")
                d = re.search(r'data-direction="(UP|DOWN)"', html)
                if not d:
                    out.append(f"{url}: a direction panel with no direction in it")
                # The word has to be *printed*, not only stamped on the wrapper. Matched as its
                # own element rather than anywhere in the page text, because "UP" and "DOWN"
                # both appear in the note above the picker explaining what an answer looks like,
                # so a check against the page text would pass on a panel that printed nothing.
                elif f">{d.group(1)}</" not in html:
                    out.append(f"{url}: the panel says {d.group(1)} in its markup and prints no direction")
                if "the shaded panel on the right is" not in low:
                    out.append(f"{url}: a direction with no chart of the bars it was read from")
                if HORIZON_LABEL[w].lower() not in low:
                    out.append(f"{url}: a direction that does not restate the window it is for")
    return out


# After a revalidation the first visit to each page still receives its old HTML while the new one is
# rendered -- on-demand revalidation in this Next version is stale-while-revalidate for pages. Two red
# watchdog runs on 2026-10-11 were exactly that: the schema lane rewrote setups, the audit revalidated, and
# read the pages before they had re-rendered. So a revalidation is followed by one warming pass over the
# pages, and a skew is re-read a bounded number of times before it is reported. A skew that persists is
# still a failure; one that is a page mid-render is not a fault in the site. A third run, live the same
# day, found the five market pages re-rendered from a read taken mid-write while the cache kept a later
# one, so the route answered "aligned"; it now reads the pages too, and each re-read asks it again.
SKEW_RETRIES = 3
SKEW_WAIT_S = 20


def warm(site: str) -> None:
    for page in PAGES:
        try:
            urllib.request.urlopen(urllib.request.Request(site + page, headers={"User-Agent": "nbt-ui-audit"}), timeout=60).read()
        except Exception:  # noqa: BLE001 - the audit proper reports an unreadable page
            pass


def fetch_page(url: str) -> str:
    return urllib.request.urlopen(
        urllib.request.Request(url, headers={"User-Agent": "nbt-ui-audit"}), timeout=60
    ).read().decode("utf-8", "replace")


def main() -> int:
    import time

    site = (os.environ.get("SITE_URL") or "https://nextbigthing-nu.vercel.app").rstrip("/")
    try:
        reply = align(site)
        if '"revalidated":true' in reply:
            warm(site)
            time.sleep(SKEW_WAIT_S)
        failures, counts = audit(site)
        tries = 0
        while tries < SKEW_RETRIES and failures and all("snapshot skew" in f for f in failures):
            tries += 1
            # Ask again: a page re-rendered from an earlier read than the one the cache kept is behind
            # even when the cache is not, and the route now re-renders such pages (lib/alignment.ts).
            align(site)
            warm(site)
            time.sleep(SKEW_WAIT_S)
            failures, counts = audit(site)
        if tries:
            print(f"ui audit: re-read {tries} time(s) while pages finished re-rendering after a revalidation")
        # The journey walk is run here rather than inside `audit`, which the unit tests drive with
        # planted HTML for the row rules: those fixtures hold no crypto pages, and a check that
        # fetched real ones from inside it would fail every one of them. This is a live-site check
        # and it belongs on the live-site path.
        failures.extend(check_crypto_journey(site, fetch_page, counts))
    except Exception as e:  # noqa: BLE001 - an unreadable site is its own answer
        print(f"ui audit: could not read {site} ({type(e).__name__})")
        return 2
    print(
        f"ui audit: {counts['rows']} rows on {len(PAGES)} pages, every price cell checked, "
        f"{counts['stars']} star markers, {counts['changes']} change sentences, "
        f"{counts['listed']} listed on the market pages ({counts['pool']} in the pool, "
        f"{counts.get('registry', 0)} in the registry, "
        f"{counts.get('venueOnly', 0)} more the venue trades), "
        f"{counts.get('journey', 0)} crypto windows walked "
        f"({counts.get('directions', 0)} returned a direction: "
        f"{counts.get('strong', 0)} strong, {counts.get('weak', 0)} weak)"
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
