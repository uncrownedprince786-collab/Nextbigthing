"""Read what the public discussion around each asset and product currently looks like.

Three separate readings, deliberately not blended into one number:

  * tone, counted from a fixed word list over headlines
  * attention, this window's item count against the window immediately before it
  * a hype flag, which is only ever attention rising and promotional wording together

Everything here comes out of News rows the site already stored, so this job makes no request
of its own. It can only describe coverage already held, which also means a target whose feed
was rate limited shows fewer items rather than a quieter world, and the note says so.

What this is not
----------------
It is not sentiment analysis. It is a word list run over headlines, and the difference
matters enough to be repeated on every surface that shows it:

  * headlines only, never article bodies
  * no negation handling, so "not a record year" counts the positive word
  * no sarcasm, no irony, no context
  * the list was written for market wording, so it reads a product headline less well

That is why the counts are stored next to the direction and why the direction is withheld
entirely below MIN_ITEMS. A tone computed on three headlines is three headlines.

Run: python jobs/human.py
Writes: HumanSignal, and one SignalLog row per target so accuracy.py can come back later.
"""

from __future__ import annotations

import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from nbt import (  # noqa: E402
    db,
    one,
    pct,
    rows,
    step,
)

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except Exception:  # noqa: BLE001
    pass


# The measured window, and the equal window before it that attention is compared against.
WINDOW_DAYS = 30

# Below this many headlines the reading is labelled thin rather than withheld.
#
# This used to withhold the direction entirely, and that was the wrong call. Hiding a
# direction because it rests on four headlines does not protect a reader, it just means the
# site noticed something and said nothing — and the whole point of this thing is to be early,
# which is precisely when the evidence is thin. So the direction is published, the count is
# published next to it, and the grade drops to none with a note saying what it rests on. A
# reader can then decide; a reader shown nothing cannot.
#
# What stays forbidden is different and unchanged: inventing a number, or describing four
# headlines as agreement.
MIN_ITEMS = 8

# The catalyst window. Attention measured over 30 days is a trend; something arriving in the
# last three days that was not arriving before is an event, and only the second one moves a
# price before a reader has noticed. Three days covers a Friday statement read on Monday.
CATALYST_DAYS = 3

# How many times the baseline daily rate the recent window has to run at. Three times is a
# rate that would not happen by ordinary variation in a feed that publishes a couple of items
# a week, and low enough to catch a single significant report rather than only a media storm.
CATALYST_RATIO = 3.0

# The baseline needs enough items to be a rate rather than an accident. Below this the spike
# is left unmeasured: two items in a month is not a baseline, and dividing by it turns one
# ordinary article into a tenfold surge.
MIN_BASELINE_ITEMS = 4

# Robust deviations above the feed's own median story rate before a flag is allowed. Paired
# with CATALYST_RATIO on purpose: the ratio catches a jump off a quiet baseline, and this
# refuses a jump that is ordinary variation for a noisy feed. Both must agree.
CATALYST_Z = 3.0

# Below this many items in the prior window, velocity is left null. Dividing by 2 turns one
# extra article into +50%, which is arithmetic rather than a change in attention.
MIN_PRIOR_ITEMS = 5

# How far the net tone has to sit from zero before it is called a direction, **as a share of the
# headlines that expressed one**. 0.15 means a 15 point net lean among the opinionated headlines:
# 4 positive against 3 negative is not a direction, 6 against 1 is.
NEUTRAL_BAND = 0.15

# Tone-carrying headlines needed before a direction is published at all.
#
# This floor exists because the denominator below changed, and the old denominator had been
# providing a floor by accident. `tone_score` was `(positive - negative) / items`, dividing the
# net lean by **every** headline in the window including the ones carrying no tone word at all.
# Measured 2026-10-07 across 265 assets: the median share of headlines carrying any tone word is
# **11.1%**, and the median asset has **2** of them. So the old rule was asking for a net lean of
# 15% of total coverage, which for a well covered name is a bar nothing clears -- and the bar got
# *higher* the better covered the name was, because `items` grew while the opinionated subset did
# not. Three measured examples, every one of them called neutral:
#
#     items 64, positive  7, negative 0   ->  7/64 = 0.109
#     items 88, positive 14, negative 5   ->  9/88 = 0.102
#     items 90, positive 10, negative 6   ->  4/90 = 0.044
#
# 7 positive and 0 negative is not an absence of direction, and reporting it as one is the
# failure this site exists to avoid: it understates what is known. Only 55 of 265 assets carried
# a direction, and the news leg was the single biggest reason `jobs/setup.py` withheld a setup --
# failing in 124 of the 151 waiting rows, ahead of volume at 115.
#
# Dividing by the opinionated subset is the correction. It needs its own floor, because that
# subset can be one headline and a 1-0 split would otherwise read as total agreement. 5 is the
# same judgement `MIN_ITEMS` makes one level up -- "a tone computed on three headlines is three
# headlines" -- applied to the quantity that actually carries the tone. It takes the directional
# count from 55 to 69 of 265; a floor of 3 would take it to 116, which is reading a direction off
# two words and a tiebreak.
MIN_TONE_ITEMS = 5

# How much the item count has to move before attention is called rising or falling. News
# counts are noisy week to week and a feed that returned one page instead of two looks like
# a collapse in interest, so the band is wide on purpose.
ATTENTION_BAND = 25.0

# Share of headlines carrying promotional wording before the hype flag can be raised, and
# it is raised only when attention is rising at the same time. Promotional wording on its
# own is a publisher's house style; promotional wording arriving with a jump in coverage is
# the thing worth naming.
HYPE_SHARE_LIMIT = 0.20

# One publisher supplying more than this share of a window makes the window that
# publisher's coverage rather than a survey of coverage. Disclosed, and caps the grade.
DOMINANT_PUBLISHER_LIMIT = 0.5

# Grade thresholds. Principle 1: several independent sources beat one strong source, so
# publisher spread counts as much as volume here.
HIGH_ITEMS = 25
HIGH_PUBLISHERS = 10
MEDIUM_ITEMS = 15
MEDIUM_PUBLISHERS = 4


# Directional wording. Kept to words whose direction does not flip with context, which is
# why some obvious candidates are absent: "cut" is negative about guidance and positive
# about interest rates, "halt" is negative about a plant and neutral about a trading halt.
# An ambiguous word adds noise to both counts and removes nothing from either.
POSITIVE_TERMS = (
    "beats", "beat", "surges", "surged", "jumps", "jumped", "rallies", "rallied",
    "soars", "soared", "climbs", "climbed", "rises", "rose", "gains", "gained",
    "record high", "all-time high", "upgrade", "upgraded", "outperforms", "outperformed",
    "tops", "topped", "boosts", "boosted", "expands", "expanded", "wins", "won",
    "approved", "approval", "breakthrough", "strong demand", "raises guidance",
)

NEGATIVE_TERMS = (
    "misses", "missed", "plunges", "plunged", "slumps", "slumped", "sinks", "sank",
    "tumbles", "tumbled", "falls", "fell", "drops", "dropped", "slides", "slid",
    "downgrade", "downgraded", "underperforms", "underperformed", "loses", "lost",
    "losses", "warns", "warned", "warning", "recall", "recalled", "lawsuit", "sues",
    "probe", "investigation", "fined", "delays", "delayed", "layoffs", "bankruptcy",
    "weak demand", "cuts guidance", "profit warning",
)

# Promotional and clickbait wording. These are patterns of the article, not claims about the
# asset, which is exactly why they are counted separately from tone: "3 stocks to buy before
# it is too late" is not positive news, it is someone selling a click.
HYPE_TERMS = (
    "skyrocket", "to the moon", "moonshot", "explodes", "exploding", "parabolic",
    "next big", "must buy", "must-buy", "no-brainer", "screaming buy", "hidden gem",
    "get rich", "millionaire", "best stock", "top pick", "should you buy",
    "before it's too late", "before it is too late", "is it too late", "you need to buy",
    "will make you", "life-changing", "can't miss", "cannot miss",
)


def count_terms(text: str, terms: tuple[str, ...]) -> int:
    """How many of the terms appear anywhere, inside other words included. Counted once per term.

    Used for the promotional list only, where matching inside a longer word ("skyrocketing") is
    the intent and an over-match can only raise a caution flag. Tone never uses this: see
    `count_words`.

    A headline that repeats a word is still one headline saying it, and counting the
    repetition would let one loud headline outvote several quiet ones.
    """
    low = text.lower()
    return sum(1 for t in terms if t in low)


# A tone term counts only as the whole word or phrase listed. Matching inside longer words gave
# signs nothing in the headline said, measured 2026-10-11 over 30 days of stored headlines:
# "against" contains "gains", which made 13 of the 31 opinionated currency headlines positive
# ("Rupee trades in narrow range against US dollar"); "MarketBeat" contains "beat"; "issues"
# contains "sues"; "Wonder" contains "won". The lists already spell out every form they mean
# ("beats", "beat", "surges", "surged"), so an unlisted form is not counted, by design: a word
# list may miss a sign, it may not invent one. An apostrophe is part of a word, so "won't" is not
# "won".
_WORD_EDGE_L = r"(?<![\w'\u2019])"
_WORD_EDGE_R = r"(?![\w'\u2019])"
_WORD_PATTERNS: dict[str, re.Pattern[str]] = {}


def _word(term: str) -> re.Pattern[str]:
    pat = _WORD_PATTERNS.get(term)
    if pat is None:
        pat = _WORD_PATTERNS[term] = re.compile(_WORD_EDGE_L + re.escape(term) + _WORD_EDGE_R)
    return pat


def count_words(text: str, terms: tuple[str, ...]) -> int:
    """How many of the terms appear as whole words. Counted once per term, like `count_terms`."""
    low = text.lower()
    return sum(1 for t in terms if _word(t).search(low))


# Currency pairs. A pair's price is one currency in units of another, and a headline is usually
# about one of the two: "Rupiah gains" is USDIDR *falling*. The word list was scoring every
# headline as if it described the pair, so a stronger rupee read as a rising USDPKR -- the
# exact opposite. A headline now takes a side for a pair only when exactly one currency of that
# pair can be named from its wording: the base keeps the headline's sign, the quote reverses it,
# the pair written in its own order ("USD/INR") keeps it. Anything else takes no side: both
# currencies named ("Rupee gains against US dollar" -- which one gained is grammar, not a word
# list), a third currency named, the pair written backwards, or a currency word that is also an
# ordinary word ("won", "real", "rand") without its country. Rule 44 still applies above this:
# a reading can only ever withdraw evidence, so a headline left without a side can only cost a
# withdrawal, never invent one.
#
# code: (names that identify it on their own, bare names). Qualified names are matched first and
# taken out, so "Singapore dollar" is never read as the US dollar's bare "dollar". Every traded
# dollar answers to a bare "dollar", so on USDSGD or AUDUSD the word names neither side.
CURRENCIES: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "USD": (("us dollar", "u.s. dollar", "american dollar", "greenback"), ("dollar",)),
    "EUR": ((), ("euro",)),
    "GBP": (("british pound", "pound sterling"), ("sterling", "pound")),
    "JPY": (("japanese yen",), ("yen",)),
    "CHF": (("swiss franc",), ("franc",)),
    "CAD": (("canadian dollar", "loonie"), ("dollar",)),
    "AUD": (("australian dollar", "aussie dollar", "aussie"), ("dollar",)),
    "NZD": (("new zealand dollar", "kiwi dollar", "kiwi"), ("dollar",)),
    "SEK": (("swedish krona",), ("krona",)),
    "NOK": (("norwegian krone",), ("krone",)),
    "PLN": (("polish zloty",), ("zloty",)),
    "TRY": (("turkish lira",), ("lira",)),
    "ZAR": (("south african rand",), ("rand",)),
    "BRL": (("brazilian real",), ("real",)),
    "MXN": (("mexican peso",), ("peso",)),
    "INR": (("indian rupee",), ("rupee",)),
    "PKR": (("pakistani rupee", "pakistan rupee"), ("rupee",)),
    "KRW": (("south korean won", "korean won"), ("won",)),
    "IDR": (("indonesian rupiah",), ("rupiah",)),
    "CNY": (("chinese yuan", "offshore yuan"), ("yuan", "renminbi")),
    "THB": (("thai baht",), ("baht",)),
    "SGD": (("singapore dollar",), ("dollar",)),
    "MYR": (("malaysian ringgit",), ("ringgit",)),
    "PHP": (("philippine peso",), ("peso",)),
    "BDT": (("bangladeshi taka",), ("taka",)),
    # Not traded here. Listed so a headline about one is recognised as a third currency rather
    # than read as one of the pair's ("Hong Kong dollar" is not the US dollar).
    "HKD": (("hong kong dollar",), ()),
    "TWD": (("new taiwan dollar", "taiwan dollar", "taiwanese dollar"), ()),
    "DKK": (("danish krone",), ()),
    "LKR": (("sri lankan rupee", "sri lanka rupee"), ()),
    "EGP": (("egyptian pound",), ()),
    "ARS": (("argentine peso", "argentinian peso"), ()),
    "CLP": (("chilean peso",), ()),
    "COP": (("colombian peso",), ()),
    "RUB": ((), ("rouble", "ruble")),
}

# Bare currency names that are also ordinary words or names. On a headline for a pair that
# contains the currency they would name, they make the headline take no side ("Won strengthens"
# and "Samsung won the contract" cannot be told apart by a word list); elsewhere they are words.
AMBIGUOUS_BARE = frozenset({"won", "real", "rand"})

# Phrases that start with a currency name and are not about the currency.
NOT_A_CURRENCY = ("euro zone", "euro area")

_PAIR_TOKEN = re.compile(r"(?<![A-Za-z])([A-Za-z]{3})[/-]?([A-Za-z]{3})(?![A-Za-z])")


def fx_pair(symbol: str) -> tuple[str, str]:
    """The two currency codes of a stored pair symbol, e.g. "USDPKR" -> ("USD", "PKR")."""
    s = (symbol or "").upper().replace("/", "").replace("=X", "")
    return (s[:3], s[3:6]) if len(s) == 6 else ("", "")


def orient(title: str, pair: tuple[str, str]) -> tuple[str, int] | None:
    """The headline's wording with every currency name taken out, and +1 or -1 for which way its
    sign applies to the pair; None when it cannot be said which currency the headline is about.
    """
    base, quote = pair
    if base not in CURRENCIES or quote not in CURRENCIES or base == quote:
        return None
    named: set[str] = set()
    own = False

    # Pair tokens first ("USD/INR", "usdinr", "EUR-USD"), on the original wording, since a code
    # inside a token has no word boundary of its own.
    def token(m: re.Match[str]) -> str:
        nonlocal own
        a, b = m.group(1).upper(), m.group(2).upper()
        if a in CURRENCIES and b in CURRENCIES and a != b:
            if (a, b) == (base, quote):
                own = True
            else:
                named.update(("BACKWARDS",) if (a, b) == (quote, base) else (a, b))
            return " | "
        return m.group(0)

    text = _PAIR_TOKEN.sub(token, title)
    # Codes on their own, in capitals only: "TRY" is the lira, "try" is a verb.
    for code in CURRENCIES:
        pat = re.compile(r"(?<![A-Za-z])" + code + r"(?![A-Za-z])")
        if pat.search(text):
            named.add(code)
            text = pat.sub(" | ", text)
    text = text.lower()
    for phrase in NOT_A_CURRENCY:
        text = _word(phrase).sub(" | ", text)
    # Qualified names, longest first, so "south korean won" is taken before "korean won".
    qualified = sorted(
        ((q, code) for code, (quals, _) in CURRENCIES.items() for q in quals),
        key=lambda x: -len(x[0]),
    )
    for q, code in qualified:
        pat = re.compile(_WORD_EDGE_L + re.escape(q) + r"s?" + _WORD_EDGE_R)
        if pat.search(text):
            named.add(code)
            text = pat.sub(" | ", text)
    # Bare names. One shared by two currencies ("rupee", "peso") names the pair's own when only
    # one side of the pair has it, and a third currency when neither does.
    bare: dict[str, set[str]] = {}
    for code, (_, names) in CURRENCIES.items():
        for b in names:
            bare.setdefault(b, set()).add(code)
    for b, codes in bare.items():
        pat = re.compile(_WORD_EDGE_L + re.escape(b) + r"s?" + _WORD_EDGE_R)
        if not pat.search(text):
            continue
        mine = codes & {base, quote}
        if b in AMBIGUOUS_BARE:
            if mine:
                return None
            continue
        if len(mine) == 1:
            named.update(mine)
        elif not mine:
            named.add("THIRD")
        else:
            return None
        text = pat.sub(" | ", text)

    if named - {base, quote}:
        return None
    if own:
        return (text, 1) if not named else None
    if named == {base}:
        return text, 1
    if named == {quote}:
        return text, -1
    return None


# Subjects (brain.md rule 93). A headline's verb belongs to the noun that opens its clause, and the word
# list was reading every directional word as if it described the asset the headline was stored against:
# "Fauji Fertilizer jumps after Engro plant shutdown" scored positive for Engro, "Solana tumbles as
# traders rotate into Bitcoin" negative for Bitcoin, "Consumer optimism slides" negative for the
# Optimism token. A headline now takes a side for an asset only through a clause that **opens with
# the asset** -- its name or its ticker -- and only the directional words in that clause count. For a
# currency pair the clause must open with one of the pair's currencies (or the pair), and `orient`
# then signs it. Everything else takes no side: a word list cannot tell which noun a verb in another
# clause belongs to, and no side costs less than the wrong one.
#
# Clauses split on the joining words that start a second subject ("as", "after", "while", "amid" ...)
# and on clause punctuation. A comma splits only when followed by a space, so "36,000" stays a number.
_CLAUSE_SPLIT = re.compile(
    r"\s+(?:as|after|while|but|amid|despite|though|although|when|because|since|following|whereas|"
    r"before|until|unless|if|even as|vs\.?|versus)\s+|,\s+|[;:|?!]|\s[-\u2013\u2014]\s",
    re.I,
)
# What may stand before the subject at the start of a clause without being a subject of its own.
_LEAD = re.compile(r"^[\s\"'\u2018\u2019\u201c\u201d]*(?:(?:the|and|shares of|stock of|stocks of)\s+)?", re.I)


def clauses(title: str) -> list[str]:
    """The headline's clauses, each with its leading article or conjunction removed."""
    return [_LEAD.sub("", c).strip() for c in _CLAUSE_SPLIT.split(title or "") if c and c.strip()]


# Corporate suffixes dropped from a stored name before it is matched: headlines say "Engro", not
# "Engro Corporation Limited".
_SUFFIX = re.compile(
    r"(?:[,.]?\s+(?:inc|incorporated|corp|corporation|co|company|ltd|limited|plc|llc|lp|holdings?|group|"
    r"sa|ag|nv|se|adr|etf|trust|class\s+[a-c]|common\s+stock|ordinary\s+shares|shares))+\.?$",
    re.I,
)
# First words too common to stand for one company at the start of a headline.
_GENERIC_FIRST = frozenset({
    "bank", "first", "national", "united", "american", "general", "international", "global", "pakistan",
    "new", "state", "china", "standard", "capital", "energy", "power", "digital", "world", "south",
    "north", "east", "west", "us", "the", "gold", "silver", "oil", "natural", "crude", "royal", "federal",
})


def subject_names(name: str, symbol: str, asset_type: str, unique_first: set[str] | None = None) -> list[re.Pattern[str]]:
    """The patterns that name this asset at the start of a clause: its stored name, the name without
    corporate suffixes, its first word when no other asset's name starts with it, and its ticker in
    capitals (three letters at least for a coin, two for a listed share)."""
    pats: list[re.Pattern[str]] = []
    names = {n for n in {(name or "").strip(), _SUFFIX.sub("", (name or "").strip()).strip()} if len(n) >= 3}
    first = (_SUFFIX.sub("", (name or "").strip()).split() or [""])[0]
    if unique_first is not None and len(first) >= 4 and first.lower() not in _GENERIC_FIRST and first.lower() in unique_first:
        names.add(first)
    for n in sorted(names, key=len, reverse=True):
        pats.append(re.compile(re.escape(n) + r"(?:'s|\u2019s)?" + _WORD_EDGE_R, re.I))
    raw = (symbol or "").strip()
    ticker = raw.split("-")[0].upper() if asset_type == "crypto" else raw.upper()
    if re.fullmatch(r"[A-Z][A-Z0-9.]{1,9}", ticker) and len(ticker) >= (3 if asset_type == "crypto" else 2):
        pats.append(re.compile(re.escape(ticker) + r"(?![A-Za-z0-9])"))
    return pats


def _starts_with_currency(clause: str) -> bool:
    """Whether a clause opens with a currency: a pair token, a code in capitals, or a currency name."""
    if re.match(r"[A-Za-z]{3}[/-]?[A-Za-z]{3}(?![A-Za-z])", clause) and clause[:3].upper() in CURRENCIES:
        return True
    if re.match(r"(?:" + "|".join(CURRENCIES) + r")(?![A-Za-z])", clause):
        return True
    low = clause.lower()
    for code, (quals, bares) in CURRENCIES.items():
        for n in (*quals, *bares):
            if re.match(re.escape(n) + r"s?" + _WORD_EDGE_R, low):
                return True
    return False


def _kind(text: str, sign: int) -> str:
    up = count_words(text, POSITIVE_TERMS)
    down = count_words(text, NEGATIVE_TERMS)
    if up and down:
        return "neutral"
    if up:
        return "positive" if sign > 0 else "negative"
    if down:
        return "negative" if sign > 0 else "positive"
    return "neutral"


def classify(title: str, pair: tuple[str, str] | None = None,
             subject: list[re.Pattern[str]] | None = None) -> str:
    """positive, negative or neutral for one headline, for the asset it was stored against.

    A headline carrying both directions is neutral rather than assigned to whichever side
    has more matches. "Revenue beats but guidance misses" is genuinely both, and picking a
    winner on match count would be inventing a judgement the wording does not support.

    `pair` is set for a currency pair and `subject` for any other asset: then only clauses that
    open with the pair's currencies (signed by `orient`) or with the asset (`subject_names`) count,
    and clauses that disagree cancel. With neither, the whole headline is read, as it always was --
    for the products this job also reads, which no decision uses.
    """
    if pair is None and subject is None:
        return _kind(title, 1)
    kinds: set[str] = set()
    for clause in clauses(title):
        if pair is not None:
            if not _starts_with_currency(clause):
                continue
            oriented = orient(clause, pair)
            if oriented is None:
                continue
            text, sign = oriented
        else:
            m = next((m for m in (pat.match(clause) for pat in subject or []) if m), None)
            if not m:
                continue
            text, sign = clause[m.end():], 1
        k = _kind(text, sign)
        if k != "neutral":
            kinds.add(k)
    return kinds.pop() if len(kinds) == 1 else "neutral"


def news_windows(cur, column: str, start: datetime, end: datetime) -> dict[str, list[dict]]:
    """{targetId: the stored items in [start, end)} for every target at once.

    This was one statement per target per window, and `read_target` asks for two windows, so
    361 targets cost 722 network waits to read a table that fits in one. The rows returned
    per target are the same rows, with the same columns, as the per-target version returned.
    """
    out: dict[str, list[dict]] = {}
    for r in rows(
        cur,
        f"""
        SELECT "{column}" AS target, title, publisher, "lineageId", "publishedAt"
        FROM "News"
        WHERE "{column}" IS NOT NULL AND "publishedAt" >= %s AND "publishedAt" < %s
        """,
        (start, end),
    ):
        out.setdefault(r["target"], []).append(r)
    return out


def base_closes(cur, on) -> dict[str, dict]:
    """{assetId: the newest stored close at or before `on`}, in one statement.

    Returned as stored rather than carried forward to the asking date, exactly as the
    per-asset version did, so the accuracy log still records which observation a later move
    was measured from.
    """
    return {r["assetId"]: r for r in rows(
        cur,
        """
        SELECT DISTINCT ON ("assetId") "assetId", date, close FROM "PriceSnapshot"
        WHERE date <= %s AND close IS NOT NULL
        ORDER BY "assetId", date DESC
        """,
        (on,),
    )}


def stories(items: list[dict]) -> int:
    """Distinct stories in a window, not items.

    An item with no lineage yet counts as its own story rather than being dropped: the
    alternative is undercounting everything collected since lineage.py last ran, which would
    silence exactly the newest information.
    """
    seen: set[str] = set()
    loose = 0
    for it in items:
        lid = it.get("lineageId")
        if lid:
            seen.add(lid)
        else:
            loose += 1
    return len(seen) + loose


def robust_z(recent_rate: float, daily_counts: list[float]) -> float | None:
    """(x - median) / (1.4826 * MAD), or None when the baseline cannot support it.

    Used instead of a ratio against a mean because a news feed reliably produces one busy
    day, and a mean baseline carries that day into every comparison afterwards. The median
    and the MAD do not, which is the entire reason to prefer them here. The 1.4826 makes the
    MAD comparable to a standard deviation for normal data; the data is not normal, which is
    why this is a robust deviation score and not a p-value.
    """
    if len(daily_counts) < 7:
        return None
    ordered = sorted(daily_counts)
    mid = len(ordered) // 2
    med = (
        ordered[mid]
        if len(ordered) % 2
        else (ordered[mid - 1] + ordered[mid]) / 2
    )
    devs = sorted(abs(c - med) for c in daily_counts)
    dmid = len(devs) // 2
    mad = devs[dmid] if len(devs) % 2 else (devs[dmid - 1] + devs[dmid]) / 2
    scale = 1.4826 * mad
    if scale <= 0:
        # A feed that published exactly the same amount every day gives MAD 0. Dividing would
        # return infinity for one extra item, so a floor of half an item a day is used and
        # the result stays finite and interpretable.
        scale = 0.5
    return (recent_rate - med) / scale


def grade(items: int, publishers: int, top_share: float | None) -> tuple[str, list[str]]:
    """How well evidenced the reading is. About the evidence, never about the direction."""
    notes: list[str] = []
    if items < MIN_ITEMS:
        return "none", [
            f"Only {items} headlines in the window, below the {MIN_ITEMS} needed to read a "
            "direction, so the counts are stored and no tone is published"
        ]

    if items >= HIGH_ITEMS and publishers >= HIGH_PUBLISHERS:
        g = "high"
    elif items >= MEDIUM_ITEMS and publishers >= MEDIUM_PUBLISHERS:
        g = "medium"
    else:
        g = "low"
        notes.append(
            f"{items} headlines from {publishers} publishers, which is thin enough that the "
            "direction rests on a handful of items"
        )

    # Principle 1 again. Volume from one publisher is one source however large it is.
    if top_share is not None and top_share > DOMINANT_PUBLISHER_LIMIT and g == "high":
        g = "medium"
        notes.append(
            f"one publisher supplied {top_share * 100:.0f}% of the headlines, so this "
            "describes that publisher's coverage more than the coverage as a whole"
        )
    elif top_share is not None and top_share > DOMINANT_PUBLISHER_LIMIT:
        notes.append(
            f"one publisher supplied {top_share * 100:.0f}% of the headlines"
        )

    return g, notes


def read_target(cur, column: str, target_id: str, name: str, end: date,
                recent: dict, earlier: dict, pair: tuple[str, str] | None = None,
                subject: list[re.Pattern[str]] | None = None):
    """Compute one target's reading. Returns None when the target has no coverage at all.

    `recent` and `earlier` are the two windows, read once for every target by `news_windows`
    and handed in. Everything below is the arithmetic it always was. `pair` is the two
    currency codes when the target is a currency pair, so each headline is signed for the pair
    (`classify`).
    """
    end_dt = datetime.combine(end, datetime.min.time())
    items = recent.get(target_id, [])
    prior = earlier.get(target_id, [])
    # Every window this function needs is a slice of those two, so the catalyst and baseline
    # windows are taken from the rows already in hand rather than asked for again. They always
    # were slices: the catalyst window is the last CATALYST_DAYS of `items`, and the baseline
    # window spans the end of `prior` and the start of `items`. Four statements per target
    # became two for the whole universe.
    window = items + prior

    if not items and not prior:
        return None

    positive = negative = neutral = 0
    hype_items = 0
    publishers: dict[str, int] = {}
    for r in items:
        title = r["title"] or ""
        kind = classify(title, pair, subject)
        if kind == "positive":
            positive += 1
        elif kind == "negative":
            negative += 1
        else:
            neutral += 1
        if count_terms(title, HYPE_TERMS):
            hype_items += 1
        p = (r["publisher"] or "unknown").strip()
        publishers[p] = publishers.get(p, 0) + 1

    n = len(items)
    top_share = (max(publishers.values()) / n) if n else None

    # Published whenever there is anything at all to read, and labelled when it is thin.
    # Withholding it was over-filtering: being early means reading weak evidence, not
    # refusing to.
    tone = None
    tone_score = None
    if n:
        # Among the headlines that expressed a direction, not among all of them. See
        # MIN_TONE_ITEMS for the measurement that forced this: dividing by `items` made the bar
        # rise with coverage, so the best covered names were the least able to register a tone.
        opinionated = positive + negative
        tone_score = (positive - negative) / opinionated if opinionated else 0.0
        if opinionated < MIN_TONE_ITEMS:
            # Not enough headlines took a side to call it. Distinct from a balanced window, and
            # the counts stored beside this say which of the two it was.
            tone = "neutral"
        elif tone_score > NEUTRAL_BAND:
            tone = "positive"
        elif tone_score < -NEUTRAL_BAND:
            tone = "negative"
        else:
            tone = "neutral"

    # Attention. Null rather than zero when the prior window is too thin to divide by: a
    # missing comparison is not a finding of no change.
    velocity = None
    attention = "unknown"
    if len(prior) >= MIN_PRIOR_ITEMS:
        velocity = pct(float(n), float(len(prior)))
        if velocity is not None:
            if velocity >= ATTENTION_BAND:
                attention = "rising"
            elif velocity <= -ATTENTION_BAND:
                attention = "falling"
            else:
                attention = "flat"

    # Catalyst: the short window against the long window's daily rate. Measured on the same
    # stored rows, but answering a different question from velocity, so both are kept.
    catalyst_from = end_dt - timedelta(days=CATALYST_DAYS)
    base_from = end_dt - timedelta(days=WINDOW_DAYS + CATALYST_DAYS)
    base_to = catalyst_from
    recent = [it for it in window if catalyst_from <= it["publishedAt"] < end_dt]
    baseline_items = [it for it in window if base_from <= it["publishedAt"] < base_to]

    recent_n = len(recent)
    # Stories, not items. This is the number the decision is made on: a ratio built on copies
    # measures syndication, which is a fact about the news industry and not about the asset.
    recent_stories = stories(recent)
    baseline_stories = stories(baseline_items)

    baseline_daily = None
    baseline_story_daily = None
    spike = None
    rz = None
    change_kind = "none"
    catalyst = False
    catalyst_note = None

    if len(baseline_items) >= MIN_BASELINE_ITEMS:
        baseline_daily = len(baseline_items) / WINDOW_DAYS
        baseline_story_daily = baseline_stories / WINDOW_DAYS
        if baseline_story_daily > 0:
            spike = (recent_stories / CATALYST_DAYS) / baseline_story_daily

        # Daily story counts across the baseline, for the robust deviation. Built from the
        # rows already fetched rather than with another query.
        per_day: dict[date, list[dict]] = {}
        for it in baseline_items:
            per_day.setdefault(it["publishedAt"].date(), []).append(it)
        daily = [float(stories(v)) for v in per_day.values()]
        # Days the feed published nothing are real zeros in the rate, so they are included
        # rather than skipped — leaving them out would raise the baseline and hide spikes.
        daily += [0.0] * max(0, WINDOW_DAYS - len(per_day))
        rz = robust_z(recent_stories / CATALYST_DAYS, daily)

        # Spike against persistent change. A loud afternoon and a fortnight of steadily
        # heavier coverage are different events, and only the second one has moved the
        # baseline the next comparison will be made against.
        recent_half = stories(
            [it for it in baseline_items if it["publishedAt"] >= base_to - timedelta(days=10)]
        ) / 10.0
        if rz is not None and rz >= CATALYST_Z:
            change_kind = (
                "persistent"
                if baseline_story_daily and recent_half >= 1.5 * baseline_story_daily
                else "spike"
            )

        # Both tests have to agree. The ratio catches a jump off a quiet baseline and the
        # robust score refuses one that is ordinary variation for this feed; requiring both
        # is what keeps a flag from being either a wire pickup or a busy Tuesday.
        catalyst = bool(
            spike is not None
            and spike >= CATALYST_RATIO
            and rz is not None
            and rz >= CATALYST_Z
        )

    if catalyst:
        copies = ""
        if recent_n > recent_stories:
            copies = (
                f" The {recent_stories} stories arrived as {recent_n} items, so some of it is "
                "the same report carried more than once"
            )
        catalyst_note = (
            f"{recent_stories} distinct stories in the last {CATALYST_DAYS} days, about "
            f"{spike:.1f} times the {baseline_story_daily:.2f} a day of the {WINDOW_DAYS} "
            f"before, and {rz:.1f} robust deviations above this feed's own median. "
            f"Read as a {change_kind}.{copies}. What arrived is in the headlines below; this "
            "flag counts stories and does not read them"
        )
    elif recent_n and baseline_daily is None:
        catalyst_note = (
            f"{recent_n} items in the last {CATALYST_DAYS} days, but the {WINDOW_DAYS} days "
            f"before hold fewer than {MIN_BASELINE_ITEMS}, which is too thin to be a rate. No "
            "spike is reported rather than one measured against almost nothing"
        )
    elif spike is not None and spike >= CATALYST_RATIO and (rz is None or rz < CATALYST_Z):
        catalyst_note = (
            f"the recent story rate is {spike:.1f} times the baseline, but only {rz:.1f} "
            "robust deviations above this feed's own median, which is ordinary variation for "
            "it. No catalyst is flagged on the ratio alone"
        )

    hype_share = (hype_items / n) if n else None
    hype_flag = bool(
        attention == "rising" and hype_share is not None and hype_share >= HYPE_SHARE_LIMIT
    )
    hype_note = None
    if hype_flag:
        hype_note = (
            f"{hype_items} of {n} headlines use promotional wording while coverage is "
            "rising. This describes how the story is being written, not the asset: heavily "
            "promoted and overvalued are different claims and only the first is measured here"
        )
    elif hype_share is not None and hype_share >= HYPE_SHARE_LIMIT:
        hype_note = (
            f"{hype_items} of {n} headlines use promotional wording, but coverage is not "
            "rising, so this reads as house style rather than a surge"
        )

    g, notes = grade(n, len(publishers), top_share)
    if catalyst:
        notes.append(
            "a catalyst is flagged, which is a count of recent items and not a reading of "
            "what they say"
        )
    if tone is not None and positive and negative and abs(tone_score) <= NEUTRAL_BAND:
        notes.append(
            f"{positive} headlines worded positively against {negative} negatively, which "
            "is a split rather than a direction"
        )

    return {
        "items": n,
        "positive": positive,
        "negative": negative,
        "neutral": neutral,
        "tone": tone,
        "toneScore": tone_score,
        "priorItems": len(prior),
        "recentItems": recent_n,
        "baselineDaily": baseline_daily,
        "spikeRatio": spike,
        "catalyst": catalyst,
        "catalystNote": catalyst_note,
        "recentStories": recent_stories,
        "baselineStoryDaily": baseline_story_daily,
        "robustZ": rz,
        "changeKind": change_kind,
        "velocityPct": velocity,
        "attention": attention,
        "hypeTerms": hype_items,
        "hypeShare": hype_share,
        "hypeFlag": hype_flag,
        "hypeNote": hype_note,
        "confidence": g,
        "confidenceNote": "; ".join(notes).capitalize() if notes else None,
        "publishers": len(publishers),
        "name": name,
    }


def claim_text(r: dict, end: date) -> str:
    """The reading in plain observational English. No future tense, by construction."""
    bits = [
        f"Coverage of {r['name']} in the {WINDOW_DAYS} days to {end.isoformat()}: "
        f"{r['items']} headlines from {r['publishers']} publishers, "
        f"{r['positive']} worded positively and {r['negative']} negatively."
    ]
    if r["priorItems"] >= MIN_PRIOR_ITEMS and r["velocityPct"] is not None:
        bits.append(
            f"That is {r['velocityPct']:+.0f}% against {r['priorItems']} headlines in the "
            f"{WINDOW_DAYS} days before, so attention is {r['attention']}."
        )
    else:
        bits.append(
            f"The {WINDOW_DAYS} days before hold {r['priorItems']} headlines, too few to "
            "compare against, so no change in attention is reported."
        )
    if r["tone"] is None:
        bits.append("No headlines are stored, so there is no wording to read.")
    elif r["items"] < MIN_ITEMS:
        bits.append(
            f"Net wording reads {r['tone']} on {r['items']} headlines, which is thin: it is "
            "reported so it can be seen early, not because it is well evidenced."
        )
    else:
        bits.append(f"Net wording reads {r['tone']}.")
    if r["catalyst"]:
        bits.append(
            f"{r['recentItems']} items arrived in the last {CATALYST_DAYS} days against a "
            f"baseline of {r['baselineDaily']:.2f} a day, so something recent is being "
            "written about that was not before."
        )
    if r["hypeFlag"]:
        bits.append("Promotional wording is rising with the coverage.")
    bits.append(
        "Counted from a fixed word list over headlines only, which cannot see negation or "
        "context."
    )
    return " ".join(bits)


def factors_text(r: dict) -> str:
    return (
        f"items={r['items']}; publishers={r['publishers']}; "
        f"positive={r['positive']}; negative={r['negative']}; neutral={r['neutral']}; "
        f"toneScore={'' if r['toneScore'] is None else format(r['toneScore'], '.3f')}; "
        f"priorItems={r['priorItems']}; "
        f"velocityPct={'' if r['velocityPct'] is None else format(r['velocityPct'], '.1f')}; "
        f"attention={r['attention']}; hypeTerms={r['hypeTerms']}; "
        f"hypeFlag={'yes' if r['hypeFlag'] else 'no'}; "
        f"recentItems={r['recentItems']}; "
        f"spikeRatio={'' if r['spikeRatio'] is None else format(r['spikeRatio'], '.2f')}; "
        f"catalyst={'yes' if r['catalyst'] else 'no'}; window={WINDOW_DAYS}d"
    )


def signal_row(column: str, target_id: str, r: dict, end: date) -> tuple[str, tuple]:
    other = "productId" if column == "assetId" else "assetId"
    return (
        f"""
        INSERT INTO "HumanSignal" ("{column}", "{other}", "targetRef", "periodEnd",
            "windowDays", items, positive, negative, neutral, tone, "toneScore",
            "priorItems", "velocityPct", attention, "recentItems", "baselineDaily",
            "spikeRatio", catalyst, "catalystNote", "recentStories", "baselineStoryDaily",
            "robustZ", "changeKind", "hypeTerms", "hypeShare", "hypeFlag",
            "hypeNote", confidence, "confidenceNote", source, "computedAt")
        VALUES (
            %s, NULL, %s, %s, %s,                       -- target, other, ref, period, window
            %s, %s, %s, %s, %s::"Tone", %s,             -- items, pos, neg, neu, tone, score
            %s, %s, %s,                                 -- priorItems, velocity, attention
            %s, %s, %s, %s, %s,                         -- recent, baseline, spike, catalyst, note
            %s, %s, %s, %s,                             -- stories, storyDaily, robustZ, change
            %s, %s, %s, %s,                             -- hypeTerms, hypeShare, hypeFlag, note
            %s::"Confidence", %s, %s, now()             -- confidence, note, source, computedAt
        )
        ON CONFLICT ("targetRef", "periodEnd", "windowDays") DO UPDATE SET
            items = EXCLUDED.items, positive = EXCLUDED.positive,
            negative = EXCLUDED.negative, neutral = EXCLUDED.neutral,
            tone = EXCLUDED.tone, "toneScore" = EXCLUDED."toneScore",
            "priorItems" = EXCLUDED."priorItems", "velocityPct" = EXCLUDED."velocityPct",
            attention = EXCLUDED.attention, "recentItems" = EXCLUDED."recentItems",
            "baselineDaily" = EXCLUDED."baselineDaily",
            "spikeRatio" = EXCLUDED."spikeRatio", catalyst = EXCLUDED.catalyst,
            "catalystNote" = EXCLUDED."catalystNote",
            "recentStories" = EXCLUDED."recentStories",
            "baselineStoryDaily" = EXCLUDED."baselineStoryDaily",
            "robustZ" = EXCLUDED."robustZ", "changeKind" = EXCLUDED."changeKind",
            "hypeTerms" = EXCLUDED."hypeTerms",
            "hypeShare" = EXCLUDED."hypeShare", "hypeFlag" = EXCLUDED."hypeFlag",
            "hypeNote" = EXCLUDED."hypeNote", confidence = EXCLUDED.confidence,
            "confidenceNote" = EXCLUDED."confidenceNote", "computedAt" = now()
        """,
        (
            target_id, target_id, end, WINDOW_DAYS, r["items"], r["positive"],
            r["negative"], r["neutral"], r["tone"], r["toneScore"], r["priorItems"],
            r["velocityPct"], r["attention"], r["recentItems"], r["baselineDaily"],
            r["spikeRatio"], r["catalyst"], r["catalystNote"], r["recentStories"],
            r["baselineStoryDaily"], r["robustZ"], r["changeKind"], r["hypeTerms"],
            r["hypeShare"], r["hypeFlag"], r["hypeNote"], r["confidence"],
            r["confidenceNote"], "Google News RSS, as stored in News",
        ),
    )


def log_row(column: str, target_id: str, r: dict, end: date, base) -> tuple[str, tuple]:
    """Record the reading so accuracy.py can measure what followed it.

    A reading with no published direction is still logged. Whether quiet, split coverage is
    followed by anything is exactly the sort of question this table exists to answer, and
    logging only the confident readings would make the eventual hit rate flattering.
    """
    other = "productId" if column == "assetId" else "assetId"
    status = "open" if base else "unmeasurable"
    return (
        f"""
        INSERT INTO "SignalLog" (kind, "{column}", "{other}", "targetRef", "issuedOn",
            claim, factors, confidence, "baseDate", "baseClose", status)
        VALUES ('humanSignal', %s, NULL, %s, %s, %s, %s, %s::"Confidence", %s, %s, %s)
        ON CONFLICT (kind, "targetRef", "issuedOn") DO UPDATE SET
            claim = EXCLUDED.claim, factors = EXCLUDED.factors,
            confidence = EXCLUDED.confidence, "baseDate" = EXCLUDED."baseDate",
            "baseClose" = EXCLUDED."baseClose"
        """,
        (
            target_id, target_id, end, claim_text(r, end), factors_text(r),
            r["confidence"], base["date"] if base else None,
            base["close"] if base else None, status,
        ),
    )


def main() -> None:
    end = date.today()
    conn = db()
    with conn, conn.cursor() as cur:
        for column, table, label in (
            ("assetId", "Asset", "assets"),
            ("productId", "Product", "products"),
        ):
            step(f"human signal for {label}")
            # A currency pair's headlines are signed for the pair, so its symbol is read with it.
            extra = ', symbol, "assetType"::text AS "assetType"' if table == "Asset" else ""
            targets = rows(cur, f'SELECT id, name{extra} FROM "{table}" ORDER BY name')
            # Three statements for the whole group, taken before the loop: the two news
            # windows every target is read over, and the base closes the log is anchored to.
            end_dt = datetime.combine(end, datetime.min.time())
            start_dt = end_dt - timedelta(days=WINDOW_DAYS)
            prior_dt = start_dt - timedelta(days=WINDOW_DAYS)
            recent = news_windows(cur, column, start_dt, end_dt)
            earlier = news_windows(cur, column, prior_dt, start_dt)
            bases = base_closes(cur, end) if column == "assetId" else {}

            written = skipped = flagged = sparked = thin = 0
            signal_sql = log_sql = None
            signal_payload: list[tuple] = []
            log_payload: list[tuple] = []
            # A first word stands for an asset only when no other asset's name starts with it.
            firsts: dict[str, int] = {}
            for t in targets:
                f = (_SUFFIX.sub("", (t["name"] or "").strip()).split() or [""])[0].lower()
                firsts[f] = firsts.get(f, 0) + 1
            unique_first = {f for f, n in firsts.items() if n == 1}
            for t in targets:
                forex = t.get("assetType") == "forex"
                pair = fx_pair(t["symbol"]) if forex else None
                subject = (
                    subject_names(t["name"], t["symbol"], t["assetType"], unique_first)
                    if column == "assetId" and not forex
                    else None
                )
                r = read_target(cur, column, t["id"], t["name"], end, recent, earlier, pair, subject)
                if r is None:
                    skipped += 1
                    continue
                signal_sql, params = signal_row(column, t["id"], r, end)
                signal_payload.append(params)
                log_sql, params = log_row(column, t["id"], r, end, bases.get(t["id"]))
                log_payload.append(params)
                written += 1
                if r["hypeFlag"]:
                    flagged += 1
                if r["catalyst"]:
                    sparked += 1
                if r["items"] and r["items"] < MIN_ITEMS:
                    thin += 1

            # One statement per table rather than two per target. The conflict clauses are
            # unchanged, so a rerun on the same day is still an update.
            if signal_payload:
                cur.executemany(signal_sql, signal_payload)
            if log_payload:
                cur.executemany(log_sql, log_payload)
            print(
                f"  {label}: {written} read, {skipped} with no stored coverage, "
                f"{sparked} catalyst flagged, {flagged} hype flagged, "
                f"{thin} published as thin"
            )


if __name__ == "__main__":
    main()
