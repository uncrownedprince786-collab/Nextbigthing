"""Daily prices, size on the snapshot dates, and news.

Sources, all free and public:
  Yahoo Finance (via yfinance)  daily OHLCV and share counts
  Binance public klines          daily crypto closes
  CoinGecko market_chart         crypto market cap history and current cap
  CoinPaprika /v1/tickers        current coin list, supply, market cap
  Google News RSS                headlines per industry and per product

Nothing here is estimated. If a source does not answer for an asset, that asset gets
no row for that date and the UI says the data is missing.

Run: python jobs/prices.py
"""

from __future__ import annotations

import sys
import time
import urllib.parse
import warnings
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone
from pathlib import Path

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent))

from nbt import SNAPSHOTS, db, get_json, get, rows, step  # noqa: E402

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except Exception:  # noqa: BLE001
    pass

import pandas as pd
import yfinance as yf  # noqa: E402

START = date(2019, 1, 1)
YAHOO = "Yahoo Finance"
COINGECKO = "CoinGecko"
BINANCE = "Binance"
PAPRIKA = "CoinPaprika"
GNEWS = "Google News RSS"
PSX = "psx"
NEWS_PER_FEED = 12
# Asset feeds are narrower than the industry ones, so a smaller cap keeps the run short
# and stops one busy company filling its own page with the same week of coverage.
NEWS_PER_ASSET = 6

SNAPSHOT_SET = set(SNAPSHOTS)


def yahoo_assets(cur) -> list[dict]:
    return rows(
        cur,
        """
        SELECT a.id, a.symbol, a."sourceRef" FROM "Asset" a
        WHERE a.source = 'yahoo' ORDER BY a.symbol
        """,
    )


def crypto_assets(cur) -> list[dict]:
    return rows(
        cur,
        """
        SELECT a.id, a."sourceRef" FROM "Asset" a
        WHERE a.source = 'coinpaprika' ORDER BY a.symbol
        """,
    )


def last_on_or_before(series: list[tuple[date, float]], target: date):
    """Closest real observation at or before target. None when the source starts later."""
    hit = [v for day, v in series if day <= target]
    return hit[-1] if hit else None


def day_on_or_before(series: list[tuple[date, float]], target: date):
    hit = [day for day, v in series if day <= target]
    return hit[-1] if hit else None


def fetch_yahoo(cur) -> int:
    assets = yahoo_assets(cur)
    tickers = [a["sourceRef"] for a in assets]
    step(f"yahoo daily history for {len(tickers)} tickers")
    if not tickers:
        return 0

    frame = yf.download(
        tickers,
        start=START.isoformat(),
        progress=False,
        auto_adjust=True,
        group_by="ticker",
        threads=4,
    )
    written = 0
    today = date.today()

    for a in assets:
        sym = a["sourceRef"]
        try:
            part = frame[sym] if isinstance(frame.columns, pd.MultiIndex) else frame
        except KeyError:
            print(f"  no column for {sym}")
            continue
        part = part.dropna(subset=["Close"])
        if part.empty:
            print(f"  empty history for {sym}")
            continue

        closes: list[tuple[date, float]] = []
        volumes: dict[date, float] = {}
        bars: dict[date, tuple[float | None, float | None, float | None]] = {}

        def num(value):
            """A float, or None for the NaN the source uses for a field it did not publish."""
            return float(value) if value == value and value is not None else None

        for stamp, row in part.iterrows():
            day = stamp.date()
            closes.append((day, float(row["Close"])))
            vol = row.get("Volume")
            if vol == vol:  # not NaN
                volumes[day] = float(vol)
            # The source has always sent these; the job used to drop them on the floor.
            bars[day] = (num(row.get("Open")), num(row.get("High")), num(row.get("Low")))

        cur.execute('DELETE FROM "PriceSnapshot" WHERE "assetId" = %s', (a["id"],))

        # Share count history, forward filled, so size on a past date uses the share
        # count that was in force on that date. Absent share data means no size row.
        shares = share_series(sym)
        cap_rows = []
        for snap in SNAPSHOTS + [today]:
            close = last_on_or_before(closes, snap)
            if close is None:
                continue
            day = day_on_or_before(closes, snap)
            sh = last_on_or_before(shares, snap) if shares else None
            if sh is None:
                continue
            cap_rows.append((day, close * sh))

        cap_by_day = {day: val for day, val in cap_rows}

        buffer = [
            (
                a["id"], day,
                *bars.get(day, (None, None, None)),
                close, volumes.get(day), cap_by_day.get(day), YAHOO,
            )
            for day, close in closes
        ]
        insert_snapshots(cur, buffer)
        written += len(buffer)
        print(f"  {sym:7} {len(closes)} days, {len(cap_by_day)} size points")
        time.sleep(0.4)

    return written


_share_cache: dict[str, list[tuple[date, float]]] = {}


def share_series(sym: str) -> list[tuple[date, float]]:
    if sym in _share_cache:
        return _share_cache[sym]
    out: list[tuple[date, float]] = []
    try:
        s = yf.Ticker(sym).get_shares_full(start=START.isoformat())
    except Exception as e:  # noqa: BLE001
        print(f"  shares failed {sym}: {type(e).__name__}")
        s = None
    if s is not None and len(s):
        for stamp, val in s.items():
            if val == val and val:
                out.append((stamp.date(), float(val)))
    _share_cache[sym] = out
    return out


def insert_snapshots(cur, buffer: list[tuple]) -> None:
    if not buffer:
        return
    with cur.copy(
        'COPY "PriceSnapshot" ("assetId", date, open, high, low, close, volume, '
        '"marketCap", source) FROM STDIN'
    ) as cp:
        for asset_id, day, op, hi, lo, close, vol, cap, source in buffer:
            cp.write_row((asset_id, day, op, hi, lo, close, vol, cap, source))


def fetch_crypto(cur) -> int:
    step("crypto history")
    assets = crypto_assets(cur)
    tickers = get_json(
        "https://api.coinpaprika.com/v1/tickers?quotes=USD",
        cache_key="paprika-tickers",
        ttl=12 * 3600,
    ) or []
    by_id = {t["id"]: t for t in tickers}

    written = 0
    for a in assets:
        cid = a["sourceRef"]
        meta = by_id.get(cid)
        sym = (meta or {}).get("symbol") or cid.split("-")[0].upper()

        # Daily closes from Binance. Public endpoint, no key. Paged forward because
        # a klines page holds at most 1000 rows.
        all_bars: list = []
        cursor = 1546300800000
        for page in range(8):
            page_rows = get_json(
                f"https://api.binance.com/api/v3/klines?symbol={sym}USDT&interval=1d"
                f"&startTime={cursor}&limit=1000",
                cache_key=f"binance-{sym}-{cursor}",
                ttl=6 * 3600 if page == 0 else 30 * 24 * 3600,
            )
            if not page_rows:
                break
            all_bars.extend(page_rows)
            cursor = page_rows[-1][0] + 86400000
            if len(page_rows) < 1000:
                break

        closes = [
            (datetime.fromtimestamp(b[0] / 1000, tz=timezone.utc).date(), float(b[4]))
            for b in all_bars
        ]
        volumes = {
            datetime.fromtimestamp(b[0] / 1000, tz=timezone.utc).date(): float(b[5])
            for b in all_bars
        }

        # Market cap. CoinPaprika publishes today's market cap for every coin. No free
        # source publishes circulating supply by year, so no historical cap is stored
        # rather than one backfilled from today's supply. That is why the crypto
        # industry is ranked by return and not by size.
        today_cap = ((meta or {}).get("quotes", {}).get("USD", {}) or {}).get("market_cap")
        cap_by_day = {}
        if today_cap:
            cap_by_day[closes[-1][0]] = float(today_cap)

        if not closes:
            print(f"  {cid}: no closes, skipped")
            continue

        cur.execute('DELETE FROM "PriceSnapshot" WHERE "assetId" = %s', (a["id"],))
        buffer = [
            (a["id"], day, close, volumes.get(day), cap_by_day.get(day), BINANCE)
            for day, close in closes
        ]
        insert_snapshots(cur, buffer)
        written += len(buffer)
        print(f"  {sym:6} {len(closes)} days, {len(cap_by_day)} size point")

    return written


def today_utc() -> date:
    return datetime.now(timezone.utc).date()


NEWS_TERMS = {
    "mega-cap-tech": "Nvidia Microsoft Apple AI spending",
    "semiconductors": "semiconductor chip export controls",
    "crypto": "bitcoin crypto market ETF",
    "precious-metals": "gold silver price central bank",
    "energy": "oil natural gas OPEC energy demand",
    "healthcare": "FDA obesity drug pharma earnings",
    "financials": "bank interest rates earnings credit",
}

# A bare company name is often the wrong search. "Apple" returns fruit and airlines,
# "Meta" returns metadata, "Oracle" returns crypto price prediction, and a metal ETF's
# name rarely appears in a headline. These give the feed a word that means the company.
ASSET_NEWS_HINTS = {
    "AAPL": "iPhone",
    "AMZN": "AWS",
    "GOOGL": "Google",
    "META": "Zuckerberg",
    "ORCL": "cloud",
    "avax-avalanche": "AVAX",
    "COPX": "copper",
    "CPER": "copper",
    "GC=F": "gold",
    "GLD": "gold",
    "IAU": "gold",
    "PALL": "palladium",
    "PPLT": "platinum",
    "SI=F": "silver",
    "SIVR": "silver",
    "SLV": "silver",
    "NFLX": "streaming",
    "TSLA": "electric vehicle",
    "NVO": "insulin",
    "LLY": "GLP-1",
    "JPM": "banking",
    "BAC": "banking",
    "C": "bank",
    "GS": "investment bank",
    "MS": "investment bank",
    "WFC": "bank",
    "AXP": "credit card",
    "BLK": "asset management",
    "SCHW": "brokerage",
    "PGR": "insurance",
    "XOM": "oil",
    "CVX": "oil",
    "COP": "oil",
    "EOG": "oil",
    "MPC": "refining",
    "PSX": "refining",
    "VLO": "refining",
    "OXY": "oil",
    "SHEL": "oil",
    "SLB": "oilfield services",
    "MU": "memory chips",
    "LRCX": "chip equipment",
    "KLAC": "chip equipment",
    "AMGN": "biotech",
    "GILD": "antiviral",
    "ISRG": "surgical robot",
    "DHR": "medical devices",
    "ABBV": "pharma",
    "MRK": "vaccine",
    "VRTX": "biotech",
    "TSM": "foundry",
    "ASML": "lithography",
    "ARM": "chip design",
    "QCOM": "mobile chips",
    "INTC": "foundry",
    "AMD": "accelerator",
    "TXN": "analog chips",
}


def asset_news_term(a: dict) -> str:
    """A search that names this asset. Each kind needs a different key."""
    kind = a["assetType"]
    hint = ASSET_NEWS_HINTS.get(a["symbol"])
    if a.get("source") == PSX:
        # A PSX ticker is three to six letters that mean something else in English news:
        # "PSO" and "MARI" and "ILP" all return unrelated results, and the company names
        # are shared with firms in other countries. The country word is what separates
        # Pakistani coverage from the rest, and it is how the local press writes it.
        return f'"{a["name"]}" Pakistan'
    if kind == "etf":
        # A fund's formal name is almost never quoted in a headline, and the brand is
        # written in lower case, so a quoted "abrdn Silver Shares" returns nothing at all.
        # The ticker is what financial news prints, so lead with that.
        base = f'"{a["symbol"]}"'
    elif kind == "crypto":
        base = a["name"]
    elif kind == "commodity":
        # A futures contract is named by its underlying in every headline, never by symbol.
        return hint or a["name"]
    else:
        base = f'"{a["name"]}"'
    return f"{base} {hint}" if hint else base


def fetch_news(cur) -> int:
    step("news")
    written = 0
    industries = rows(cur, 'SELECT id, slug FROM "Industry"')
    products = rows(cur, 'SELECT id, name FROM "Product"')
    assets = rows(
        cur, 'SELECT id, symbol, name, "assetType", source FROM "Asset" ORDER BY symbol'
    )

    def ingest(url, cache_key, insert_sql, params_fn, cap=NEWS_PER_FEED):
        nonlocal written
        raw = get(url, cache_key=cache_key, ttl=3600)
        if not raw:
            return
        try:
            root = ET.fromstring(raw)
        except ET.ParseError:
            print("  bad rss")
            return
        kept_here = 0
        for item in root.iter():
            if not item.tag.endswith("item") or kept_here >= cap:
                continue
            gett = {c.tag.split("}")[-1]: (c.text or "").strip() for c in item}
            title = gett.get("title", "")
            link = gett.get("link", "")
            pub = gett.get("pubDate", "")
            if not title or not link:
                continue
            publisher = title.rsplit(" - ", 1)[-1] if " - " in title else ""
            try:
                # strptime in this Python rejects a bare "GMT", so name the offset.
                when = datetime.strptime(
                    pub.replace("GMT", "+0000").replace("UTC", "+0000"),
                    "%a, %d %b %Y %H:%M:%S %z",
                ).astimezone(timezone.utc).replace(tzinfo=None)
            except ValueError:
                continue
            cur.execute(
                insert_sql,
                params_fn(when, title, link, publisher),
            )
            written += cur.rowcount if cur.rowcount > 0 else 0
            kept_here += 1
        print(f"  {kept_here} from {cache_key}")

    news_sql = """
        INSERT INTO "News" ("industryId", title, url, publisher, "publishedAt", source, "createdAt")
        VALUES (%s,%s,%s,%s,%s,%s, now())
        ON CONFLICT ("industryId", url)
        WHERE "assetId" IS NULL AND "productId" IS NULL AND "industryId" IS NOT NULL
        DO NOTHING
    """
    prod_sql = """
        INSERT INTO "News" ("productId", title, url, publisher, "publishedAt", source, "createdAt")
        VALUES (%s,%s,%s,%s,%s,%s, now())
        ON CONFLICT ("productId", url)
        WHERE "productId" IS NOT NULL AND "assetId" IS NULL DO NOTHING
    """
    asset_sql = """
        INSERT INTO "News" ("assetId", title, url, publisher, "publishedAt", source, "createdAt")
        VALUES (%s,%s,%s,%s,%s,%s, now())
        ON CONFLICT ("assetId", url) WHERE "assetId" IS NOT NULL DO NOTHING
    """

    for ind in industries:
        term = NEWS_TERMS.get(ind["slug"], ind["slug"])
        url = (
            "https://news.google.com/rss/search?q="
            + urllib.parse.quote(term)
            + "&hl=en-US&gl=US&ceid=US:en"
        )
        ingest(
            url,
            f"gnews-ind-{ind['slug']}",
            news_sql,
            lambda w, t, l, p, i=ind: (i["id"], t, l, p, w, GNEWS),
        )

    for prod in products:
        url = (
            "https://news.google.com/rss/search?q="
            + urllib.parse.quote(f'"{prod["name"]}"')
            + "&hl=en-US&gl=US&ceid=US:en"
        )
        ingest(
            url,
            f"gnews-pr-{prod['id']}",
            prod_sql,
            lambda w, t, l, p, pr=prod: (pr["id"], t, l, p, w, GNEWS),
        )

    # Asset pages. An article is stored once per target, so the same story can appear on an
    # asset, a product and an industry at once, which is what a reader of each page wants.
    # The query stays narrow anyway: naming the company is what finds the coverage stories
    # for that company rather than generic news about its industry.
    empty = []
    for a in assets:
        term = asset_news_term(a)
        url = (
            "https://news.google.com/rss/search?q="
            + urllib.parse.quote(term)
            + "&hl=en-US&gl=US&ceid=US:en"
        )
        before = written
        ingest(
            url,
            # Versioned: the feed is cached by key, so a term that changes has to change
            # the key too or a stale response is reused for the rest of the hour.
            f"gnews-as-v2-{a['symbol']}",
            asset_sql,
            lambda w, t, l, p, x=a: (x["id"], t, l, p, w, GNEWS),
            cap=NEWS_PER_ASSET,
        )
        if written == before:
            empty.append(a["symbol"])
    if empty:
        print(f"  {len(empty)} assets matched no new article: {', '.join(empty)}")

    cur.execute('DELETE FROM "News" WHERE "publishedAt" < now() - interval \'120 days\'')
    return written


def main() -> None:
    conn = db()
    todo = set(sys.argv[1:]) or {"yahoo", "crypto", "news"}
    with conn, conn.cursor() as cur:
        if "yahoo" in todo:
            n1 = fetch_yahoo(cur)
            step("yahoo total")
            print(f"  {n1} price rows")
        if "crypto" in todo:
            n2 = fetch_crypto(cur)
            print(f"  {n2} crypto price rows")
        if "news" in todo:
            n3 = fetch_news(cur)
            print(f"  {n3} news rows written")

        cur.execute('SELECT count(*) AS n, max(date) AS latest FROM "PriceSnapshot"')
        got = cur.fetchone()
        print(f"\nPriceSnapshot rows: {got['n']}, latest {got['latest']}")
        cur.execute('SELECT count(*) AS n FROM "News"')
        print(f"News rows: {cur.fetchone()['n']}")
    conn.close()


if __name__ == "__main__":
    main()
