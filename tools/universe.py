"""Propose additions to the crypto and PSX universes, by stated criteria. Read-only.

Writes nothing, to the database or to `jobs/seed.py`. It prints what it would add, and **why it
refused each of the others**, so the list can be read and argued with before any of it is pasted
into the seed. The universe lives in version control and not in the database for the reason every
other reference row does: a name that exists only because a tool inserted it once is a name no
review ever saw.

Why this is a filter and not "add everything"
---------------------------------------------
The Pakistan Stock Exchange's daily file lists about 1,000 symbols and this project follows 157.
The 863 it does not follow look like stocks and mostly are not. Measured 2026-10-10, the most
heavily "traded" unseeded lines are government securities (`P03GHS151026`, "3 Month GHS", Rs 2.2
trillion of face value on a day) and monthly futures contracts (`PRL-OCT`, `OGDC-OCTB`) -- the
first priced as a bond and the second a derivative of a share this project already holds. Fed to
a rule table that reads a 20/50 day average stack, either one would produce confident nonsense,
and the futures would duplicate their own underlying under a second name. So the question is never
"what is listed" but "what is an ordinary share, that trades, in a sector this project already
has".

The same shape on the crypto side. The top of a market-cap ranking is stablecoins, wrapped and
staked copies of a coin that is already followed, and bridged tokens; none is an independent
reading, and a stablecoin's 20/50 day stack is a measurement of nothing.

Run: python tools/universe.py [crypto|psx|all] [--top N] [--emit]
     --emit    also print the accepted rows as `jobs/seed.py` tuples, ready to review and paste.
"""

from __future__ import annotations

import re
import statistics
import sys
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "jobs"))

# --- crypto -------------------------------------------------------------------------------------

# How far down the ranking is looked at. The tail beyond this is thin enough that its daily bars
# are mostly one venue's noise, and every coin added is a series stored for good.
CRYPTO_TOP = 150

# A series shorter than this cannot feed the legs that need history: the analog matcher compares
# today against the past, and the squeeze reading wants 160 sessions on its own. A year is the
# floor below which a coin would sit in WAIT for want of data and add rows for nothing.
CRYPTO_MIN_HISTORY_DAYS = 365

# Stablecoins, named. The peg check below is the backstop and this list is the first line, because
# a de-pegged stablecoin passes any numeric test for exactly the days it matters.
STABLES = frozenset(
    "USDT USDC DAI BUSD TUSD USDD FDUSD USDE PYUSD USDS FRAX GUSD LUSD USDP EURC EURT USD1 "
    "USDX USDG RLUSD BFUSD USDY SUSDE SUSDS USDF USDT0 CRVUSD GHO USDB".split()
)
# Wrapped, staked and bridged copies of a coin the universe already follows or could. They move
# with their underlying by construction, so they are the same reading twice and every one of them
# would count as an independent confirmation in the peer leg.
DERIVATIVE_SYMBOLS = frozenset(
    "WBTC WETH STETH WSTETH WEETH CBBTC CBETH RETH WBETH JITOSOL MSOL BNSOL SOLVBTC LBTC "
    "EETH EZETH RSETH WSOL ETHX SFRXETH TBTC KBTC FBTC USDTB BTCB "
    # Gold-backed tokens. They track the metal, which this project already follows as a futures
    # contract and as funds, so each is the same reading a third time.
    "PAXG XAUT KAU KAG".split()
)
DERIVATIVE_NAME = re.compile(
    r"wrapped|staked|staking|restaked|liquid|bridged|peg\b|binance-peg|coinbase wrapped|"
    r"lido|rocket pool|ether\.fi|renzo|kelp",
    re.IGNORECASE,
)

# Dollars traded in the last 24 hours. A bridged or abandoned copy of a real coin keeps a ranking
# and a price and trades almost nothing: `TONToken` ranks 135th and moved $0.1m against the real
# Toncoin's $42.8m, so its close is whichever stray order printed last.
CRYPTO_MIN_VOLUME_24H = 1_000_000

# A stablecoin trades within a cent of a dollar for months. Wider than a day's move on any real
# asset and tighter than any real asset's month.
PEG_BAND = (0.97, 1.03)
PEG_MAX_30D_MOVE_PCT = 2.0


def crypto_reject_reason(
    t: dict,
    *,
    seeded_ids: set[str],
    coinbase_usd: set[str],
    binance_usdt: set[str],
    today: date,
) -> str | None:
    """Why this ticker is not proposed, or None when it is. Pure: no network, no clock."""
    sym = str(t.get("symbol", "")).upper()
    name = str(t.get("name", ""))
    rank = t.get("rank")
    if not rank or rank > CRYPTO_TOP:
        return f"rank {rank} is past the top {CRYPTO_TOP}"
    if t.get("id") in seeded_ids:
        return "already followed"
    if sym in STABLES:
        return "a stablecoin"
    q = (t.get("quotes") or {}).get("USD") or {}
    price = q.get("price")
    move30 = q.get("percent_change_30d")
    if (
        price is not None
        and PEG_BAND[0] <= price <= PEG_BAND[1]
        and move30 is not None
        and abs(move30) <= PEG_MAX_30D_MOVE_PCT
    ):
        return f"holds ${price:.3f} within {PEG_MAX_30D_MOVE_PCT}% over 30 days, which is a peg"
    if sym in DERIVATIVE_SYMBOLS or DERIVATIVE_NAME.search(name):
        return "a wrapped, staked or bridged copy of another asset"
    # Coinbase specifically, and Binance is not an acceptable substitute. Binance stopped answering
    # from GitHub's runners on 2026-09-29 while answering normally from a laptop, so a coin it alone
    # carries would be fetched and stored on a developer's machine and then silently never updated
    # in production -- the failure that left every crypto close stale for a week. Coinbase is the
    # venue that answered from the runners, and it is what `fetch_crypto` falls through to.
    if sym not in coinbase_usd:
        carried = " (Binance carries it, which is geo-blocked from the CI runners)" if sym in binance_usdt else ""
        return f"no USD daily pair on Coinbase{carried}"
    volume = q.get("volume_24h")
    if volume is None or volume < CRYPTO_MIN_VOLUME_24H:
        return f"24h volume {volume} is under ${CRYPTO_MIN_VOLUME_24H:,}: too thin to be a reading"
    first = t.get("first_data_at")
    if not first:
        return "no recorded start of history"
    try:
        started = datetime.fromisoformat(str(first).replace("Z", "+00:00")).date()
    except ValueError:
        return f"unreadable history start {first!r}"
    if (today - started).days < CRYPTO_MIN_HISTORY_DAYS:
        return f"only {(today - started).days} days of history, under {CRYPTO_MIN_HISTORY_DAYS}"
    return None


# How far a venue's last price may sit from CoinPaprika's before the two are treated as naming
# different assets. A ticker is not an identity: `GRAM` and `TON` are both live in the ranking, and
# the same ticker has been two different coins on two sources before. A wrong mapping would store
# one coin's prices under another's name, silently, for good.
PRICE_AGREES_WITHIN = 0.15


def prices_agree(paprika: float | None, venue: float | None) -> bool:
    """Do two quotes plausibly describe the same asset? False when either is missing or non-positive."""
    if paprika is None or venue is None or paprika <= 0 or venue <= 0:
        return False
    return abs(venue / paprika - 1.0) <= PRICE_AGREES_WITHIN



def crypto_report(top: int = CRYPTO_TOP, emit: bool = False, verbose: bool = False) -> int:
    from nbt import get_json  # noqa: PLC0415 - kept local so the pure half needs no network

    import seed  # noqa: PLC0415

    today = datetime.now(timezone.utc).date()
    tickers = get_json("https://api.coinpaprika.com/v1/tickers?quotes=USD", cache_key="universe-paprika-tickers", ttl=3600)
    cb = get_json("https://api.exchange.coinbase.com/products", cache_key="universe-coinbase-products", ttl=3600) or []
    bn = (get_json("https://api.binance.com/api/v3/exchangeInfo", cache_key="universe-binance-info", ttl=3600) or {}).get("symbols", [])
    if not tickers:
        print("CoinPaprika answered nothing; no proposal can be made.")
        return 1
    coinbase_usd = {
        p["base_currency"].upper()
        for p in cb
        if p.get("quote_currency") == "USD" and p.get("status") == "online" and not p.get("trading_disabled")
    }
    binance_usdt = {
        s["baseAsset"].upper() for s in bn if s.get("quoteAsset") == "USDT" and s.get("status") == "TRADING"
    }
    # By source and not by list name: `seed.ASSETS` is built from a dozen appended batches
    # (`MORE_CRYPTO`, `MORE_CRYPTO_2`, ...) and reading one of them would undercount what is
    # already followed and propose names the seed holds.
    seeded_ids = {row[6] for row in seed.ASSETS if row[5] == seed.PAPRIKA}

    accepted, reasons = [], Counter()
    ranked = sorted((t for t in tickers if t.get("rank")), key=lambda t: t["rank"])[:top]

    def venue_price(sym: str) -> float | None:
        """The last price on whichever venue answers, Coinbase first."""
        if sym in coinbase_usd:
            got = get_json(f"https://api.exchange.coinbase.com/products/{sym}-USD/ticker", cache_key=f"universe-cb-{sym}", ttl=900)
            if got and got.get("price"):
                return float(got["price"])
        if sym in binance_usdt:
            got = get_json(f"https://api.binance.com/api/v3/ticker/price?symbol={sym}USDT", cache_key=f"universe-bn-{sym}", ttl=900)
            if got and got.get("price"):
                return float(got["price"])
        return None

    for t in ranked:
        why = crypto_reject_reason(
            t, seeded_ids=seeded_ids, coinbase_usd=coinbase_usd, binance_usdt=binance_usdt, today=today
        )
        if why is None:
            quoted = ((t.get("quotes") or {}).get("USD") or {}).get("price")
            seen = venue_price(str(t["symbol"]).upper())
            if not prices_agree(quoted, seen):
                why = (
                    f"venue price {seen} disagrees with CoinPaprika's {quoted}, so the ticker may name "
                    "a different asset"
                )
        if why is None:
            accepted.append(t)
        elif why != "already followed":
            reasons[re.sub(r"[0-9.]+", "N", why)] += 1
            if verbose:
                print(f"  refused {t['rank']:>4} {t['symbol']:8} {why}")
    print(f"crypto: {len(accepted)} proposed from the top {top}; {len(seeded_ids)} already followed. Refused:")
    for why, n in reasons.most_common():
        print(f"   {n:>4}  {why}")
    print()
    for t in accepted:
        print(f"  + {t['rank']:>4} {t['symbol']:8} {t['name']}")
    if emit:
        print("\n# --- paste into jobs/seed.py, in the crypto block ---")
        for t in accepted:
            print(
                f'    ("crypto", "{t["id"]}", "{t["name"]}", "crypto", "marketCap", PAPRIKA, "{t["id"]}", '
                f'"Listed by CoinPaprika at rank {t["rank"]} by market capitalisation."),'
            )
    return 0


# --- PSX ----------------------------------------------------------------------------------------

# Sessions looked back over, and how many of them a symbol must have traded on. A share that
# trades one day in three has a close that is mostly the last trade's price carried, and every leg
# that measures movement would be measuring the carry.
PSX_LOOKBACK_SESSIONS = 60
PSX_MIN_TRADED_SHARE = 0.70
# Median value traded per session, in rupees. Low enough to admit a mid cap and high enough to
# exclude a name whose "volume" is one lot.
PSX_MIN_MEDIAN_VALUE = 1_000_000

# What an ordinary share's symbol looks like. A futures contract is `SYMBOL-OCT` or `SYMBOL-OCTB`
# and a government security begins `P` and a digit pair (`P03GHS151026`, `P01GIS210127`).
ORDINARY = re.compile(r"^[A-Z][A-Z0-9]{1,9}$")
SECURITY = re.compile(r"^P\d\d")
# Where an exchange-published sector code must agree with the project's own filing before a name
# is placed in that sector. A code that maps to two industries is ambiguous and places nothing.
MIN_SECTOR_AGREEMENT = 0.8


MARKER = re.compile(r"(?<=[a-z.])X[DRB]{1,2}$")


def clean_name(name: str) -> str:
    """The exchange's name for a line, minus a trailing corporate-action marker.

    The daily file appends `XD` (ex-dividend), `XR` (ex-rights) or `XB` (ex-bonus) to a name for
    the sessions around the event -- `Ghani ChemworldXR`, `Nishat ChunPowerXD`. That is a state of
    one fortnight and not part of the company's name, so it must not become a permanent asset name.
    Only stripped after a lowercase letter or a dot, so a name that genuinely ends in capitals is
    left alone, and never to nothing.
    """
    cleaned = MARKER.sub("", name.strip())
    return cleaned if cleaned else name.strip()


def is_ordinary_share(symbol: str) -> bool:
    """True for something that looks like a listed share rather than a contract or a bond."""
    s = symbol.strip().upper()
    return bool(ORDINARY.match(s)) and not SECURITY.match(s) and "-" not in s


def sector_map(seeded: dict[str, str], codes: dict[str, str]) -> dict[str, str]:
    """{exchange sector code: project industry slug}, only where the seeded names agree.

    Built from the names this project already files by hand. An exchange code that two of our own
    industries share is not resolved by guessing: it maps to nothing, and the names carrying it
    are listed as unplaced for a person to decide.
    """
    by_code: dict[str, Counter] = {}
    for symbol, slug in seeded.items():
        code = codes.get(symbol)
        if code:
            by_code.setdefault(code, Counter())[slug] += 1
    out: dict[str, str] = {}
    for code, counts in by_code.items():
        slug, n = counts.most_common(1)[0]
        if n / sum(counts.values()) >= MIN_SECTOR_AGREEMENT:
            out[code] = slug
    return out


def psx_report(emit: bool = False) -> int:
    import nbt  # noqa: PLC0415
    import psx  # noqa: PLC0415
    import seed  # noqa: PLC0415

    today = date.today()
    sessions: list[tuple[date, dict[str, dict]]] = []
    for day in reversed(psx.dense_dates(today)):
        raw = nbt.get(psx.file_url(day), cache_key=f"psx-{day.isoformat()}", ttl=psx.ttl_for(day, today))
        text = psx.unpack(raw) if raw else None
        if text is None:
            continue
        rows: dict[str, dict] = {}
        for line in text.splitlines():
            f = line.split("|")
            if len(f) < 10 or not f[1]:
                continue
            try:
                close, volume = float(f[7]), float(f[8])
            except ValueError:
                continue
            rows[f[1].strip().upper()] = {"sec": f[2].strip(), "name": f[3].strip(), "close": close, "volume": volume}
        if rows:
            sessions.append((day, rows))
        if len(sessions) >= PSX_LOOKBACK_SESSIONS:
            break
    if not sessions:
        print("No PSX session files could be read; no proposal can be made.")
        return 1
    newest = sessions[0][1]
    print(f"psx: read {len(sessions)} sessions back from {sessions[0][0]}; {len(newest)} symbols listed")

    # Every batch, by source, for the reason given in `crypto_report`.
    seeded = {row[1].upper(): row[0] for row in seed.ASSETS if row[5] == seed.PSX}
    # Every symbol the project already holds, in any market. An asset page is looked up by symbol
    # alone, so a second `PSX` -- the exchange's own ticker is also Phillips 66 -- would leave one
    # of the two unreachable. A collision is refused rather than renamed: inventing a symbol for a
    # listed company is the kind of small invention this project exists not to make.
    taken = {row[1].upper() for row in seed.ASSETS}
    codes = {sym: v["sec"] for sym, v in newest.items()}
    mapping = sector_map(seeded, codes)

    proposed, refused = [], Counter()
    for sym, v in sorted(newest.items()):
        if sym in seeded:
            continue
        if sym in taken:
            refused["symbol already used by another asset in another market"] += 1
            continue
        if not is_ordinary_share(sym):
            refused["not an ordinary share (a contract or a government security)"] += 1
            continue
        traded = [(rows[sym]["close"] * rows[sym]["volume"]) for _, rows in sessions if sym in rows and rows[sym]["close"] > 0 and rows[sym]["volume"] > 0]
        share = len(traded) / len(sessions)
        if share < PSX_MIN_TRADED_SHARE:
            refused[f"traded on under {PSX_MIN_TRADED_SHARE:.0%} of the last {len(sessions)} sessions"] += 1
            continue
        if statistics.median(traded) < PSX_MIN_MEDIAN_VALUE:
            refused[f"median value traded under Rs {PSX_MIN_MEDIAN_VALUE:,}"] += 1
            continue
        slug = mapping.get(v["sec"])
        if slug is None:
            refused["sector code does not map to one of this project's industries"] += 1
            continue
        proposed.append((slug, sym, v["name"], statistics.median(traded), share))

    print(f"\npsx: {len(proposed)} proposed; {len(seeded)} already followed. Refused, by reason:")
    for why, n in refused.most_common():
        print(f"   {n:>4}  {why}")
    by_sector = Counter(p[0] for p in proposed)
    print("\nproposed by sector:", dict(by_sector.most_common()))
    for slug, sym, name, med, share in sorted(proposed, key=lambda p: -p[3])[:30]:
        print(f"  + {sym:10} {name[:26]:26} {slug:22} median Rs {med:>13,.0f}  traded {share:.0%}")
    if len(proposed) > 30:
        print(f"  ... and {len(proposed) - 30} more")
    if emit:
        print("\n# --- paste into PSX_ASSETS in jobs/seed.py ---")
        for slug, sym, name, _, _ in proposed:
            nm = clean_name(name).replace('"', "'")
            print(
                f'    ("{slug}", "{sym}", "{nm}", "stock", "marketCap", PSX, "{sym}", '
                f'"Listed on the Pakistan Stock Exchange in the sector the exchange files it under."),'
            )
    return 0


def main(argv: list[str]) -> int:
    # Tickers include characters a Windows console codepage cannot encode, and a report that dies
    # printing the fortieth line has told nobody anything about the other hundred and ten.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    emit = "--emit" in argv
    verbose = "--why" in argv
    what = next((a for a in argv if a in ("crypto", "psx", "all")), "all")
    rc = 0
    if what in ("crypto", "all"):
        rc |= crypto_report(emit=emit, verbose=verbose)
    if what in ("psx", "all"):
        rc |= psx_report(emit=emit)
    return rc


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
