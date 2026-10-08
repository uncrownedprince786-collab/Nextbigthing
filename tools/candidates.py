"""Measure a proposed asset against its own free source before it is written into seed.py.

The expansion comment in `jobs/seed.py` says every symbol there "was verified against its own
source before being written down". That verification was done by hand, once, and left no
reproducible record. This is that check as a committed script, so the next batch is measured
the same way and the figures behind each name can be reprinted rather than remembered.

What each market is asked, and why those bars:

    US / FX / commodity   Yahoo's chart endpoint, one year of daily bars. A candidate must
                          return at least MIN_BARS sessions and carry at least MIN_TURNOVER
                          of median daily turnover (close x volume). Turnover rather than
                          volume, because 10 million shares of a $3 stock and 200,000 of a
                          $600 one are not the same market, and the rankings on this site are
                          computed inside an industry where both would sit.

    crypto                Coinbase's own candle endpoint for <SYM>-USD, which is the source
                          `jobs/prices.py` actually stores from. A coin that CoinPaprika lists
                          but Coinbase does not serve is a coin this project cannot price, so
                          the question asked is the one that decides whether a row ever lands.

    PSX                   the exchange's own published closing files. There is no symbol list
                          to check a guess against -- the archive IS the list -- so this mode
                          does not take candidates at all. It reads the last PSX_DAYS
                          published files, ranks every symbol in them by median daily turnover
                          and prints the liquid ones that are not already stored.

Nothing here writes a row. It reads the database only to find out which symbols are already
followed, so a candidate that is already in the universe is reported as such rather than
measured again.

    python tools/candidates.py psx
    python tools/candidates.py us IBM CSCO ...
    python tools/candidates.py crypto btc-bitcoin eth-ethereum ...
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "jobs"))

from nbt import db, get, get_json, rows  # noqa: E402
import prices as prices_job  # noqa: E402
import psx as psx_job  # noqa: E402

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except Exception:  # noqa: BLE001
    pass

# The bars a candidate must have printed in the last year. A name that did not trade on a
# fifth of the year's sessions cannot be ranked against one that traded every day.
MIN_BARS = 200
# Median daily turnover, in the quote currency. $50M is the floor the 2026-10-04 batch used
# and it is repeated rather than loosened: it is what dropped GT and HOG from that list.
MIN_TURNOVER = 50_000_000
# Crypto trades every day, so a year is 365 bars; Coinbase's endpoint caps a request at 300,
# and one page of it is enough to measure liquidity.
MIN_CRYPTO_BARS = 250
# Calibrated against the coins already followed rather than asserted. Measured 2026-10-08 on
# the venue each one actually prices from, the 27 stored coins run from $573M (bitcoin) down to
# $0.5M (ethereum classic), with a median near $4M. A $20M floor -- the figure the 2026-10-04
# batch used against Binance's global volume -- rejects two thirds of the universe this site
# already carries, which makes it a floor for a different question. $4M is the median of what
# is here: a new coin has to be at least as liquid as the typical one already followed.
MIN_CRYPTO_TURNOVER = 4_000_000
# PSX turnover is in rupees. Rs.20M a day is around $70k -- small in dollars and genuinely
# liquid on this exchange, where the median listed name trades far less.
MIN_PSX_TURNOVER = 20_000_000
# Published files read for the PSX ranking. Fifteen sessions is the window the existing PSX
# batch was chosen on, and the cache in .cache makes a re-run of this free.
PSX_DAYS = 21
# A symbol must have printed a close on this fraction of the sessions actually published, so
# one 30-million-rupee day cannot carry a name that otherwise does not trade.
PSX_PRESENCE = 0.8
# Followed names a sector code needs behind it before the code is treated as meaning that
# industry. One is not evidence: `ENGROH` is a holding company the exchange files under its
# investment-company code, and the project placed it in PSX Fertilizer, which on its own
# taught the map that every brokerage on the exchange was a fertilizer producer -- seven of
# them, including Arif Habib and Trust Brokerage, arrived as fertilizer candidates. A wrong
# industry is not a cosmetic error here: every peer median, relative-strength reading and
# ranking on this site is computed inside one.
MIN_CODE_EVIDENCE = 3

CHART = "https://query1.finance.yahoo.com/v8/finance/chart/"
COINBASE = "https://api.exchange.coinbase.com/products"
PAPRIKA = "https://api.coinpaprika.com/v1/coins"


def stored_symbols() -> dict[str, str]:
    """{symbol: market} for everything already followed, so a duplicate is never measured."""
    conn = db()
    try:
        with conn.cursor() as cur:
            got = rows(
                cur,
                'SELECT a.symbol, a."sourceRef", i.market FROM "Asset" a '
                'JOIN "Industry" i ON i.id = a."industryId"',
            )
    finally:
        conn.close()
    out: dict[str, str] = {}
    for r in got:
        out[r["symbol"].upper()] = r["market"]
        if r["sourceRef"]:
            out[r["sourceRef"].upper()] = r["market"]
    return out


def stored_in(market: str) -> set[str]:
    """The symbols already followed **in one market**.

    A symbol is not unique across exchanges and this is not a hypothetical: PSX is both the
    Pakistan Stock Exchange's own listing in Karachi and Phillips 66 in New York, and this
    project follows the American one. Checking a Karachi candidate against every symbol stored
    anywhere therefore dropped the exchange itself -- Rs.29.9M a day, in the archive on every
    session -- as "already followed". A market has to be part of the question.
    """
    conn = db()
    try:
        with conn.cursor() as cur:
            return {
                r["symbol"].upper()
                for r in rows(
                    cur,
                    'SELECT a.symbol FROM "Asset" a JOIN "Industry" i ON i.id = a."industryId" '
                    "WHERE i.market = %s",
                    (market,),
                )
            }
    finally:
        conn.close()


def yahoo_year(symbol: str) -> tuple[int, float | None, str]:
    """(bars, median turnover, note) for one Yahoo symbol over the last year."""
    payload = get_json(
        f"{CHART}{symbol}?range=1y&interval=1d",
        cache_key=f"cand-y-{symbol}",
        ttl=6 * 3600,
    )
    if not payload:
        return 0, None, "no answer from the chart endpoint"
    result = (payload.get("chart") or {}).get("result") or []
    if not result:
        err = ((payload.get("chart") or {}).get("error") or {}).get("description")
        return 0, None, err or "the endpoint returned no series"
    quote = (result[0].get("indicators") or {}).get("quote") or [{}]
    closes = quote[0].get("close") or []
    volumes = quote[0].get("volume") or []
    turnover = [
        float(c) * float(v)
        for c, v in zip(closes, volumes)
        if c is not None and v is not None
    ]
    bars = len([c for c in closes if c is not None])
    if not turnover:
        return bars, None, "the series carries no volume, so turnover cannot be measured"
    return bars, median(turnover), ""


def venue_year(paprika_id: str) -> tuple[int, float | None, str, str]:
    """(bars, median daily turnover, venue, note) from the venue chain the job itself uses.

    `prices.crypto_closes` walks Binance, Coinbase, Kraken and Bitstamp in that order and
    returns the first venue with a *current* series. Asking it rather than one exchange is the
    whole point: TRON is followed here and Coinbase serves no TRX-USD product at all, so a
    check written against Coinbase alone would have rejected a coin this project has been
    pricing daily for a week. The question a candidate has to answer is "can this repository
    price you", and that is the function that decides it.
    """
    symbol = paprika_id.split("-")[0].upper()
    try:
        venue, bars = prices_job.crypto_closes(symbol)
    except Exception as e:  # noqa: BLE001
        return 0, None, "", f"the venue chain raised {type(e).__name__}"
    if not bars:
        return 0, None, "", f"no venue in the chain serves {symbol}"
    # (day, open, high, low, close, volume)
    turnover = [float(b[4]) * float(b[5]) for b in bars if b[4] and b[5] is not None]
    if not turnover:
        return len(bars), None, venue or "", "the series carries no volume"
    return len(bars), median(turnover), venue or "", ""


def paprika_known(paprika_id: str) -> str:
    """Empty when CoinPaprika carries the id, otherwise why it does not."""
    payload = get_json(
        f"{PAPRIKA}/{paprika_id}", cache_key=f"cand-pap-{paprika_id}", ttl=24 * 3600
    )
    if not isinstance(payload, dict) or not payload.get("id"):
        return "CoinPaprika does not carry this id"
    if payload.get("is_active") is False:
        return "CoinPaprika lists the coin as inactive"
    return ""


def report(label: str, ok: bool, detail: str) -> bool:
    print(f"  {'PASS' if ok else 'DROP'}  {label:<24} {detail}")
    return ok


def run_us(candidates: list[str]) -> None:
    known = stored_symbols()
    print(f"US candidates, one year of Yahoo daily bars, floor {MIN_BARS} bars and "
          f"${MIN_TURNOVER/1e6:.0f}M median daily turnover\n")
    kept = []
    for sym in candidates:
        if sym.upper() in known:
            report(sym, False, f"already followed ({known[sym.upper()]})")
            continue
        bars, turn, note = yahoo_year(sym)
        if note:
            report(sym, False, note)
            continue
        ok = bars >= MIN_BARS and turn is not None and turn >= MIN_TURNOVER
        detail = f"{bars} bars, ${turn/1e6:.0f}M median daily turnover"
        if report(sym, ok, detail):
            kept.append(sym)
    print(f"\n  {len(kept)} of {len(candidates)} pass: {' '.join(kept)}")


def run_crypto(candidates: list[str]) -> None:
    known = stored_symbols()
    print(f"crypto candidates, Coinbase daily candles, floor {MIN_CRYPTO_BARS} bars and "
          f"${MIN_CRYPTO_TURNOVER/1e6:.0f}M median daily turnover\n")
    kept = []
    for cid in candidates:
        if cid.upper() in known:
            report(cid, False, "already followed")
            continue
        why = paprika_known(cid)
        if why:
            report(cid, False, why)
            continue
        bars, turn, venue, note = venue_year(cid)
        if note:
            report(cid, False, note)
            continue
        ok = bars >= MIN_CRYPTO_BARS and turn is not None and turn >= MIN_CRYPTO_TURNOVER
        if report(cid, ok, f"{venue}, {bars} bars, ${turn/1e6:.1f}M median daily turnover"):
            kept.append(cid)
    print(f"\n  {len(kept)} of {len(candidates)} pass: {' '.join(kept)}")


# Symbol shapes the archive publishes that are not shares. Government paper dominates turnover
# by orders of magnitude and every underlying also carries a dated futures contract, which
# would double-count a name whose cash symbol is already followed. Both were filtered by hand
# for the 2026-10-04 batch; the rule is written down here instead.
def is_tradable_share(symbol: str) -> bool:
    if "-" in symbol:            # OGDC-OCT, PRL-SEP: dated futures on a cash symbol
        return False
    if symbol.startswith("P") and symbol[1:3].isdigit():   # P01GIS..., P05FRR...: state paper
        return False
    if symbol.endswith("TFC") or symbol.endswith("SUK"):   # term finance and sukuk issues
        return False
    return True


def psx_archive(days: int) -> tuple[int, dict[str, dict]]:
    """(sessions read, {symbol: {code, name, turnovers}}) from the exchange's own files.

    Parsed here rather than through `psx.read_day`, which drops the sector code: that field is
    the exchange's own classification and it is the only non-guessed answer to "which industry
    does this belong in". Pipe layout, confirmed against a published file: date, symbol, sector
    code, name, open, high, low, close, volume.
    """
    today = date.today()
    out: dict[str, dict] = {}
    sessions = 0
    for i in range(days + 1):
        day = today - timedelta(days=i)
        raw = get(
            psx_job.file_url(day),
            cache_key=f"psx-{day.isoformat()}",
            ttl=psx_job.ttl_for(day, today),
        )
        if not raw:
            continue
        text = psx_job.unpack(raw)
        if text is None:
            continue
        sessions += 1
        for line in text.splitlines():
            f = line.split("|")
            if len(f) < 10 or not f[1].strip():
                continue
            sym = f[1].strip().upper()
            if not is_tradable_share(sym):
                continue
            try:
                close, volume = float(f[7]), float(f[8])
            except ValueError:
                continue
            if close <= 0:
                continue
            row = out.setdefault(
                sym, {"code": f[2].strip(), "name": f[3].strip(), "turnovers": []}
            )
            row["turnovers"].append(close * volume)
    return sessions, out


def psx_code_map(archive: dict[str, dict]) -> dict[str, str]:
    """{exchange sector code: industry slug}, learned from the names already followed.

    The project's eight PSX industries were written by hand, and which of the exchange's
    sector codes each one means was never written down anywhere. It does not have to be: every
    followed symbol carries a code in the published file, so the mapping can be read off the
    universe instead of asserted. A code that two industries both claim is dropped rather than
    guessed, and a code no followed name carries means the project has no industry for it --
    which is the honest answer for the steel, sugar, pharmaceutical and property names that
    rank high on turnover and have nowhere to sit.
    """
    conn = db()
    try:
        with conn.cursor() as cur:
            followed = {
                r["symbol"].upper(): r["slug"]
                for r in rows(
                    cur,
                    'SELECT a.symbol, i.slug FROM "Asset" a '
                    'JOIN "Industry" i ON i.id = a."industryId" WHERE i.market = %s',
                    ("PK",),
                )
            }
    finally:
        conn.close()

    claims: dict[str, set[str]] = {}
    counts: dict[str, int] = {}
    for sym, slug in followed.items():
        row = archive.get(sym)
        if row:
            claims.setdefault(row["code"], set()).add(slug)
            counts[row["code"]] = counts.get(row["code"], 0) + 1

    kept, thin, split = {}, [], []
    for code, slugs in sorted(claims.items()):
        if len(slugs) > 1:
            split.append(code)
        elif counts[code] < MIN_CODE_EVIDENCE:
            thin.append(f"{code} ({counts[code]} name, {next(iter(slugs))})")
        else:
            kept[code] = next(iter(slugs))
    if thin:
        print("  codes left unmapped, too few followed names behind them to be evidence: "
              + ", ".join(thin))
    if split:
        print("  codes two industries both claim, so neither is taken: " + ", ".join(split))
    return kept


def run_psx(turnover_floor: float = MIN_PSX_TURNOVER) -> None:
    known = stored_in("PK")
    sessions, archive = psx_archive(PSX_DAYS)
    codes = psx_code_map(archive)
    print(f"PSX, ranked from the exchange's own closing files over the last {PSX_DAYS} days\n")
    print(f"  {sessions} published sessions read, {len(archive)} share symbols in them")
    if not sessions:
        print("  the exchange published nothing in this window, so nothing can be ranked")
        return
    print(f"  {len(codes)} sector codes map to one industry each: "
          + ", ".join(f"{c}->{s}" for c, s in sorted(codes.items())))

    present = max(1, int(sessions * PSX_PRESENCE))
    ranked = []
    for sym, row in archive.items():
        if len(row["turnovers"]) < present or sym in known:
            continue
        ranked.append((median(row["turnovers"]), sym, row))
    ranked.sort(key=lambda r: -r[0])

    fits = [r for r in ranked if r[2]["code"] in codes and r[0] >= turnover_floor]
    nowhere = [r for r in ranked if r[2]["code"] not in codes and r[0] >= turnover_floor]

    print(f"\n  not yet followed, present on at least {present} of {sessions} sessions, "
          f"floor Rs.{turnover_floor/1e6:.0f}M median daily turnover\n")
    print(f"  {len(fits)} fit an industry that already exists:\n")
    for turn, sym, row in fits:
        print(f"    {sym:<10} Rs.{turn/1e6:>8.1f}M  {codes[row['code']]:<16} {row['name']}")
    print(f"\n  {len(nowhere)} are liquid and have no industry here, so they are not "
          "candidates:\n")
    for turn, sym, row in nowhere[:20]:
        print(f"    {sym:<10} Rs.{turn/1e6:>8.1f}M  sector {row['code']}        {row['name']}")


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    rest = sys.argv[2:]
    if mode == "psx":
        # An optional floor in millions of rupees, so the same ranking can be read down past
        # the default when the question is "which liquid names fit an industry that exists"
        # rather than "which are liquid at all".
        run_psx(float(rest[0]) * 1e6 if rest else MIN_PSX_TURNOVER)
    elif mode == "us" and rest:
        run_us(rest)
    elif mode == "crypto" and rest:
        run_crypto(rest)
    else:
        print(__doc__)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
