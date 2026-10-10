# NextBigThing - Brain

## Goal
Show what led before AI, what leads after AI, what is rising, and why. Cover markets
(stocks, crypto, commodities) and real world products. Free and authentic data only.
Readers open the site and read. No invented numbers, ever.

The reader can find every one of these sources themselves. What they cannot do is check all
of them, against every small factor, against every past parallel, fast enough to still be
early. That is the whole job: not to know something the public data does not, but to have
already read it. So the site is a research assistant that produces referenced context, and
it is never a prediction.

## Thinking principles
The permanent framework. These decide how a question is approached; every conclusion still
has to come out of stored rows and arithmetic done on them.

1. Several independent sources beat one strong source.
2. Relative strength against peers matters more than a raw return.
3. Sample size decides how much weight a parallel earns. It is never left unstated.
4. A past pattern is only useful when the differences are shown next to it. A similarity
   presented on its own reads as a forecast whatever words surround it.
5. Current human attention is context, not proof.
6. Factors that did not exist in the past window — the AI era, a different rate regime, a
   change in market structure or regulation — are surfaced every time, not just when they
   are convenient.
7. Every signal is checked against what actually happened afterwards.
8. Honesty beats an impressive number. A thin reading said plainly is worth more than a
   confident one that cannot be checked.

### What these rule out, in words the code has to honour
No "will", "likely", "expected to", "should". No advice about what to hold. A parallel is
described as measured history and a sample count, never as what happens next.

## Hard rules
1. Zero paid APIs, zero paid data sources.
2. Never estimate, interpolate, or fill a missing number. If a value is not published by
   the source, the row is absent and the UI says the data is unavailable.
3. Every stored number has a `source` column. Every stored claim has a `source` column.
4. Analysis is short plain factual English. No forecasts presented as fact, no causality
   claims. Direction and correlation only.
5. The frontend reads the database and nothing else. All fetching happens in jobs.
6. Jobs are rate limited, send a real User-Agent, and cache to disk so a rerun does not
   hammer a source.

## Data sources, as verified on 2026-09-29
| Source | Endpoint | Verdict |
| --- | --- | --- |
| Yahoo Finance | via `yfinance` | Works. Daily history since 2019, share counts. |
| CoinGecko | `/coins/{id}/market_chart` | Not used. `/coins/markets` returns 403 and `market_chart` returned 401 then 429, so it is not a source any number depends on. |
| CoinPaprika | `/v1/tickers` | Works. Full coin list with market cap and rank. This is the only source of current crypto market cap. |
| CoinPaprika | `/v1/coins/{id}/historical` | Paid tier only, returns 402. So crypto has a current size but no historical size. |
| Binance | `/api/v3/klines` | Works. Daily OHLCV history per pair, no key. |
| Google Trends | via `pytrends` | Works after a urllib3 Retry patch. Max 5 terms per call. |
| Google Trends trending | `/trending/rss?geo=US` | Works. Daily trending searches. |
| Wikipedia | `wikimedia.org` pageviews REST | Works. Per article, per day, free, no key. |
| Reddit | `*.reddit.com/r/{sub}/search.rss` | Works with a slow, identified client. `.json` endpoints return 403. |
| Hacker News | `hn.algolia.com/api/v1/search` | Works, no key. |
| Google News | `news.google.com/rss/search` | Works, **and ranks by relevance, not by date**. Re-verified 2026-10-07 and this is the correction that matters: the first six items of `"Hub Power" Pakistan` were published 24 Jul, 22 Jul, 28 Jul, 10 Aug, 4 Jun and 5 Mar **2024**, out of 97 offered. A cap that keeps the first six keeps those, `ON CONFLICT DO NOTHING` drops them as already stored, and the asset is frozen at six rows for ever — which is what had happened to 21 PSX names and 3 FX pairs. The same query with `when:14d` returns eight items, all inside the fortnight, including that week's real company news. Every feed in the lane now asks for `when:30d` **and** checks each item's own `pubDate`, because the operator is a request and the date is the evidence. |
| Google News, known residual | — | A company whose legal name is a generic phrase cannot be separated by name matching, and `SYS` is the measured case: `"Systems Limited"` also matches **Organic Recycling Systems Limited** and **Inter State Gas Systems Limited**, so two of its three items on 2026-10-07 were about other companies. The country word does not separate them, because the colliding names are regional too. Left as a stated limit rather than filtered: a rule strict enough to catch it — rejecting a name preceded by another capitalised word — would also reject "Pakistan's Systems Limited eyes acquisitions", and dropping real coverage of twenty names to clean two items is the wrong trade. The ticker rule already carries the other half of this problem, and a hint in `ASSET_NEWS_HINTS` is the lever if it ever matters more than it does. |
| Bing News RSS | `bing.com/news/search?...&format=RSS` | Works, no key. Verified 2026-10-07: 11 items for `"Lucky Cement" Pakistan`, led by that week's GEPCO privatisation story. The most precise of the three on Pakistani company names, which is why it is the first fallback everywhere. No date operator, so the window is enforced by the stored `pubDate` check alone. |
| Yahoo Finance headline RSS | `feeds.finance.yahoo.com/rss/2.0/headline?s=<SYM>` | Works for US listings — 18 items for AAPL, verified 2026-10-07. **Last in the chain and offered to US listings only**: it answered nothing at all for `USDPKR=X`, and for `SYS.KA` it answered with three real articles about core banking at other banks entirely, which is the fault the per-asset token guard exists to catch. |
| GDELT DOC API | `api.gdeltproject.org/api/v2/doc/doc` | **Not used.** Free and keyless, and it failed both halves of what a fallback has to do. Rate limited hard — 429 on two of three probes spaced six seconds apart on 2026-10-07 — and imprecise: `"Oil and Gas Development"` returned a Chinese-language article about an offshore platform as its first result. A source that cannot be asked about 112 names in a run, and whose answer is not about the name asked for, is worse than the gap. |
| The News (Pakistan) business feed | `thenews.com.pk/rss/2/9` | Not used. Answered 200 with a 37-byte body: "No news print today in this section". |
| Profit (Pakistan Today) | `profit.pakistantoday.com.pk/feed/` | Not used. Connection timed out from this network on 2026-10-07. Re-verify before adding. |
| SEC EDGAR | `data.sec.gov/submissions` | Works. Needs a `User-Agent` with contact details. |
| FRED | `fred.stlouisfed.org/graph/fredgraph.csv` | Times out from this network. Not used. |
| Stooq | CSV endpoint | Blocked by a JS challenge. Not used. |
| X / Twitter | any | No free authentic endpoint. Not used. Replaced by HN, Wikipedia, Reddit, Google News. |
| Amazon best sellers | `amazon.com/Best-Sellers/zgbs/<cat>/` | Re-verified 2026-09-30 and the earlier verdict was wrong, or the page changed: the first 30 positions are server rendered, with the rank inside each item's own link. Used for the marketplace section only, never in a demand score. Page two restarts the rank counter, so only page one is read. An unknown category slug does not 404, it serves a different category, so every slug is fetched before being added. |
| PSX daily closing file | `dps.psx.com.pk/download/mkt_summary/<date>.Z` | Works. A ZIP holding `closing11.lis`, one pipe delimited line per symbol: date, symbol, sector, name, open, high, low, close, volume, previous close. No key, no cookie, nothing solved. Files exist back past 2019-12-31, so all four snapshot dates are covered. This is the exchange's own record, not a scrape of a rendered page. |
| PSX company page | `dps.psx.com.pk/company/<SYM>` | Works, server rendered. Used only for the current share count. Verified: OGDC close 316.73 times 4,300,928,400 shares gives 1,362,233,052,132 PKR, against the 1,362,233,052.13 thousand the page publishes itself. There is no history behind the share count, so it is applied to the newest close and no other date. |
| PSX `dps.psx.com.pk/historical` | POST form | Returns 403. Not needed: the daily closing files cover the same ground. |
| PSX data API, and the `psxdata` library | any | Not used, and the difference matters. The reports of PSX requiring an `X-Req-Id` token since 2026-09-24, and of `psxdata` 1.1.1 adding a token fetch with a 403 retry, are about the JSON data endpoints. This site reads the published closing files instead, and those still answer an ordinary request with no token: re-verified 2026-09-30, HTTP 200, 1,025 symbols, and all 70 seeded PSX symbols present in the file. Do not add a library to fix a 403 this code path does not get. |
| eBay | `ebay.com/sch/i.html` with sold and completed filters | Returns 403 to an ordinary request. No free public endpoint behind it, so eBay is absent rather than estimated from something else. |
| Daraz, OLX, Facebook Marketplace | any | No free public ranking or volume endpoint. The product pages list the local checks a reader has to make by hand instead of showing a number that does not exist. |

Puppeteer is not used. The brief asked for stealth logged-in scraping of Reddit and X.
That breaks both sites' terms of service and risks the accounts. Every source that did
work has a public, rate limited endpoint, so the stealth layer would add risk and no data.

## Industries and assets
Seven market industries, 10 assets each. `size` basis is market cap for companies, fund
assets for ETFs, and absent for futures and for crypto at past dates, because no free
source publishes circulating supply history. Crypto has a current size only, from
CoinPaprika, and no pre-AI size row, which the UI shows as a gap rather than a zero.

1. Mega Cap Tech: AAPL MSFT NVDA GOOGL AMZN META AVGO TSLA ORCL NFLX
2. Semiconductors: TSM ASML AMD INTC MU QCOM ARM TXN LRCX KLAC
3. Crypto: BTC ETH SOL XRP BNB DOGE ADA LINK AVAX LTC (CoinPaprika ids)
4. Precious Metals: GLD SLV PPLT PALL CPER COPX GC=F SI=F IAU SIVR
5. Energy: XOM CVX COP SLB OXY EOG PSX VLO MPC SHEL
6. Healthcare: LLY NVO JNJ MRK ABBV ISRG AMGN GILD VRTX DHR
7. Banks and Financials: JPM BAC GS MS WFC C BLK SCHW AXP PGR
8. Automobile: TM GM F STLA HMC RIVN LCID RACE APTV BWA
9. Software and Cloud: CRM NOW ADBE INTU PANW SNOW PLTR WDAY DDOG MDB

TSLA stays in Mega Cap Tech and is not repeated in Automobile; MSFT and ORCL stay there
and are not repeated in Software and Cloud. One asset in two industries would sit in two
rankings and two industry averages, so its peers would be compared against a figure it
had helped set twice.

## Pakistan Stock Exchange
Eight sectors using the exchange's own sector groupings, 70 symbols, each one checked
against the closing file for both 2026-09-30 and 2021-12-31 so it exists now and has a
pre-AI reading to compare with.

1. PSX Banks: HBL UBL MCB MEBL BAFL BAHL NBP ABL AKBL FABL
2. PSX Oil and Gas: OGDC PPL POL MARI PSO APL SNGP SSGC ATRL HTL
3. PSX Cement: LUCK DGKC MLCF FCCL CHCC KOHC PIOC ACPL BWCL GWLC
4. PSX Fertilizer: FFC EFERT FATIMA AGL AHCL
5. PSX Power: HUBC KAPCO KEL NCPL NPL ALTN PKGP TSPL
6. PSX Technology and Communication: SYS NETSOL TRG AVN PTC TELE AIRLINK TPL HUMNL WTL
7. PSX Textile: NML GATM ILP NCL KTML ANL KOIL TOWL
8. PSX Automobile: INDU HCAR MTL AGTL SAZEW GHNI ATLH HINO DFML

These are separate industries, not extra rows in the existing ones. Every ranking is
computed inside one industry, so keeping them apart means a rupee size figure is never
sorted against a dollar one.

`size` basis is market capitalisation but only against the newest close, because the
share count has no history. There is no pre-AI size row for any PSX asset and the UI
shows that as a gap. Returns are in rupees and are not converted: a return earned over a
period of depreciation is not the same quantity as a dollar return, and saying so is
cheaper than pretending an exchange rate series exists for every date.

Fertilizer has five listings. That is a real limit on what a ranking inside it can say,
and the existing peer-count rules already cap it at medium for exactly that reason. It is
left as five rather than padded with unrelated companies to reach ten.

## Product hunting
Rising demand is the plain mean of whichever of these answered, each a percentage change
over a short, stated window:
- Google Trends: mean of the last 8 complete weeks against the 8 weeks before that, and
  the last 26 weeks against the 26 weeks a year earlier. Max 5 terms per request, so the
  30 products are batched.
- Wikipedia pageviews: same two windows, on the article title in the seed data. 27 of the
  30 titles resolve; the 3 that do not are a known gap, not zero.
- Hacker News stories: last 90 days against the 90 days before.
- Google News articles: last 30 days against the 30 days before.
- Reddit posts: the last 30 days against the rate over the 90 days immediately before,
  both cut from the year feed. Reddit's own 30 day feed caps at 25 results, so a capped
  count could not be compared with an uncapped one; reading both windows from the year
  feed keeps them comparable.
  The two windows are adjacent and the longer one is divided by three before the
  comparison. The first version of this compared the 30 day count directly against a
  90 day count taken from 180 to 90 days ago, which was wrong twice over: the 60 days in
  between were measured by neither window, and dividing a 30 day count by a 90 day count
  is not a change at all, so a product discussed at a perfectly steady rate came out at
  -67% on every single run.
  A product is counted only when *all* of its subreddits answered. Counting the ones that
  did answer would understate the product and read as falling demand, and because the
  denominator would change between runs the two figures would not be comparable at all. A
  rate limited product shows no Reddit figure for that period rather than a partial one,
  and any stored count left without the base it was measured against is deleted, because a
  reader cannot check a percentage whose denominator is missing.

`demandNote` names the sources that answered, so a reader can see the strength of the
signal. A product with one source is never called rising. A product with no sources is
labelled "no data" and is left out of every list.

News is deduped per target, not per table. One article can be stored once per asset, once
per product and once for an industry, because the same story genuinely belongs on all
three. Within a single target the same url is stored once. This is what lets two metal ETFs
tracking the same metal both hold the same coverage story.

Every asset has its own Google News feed, and the search term is chosen per instrument
kind rather than from the name alone: a stock uses its quoted name plus a disambiguating
word, because "Apple" returns fruit and "Oracle" returns crypto price prediction; a fund
uses its ticker, because a formal fund name is never quoted in a headline and the brand is
written in lower case, so a quoted "abrdn Silver Shares" matches nothing; and a futures
contract is searched by its underlying, since that is how headlines name it.

Related assets are a fixed, factual mapping in the seed data. The app shows the asset's
measured return next to the product. It does not say the product caused the move.

## Snapshots and ranking
Snapshot dates: 2019-12-31, 2021-12-31, 2023-12-29, 2025-12-31, plus the last close.
- Pre-AI: 2019-01-01 to 2021-12-31, ranked by size at 2021-12-31.
- Post-AI: 2021-12-31 to today, ranked by size today.
- Returns are price returns. Dividends are not added, so a high yielding asset looks
  weaker than a total return figure would. The label "total return" in the schema means
  price return, and the methodology page says so.
- Rising: return over the last 24 months minus the industry average over the same window,
  cross checked against whether 20 day average volume rose. If the volume check fails the
  row is stored with a note instead of being dropped.
- Every ranking row keeps `sizeRank` next to its own `rank`, so the size ranking is always
  available even when the primary rank is a return ranking.

## Confidence
Every ranking row, product and analysis line carries a grade of high, medium, low or none.
The grade is a claim about how well evidenced a figure is, not about direction, and the
reason is always stored next to it in `confidenceNote` so the badge can never be read as
saying more than the note supports.

Rankings:
- The industry mean is compared with the industry median. If they differ by more than
  `SKEW_LIMIT` (25 points) the mean is not a fair description of a typical peer, so the row
  is graded down. The rank itself is left alone, because changing the comparator would
  change published history; the skew is disclosed instead.
- High also needs `PEER_HIGH` (8) or more peers in the industry and a passing volume check.

Products:
- Agreement is measured against the average, not against whichever side is bigger. Three
  sources down and one up is a minority position even though three is the larger number.
- A split up/down caps the grade at medium however lopsided it is.
- A source reading exactly zero answered and reported no change. It is not a vote down.
  It stays in the denominator, because it answered, and it is counted as agreeing with
  neither direction. Deriving `down` as `answered - up` used to put it on the down side,
  which invented disagreements: three sources up and one unmoved was described as a split
  and capped at medium for a conflict that never happened.
- A mean and a median landing on opposite sides of zero also caps at medium, because the
  total no longer describes what a typical source said.
- One source supplying more than `DOMINANT_SHARE_LIMIT` (60%) of the average is disclosed
  but does not cap the grade on its own: several sources can agree on direction while one
  supplies the magnitude, and that is still agreement.
- High needs `PRODUCT_SOURCES_HIGH` (4) sources answering and 75% agreement.

### Small denominators
Reddit post counts are the one place where a percentage can be arithmetically true and still
be worth nothing. Measured across all 30 products the largest 90 day base is 15 posts, so at
a base of 6 a single post is 17% of the reading.
- `MIN_COUNT_BASE` (5) in `jobs/signals.py` decides what gets *published*. Below it only the
  raw counts are stored, because 1 post against 0 is a rounding artifact, not a demand signal.
- `THIN_BASE` (10) in `jobs/confidence.py` decides what can be *graded*. A Reddit percentage
  on a base under 10 is published, because 2 against 6 really is -67%, but it caps the
  product at medium. The number and the confidence claim are separate judgements and only
  the second one is limited.
- The effect is that no product currently grades high. The only one that used to, the
  espresso machine, was high on four agreeing sources while Reddit supplied 93% of its mean
  from a 6 post base. That was a handful of individual posts wearing the costume of a
  consensus.

## Jobs
- `jobs/schemacheck.py` refuses to let a data lane start when the database is behind this
  checkout's migrations. Holds no writer privilege and issues no DDL, so it cannot race the one
  workflow that does migrate. Exit 1 means behind; exit 2 means the check itself could not run,
  which is a different answer.
- `jobs/intraday.py` five minute bars for an **active set** chosen from stored rows, with 15, 30
  and 60 derived from them exactly. Bounded by a per-run request ceiling and swept after ten
  days. One minute bars are supported in the code and not fetched, because every reader queries
  five.
- `jobs/horizons.py` the intraday and longer term condition reads, plus a measured target range
  per method for every horizon including the swing read `setup.py` owns. Three horizons are
  three rows and are shown side by side, including when they disagree.
- `jobs/investigate.py` when a move is unusual against the asset's own sixty-session spread, it
  checks nine kinds of stored evidence and records `found`, `absent` and `unavailable` as three
  distinct answers. A move with no story behind it is reported as unexplained rather than
  attributed to something.
- `jobs/seed.py` industries, assets, products, asset links, asset notes. Run once.
- `jobs/psx.py recent|full` PSX closes from the exchange's daily closing files. `recent`
  is the snapshot dates plus the last 120 days; `full` adds a monthly grid back to 2019.
  Historical files never change, so they are cached for a year and a rerun is nearly free.
  Anchor dates walk backwards to the last published day rather than fetching every day in
  a window, which is the difference between about 300 requests and about 1,000.
- `jobs/events.py` seeds the hand written event list and measures the price change over
  the 14 and 30 days after each one. Runs before `analysis.py`, because the sentence under
  each event table is built from the rows in it.
- `jobs/marketplace.py` Amazon Best Sellers, first page of nine categories, with each
  listing's movement against the previous stored run. Weekly.
- `jobs/human.py` tone, attention and the hype flag per asset and product, from stored `News`
  rows. Makes no request. Also writes the `SignalLog` row for each reading.
- `jobs/accuracy.py` measures the move that followed each logged reading at 30 and 60 days,
  from stored closes. Makes no request. Runs after `human.py` so the day's reading is logged
  before the job that measures logged readings runs.
- `jobs/thesis.py` compares every held directional read against the row written on the day
  that state first appeared, and moves it through active, weakening and broken. Makes no
  request. Runs straight after `setup.py`, because it reads the row `setup.py` has just
  written; running it first would compare today against a run that ends yesterday and miss
  the day a reason broke. The opening conditions are copied, never recomputed — recomputing
  them would answer "what would we have said then, knowing what we know now". `broken` is
  terminal, so a recovery after a named level was passed cannot erase that it was passed.
- `jobs/attribution.py` splits each asset's 20 session move into the part its whole exchange
  group made, the part its own industry made beyond that, and the remainder. Medians, so one
  crypto return cannot describe a sector. Exclusive by construction: the three parts sum to
  the move. It names what a move was shared *with* and never what moved it, and no
  probability is attached, because a likelihood needs matured outcomes and none have matured.
  Below three industry peers the sector and specific parts are left null rather than
  estimated.
- `jobs/graph.py` carries each flagged catalyst at most two hops over the relationships
  already stored — shared product, shared dated item, small enough industry — and writes the
  chain in words beside every score. Bounded three ways: hops, edge group size, and an edge
  weight divided by the size of the group it came from. What travels is a reason to look. It
  is not impact, and nothing in it says a move travelled along an edge. Runs after
  `human.py`, because the catalysts it walks out from do not exist until then.
- `jobs/prices.py yahoo crypto news` daily closes, volume, share counts, market cap, news.
- `jobs/rank.py` all four ranking bases.
- `jobs/signals.py trends wiki hn news reddit` product demand signals.
- `jobs/confidence.py rankings|products|all` grades ranking rows and products. Runs between
  `rank.py` and `analysis.py`, because the analysis prose reads the grades so the badge and
  the sentence underneath it cannot disagree. `analysis.py` grades products itself, after it
  recomputes demand scores, so the grade always matches the score beside it.
- `jobs/analysis.py` the one line shifts, asset positions, rising notes, forward looks,
  product demand reads, front page lead. Deletes and rewrites `Analysis` on every run.
- `jobs/run.py daily|weekly|seed` runs the above in order, one subprocess per step, and
  exits non zero if any step failed.
- `jobs/stats.py` row counts and newest stored date per table. Also the last step of the
  scheduled workflow, so a run leaves a record.
- GitHub Actions runs `daily` at 07:17 UTC and `weekly` on Monday 07:43 UTC. Vercel cannot
  run Python, so nothing on the site is computed in the browser.
- Schema migrations run in the refresh workflow, never in the Vercel build. Vercel holds the
  read-only role, which has no rights to run DDL, so a migration there could only ever fail.
  The workflow holds the writer secret and applies `npx prisma migrate deploy` before any job
  runs, which is also the order the data needs: a job cannot write to a table that does not
  exist yet. `migrate deploy` skips migrations that have already run, so the step is a no-op
  on an unchanged schema.
- The consequence is that a schema change has to reach the database before the deploy that
  depends on it. The pages read their tables while Next.js collects page data, so a build
  that runs ahead of its migration fails there. That failure is safe — Vercel keeps serving
  the previous deployment — but the fix is always to run the migration and rebuild, never to
  give the site's role write access.

## The current discussion read
`jobs/human.py` writes one `HumanSignal` row per asset and per product from the `News` rows
already stored, so it makes no request of its own. Three readings, kept apart on purpose
because they answer different questions and often disagree.

- **Tone.** A fixed word list over headlines. Both-directions counts as neither, because
  "revenue beats but guidance misses" is both and picking a winner on match count invents a
  judgement. Published only at `MIN_ITEMS` (8) headlines or more and past a `NEUTRAL_BAND`
  (0.15) net share; below either, the counts are stored and no direction is. Ambiguous words
  are in neither list: `cut` is bad about guidance and good about rates.
- **Attention.** This 30 day window's item count against the 30 before it, called only past
  `ATTENTION_BAND` (25 points), and left null below `MIN_PRIOR_ITEMS` (5) rather than
  divided. It measures coverage collected, not interest: a rate limited feed looks exactly
  like a quiet month, which is why the raw counts sit next to the percentage everywhere.
- **Hype.** A separate promotional word list, flagged only when it covers `HYPE_SHARE_LIMIT`
  (20%) of the window *and* attention is rising. Wording alone is house style. The flag
  describes the writing, never the asset.

Grades follow principle 1: publisher spread counts as much as volume, and one publisher over
`DOMINANT_PUBLISHER_LIMIT` (50%) of a window caps the grade and is disclosed.

It is a word list and not sentiment analysis, and every surface that shows it says so. No
bodies, no negation, no sarcasm, no context.

## Accuracy, and why it reports nothing yet
`jobs/accuracy.py` is the other half of principle 7. `human.py` logs each reading in
`SignalLog` on the day it is generated, with the factors it rested on and the close stored
beside it; `accuracy.py` returns at 30 and 60 days and stores the move that followed.

- Readings with no published direction are logged too. Whether quiet, split coverage is
  followed by anything is the question the log exists to answer, and logging only the
  confident readings would make the eventual figure flattering.
- Nothing is filled in. An unelapsed window stays `open`, a product has no price series so
  its rows are `unmeasurable`, and a window landing in a gap in the stored prices keeps its
  null rather than borrowing a close beyond `MAX_DRIFT_DAYS` (5).
- No rate is published below `MIN_MEASURED` (20) matured rows, in the job and again in
  `lib/queries.ts`, so the page cannot publish what the job would have withheld. Until then
  the pages say how many are waiting.
- A stored move is a measurement, not a score. Coverage turning positive and a price rising
  in the same month is two things happening. The table is what has to exist before anyone can
  honestly say whether the two travel together.

## Planned layers, and what the stored history allows
Two of the four specified layers are built: the current discussion read and the accuracy log
above, both surfaced in one block on the asset and product pages. Still to come: historical
parallels with a context delta, and rule-based feedback from the accuracy log into factor
weights, which cannot start until the log has matured rows to learn from.

What can be built now is decided by what is actually stored, not by what is wanted:

- **Assets can support parallels.** `PriceSnapshot` holds daily closes and volume from
  2019-01-01, so relative strength quartiles and volume trend can be recomputed over any
  past rolling window. Roughly seven years of daily observations per US asset.
- **Products cannot yet.** `ProductSignal` is keyed on `periodEnd` so history does
  accumulate, but the first rows were written on 2026-09-29. Two days is not a history, and
  attention velocity measured against it would be a number with nothing behind it. Product
  parallels wait until the weekly signal runs have built a real series, and the honest thing
  in the meantime is for the product pages to say so rather than to show an empty block.
- **PSX cannot yet.** Those closes start arriving with this release, and market
  capitalisation exists for the latest close only, so a Karachi sector has no pre-AI size
  and no long window to match against.
- **Accuracy tracking has to be written before it can report.** A signal logged today is
  measurable in 30 days and not before. The table comes first and the hit rate comes later;
  showing a hit rate computed on a handful of rows would break principle 3.

The consequence for sequencing: the parallel layer starts with US assets, the accuracy log
starts recording immediately so the clock begins, and both product parallels and any
published hit rate stay behind a stated sample-size floor.

Three of the planned layers have since been built, and each one was only buildable because it
reads rows that already exist:

- **Thesis memory** needed nothing new. `AssetSetup` already stored a dated condition read
  per asset per day; the gap was that nobody compared two of them. A run of consecutive reads
  on one state is the thesis, and the only genuinely new idea is that the opening day's row is
  the reference rather than yesterday's.
- **Attribution** needed only closes, which go back to 2019 for the US names. It is the
  honest half of a hypothesis engine: the hypotheses are exclusive and their magnitudes are
  measured, and the half that is still missing is the posterior, which is blocked on matured
  outcomes exactly as the accuracy log is.
- **Graph propagation** needed only the link tables. What made it safe to build was the
  bounding, not the arithmetic: an unbounded walk over 160 assets reaches everything, and a
  list of everything is indistinguishable from no list at all.

## Rules for changes
0. One branch, `main`. Vercel deploys production from it and `schema.yml` triggers on it.
   `master` is left where it was and is not maintained. The catch to remember: GitHub takes
   `schedule` and `workflow_dispatch` from the repository's *default* branch and nowhere
   else, both the workflow file and the code, so the nightly refresh only runs current code
   once the default is `main`. If a job change does not show up in the nightly run, this is
   why.
1. Check whether the number already exists before adding a column.
2. If a source stops answering, mark it unavailable in this file and in the UI. Do not
   substitute a different source without saying so.
3. Never widen a ranking silently. The asset list is fixed in the seed.
4. Anything a reader could act on must carry the source name and the as of date.
5. `Analysis` rows are generated. Never hand edit text there, change `jobs/analysis.py`.
6. A grade must never be more confident than the note beside it. When a rule is added to
   cap a grade, add the reason to the note in the same change, or the badge is decoration.
7. Do not describe agreement when fewer than two sources answered. A single reading is one
   reading, and the prose has to say that.
8. Count the sources that answered, not the ones that moved. A source reporting no change
   still answered, and saying "all 3 sources that answered" when 4 did is just wrong.
9. Two windows compared against each other must be the same length, or one of them must be
   converted to a rate first. A count over 30 days divided by a count over 90 days is a
   ratio of window lengths with a real signal buried somewhere underneath it.
10. Nothing on this site says an event caused a price move. The event section measures what
    moved in a window that begins on a date. Over any 30 days some asset has the largest
    move, and a table that puts the two next to each other is already doing as much as the
    data allows. The words "because", "driven by", "in response to" and "reaction" do not
    belong in `jobs/analysis.py`.
11. Marketplace rows never enter a demand score. A search trend and a bestseller rank are
    different claims, and an average of the two would mean something different every week
    depending on which source answered.
12. A size figure carries its currency everywhere it is printed. A rupee market
    capitalisation shown with a dollar sign is wrong by a factor of nearly 300, in the
    direction that makes a Karachi listing look like a global one.
13. Verify a marketplace category slug by fetching it before adding it. An unknown Amazon
    slug does not 404, it quietly serves a different category, and nothing downstream would
    look wrong.
14. A thesis never re-derives its opening conditions. `AssetThesis.openConditions` is a copy
    of the row written on the day the state appeared, and anything that recomputes it from
    today's data has reintroduced look-ahead bias into the one place built to exclude it.
15. `broken` is terminal. Do not add a path that reassesses a broken thesis, however much a
    later recovery looks like it should count: the whole value of a level named in advance is
    that passing it cannot be taken back.
16. Attribution names what a move was shared with, never what moved it. The decomposition is
    co-movement; the banned words in rule 10 are banned here too, and the test suite checks
    the generated sentence for them.
17. Relevance from `jobs/graph.py` is a reading order and never an impact estimate. If a
    score is ever shown without the path that produced it, it has become the unsupported
    chain this project exists not to produce.
18. Keep the graph bounded. Raising `MAX_HOPS` past two, or `MAX_GROUP` past the point where
    a hub edge is excluded, makes every asset relevant to every other and the list worthless.
19. **One workflow migrates.** `schema.yml`, and nothing else. The data lanes run
    `jobs/schemacheck.py` and refuse to start when the database is behind. Adding a second
    `prisma migrate deploy` anywhere recreates the race that killed run 36798989654, and a test
    asserts there is only one.
20. **Retention never touches `PriceSnapshot`.** It is the permanent record and every other job
    is built on it. The sweep in `intraday.py` names `IntradayBar` and `IntradaySession`
    explicitly, and a test asserts those are the only tables it deletes from.
21. **Absent, zero and unavailable are three values, not one.** A zero-volume bar is a quiet
    five minutes; an absent one is a hole; an unsupported asset is a fact about the provider.
    `IntradaySession.status`, `InvestigationFinding.status` and `AssetSetup.missing` all exist
    to keep them apart, and collapsing any two of them is the silent data loss everything here
    is arranged to prevent.
22. **No bar is invented and no interval is approximated.** A derived bar is written only when
    every component bar is present. An hour built from nine of its twelve five minute bars is a
    quieter hour than the one that happened.
23. **A horizon's condition string must stay in `setup.py`'s format.** `thesis.py` parses it to
    decide whether a reason still holds, so a new horizon written in a new format silently
    produces theses with nothing to compare. Tests run the parser over every horizon's output.
24. **Targets are never averaged.** Three methods that disagree are three answers, and
    `SetupTarget.agreement` is how the disagreement reaches the page. A target is never written
    without an invalidation level behind it, and a target range never contains the entry.
25. **Quote identifiers in hand-written SQL.** `leading` is reserved in Postgres because `TRIM`
    uses it, and the unquoted column cost a production run that could not be diagnosed without
    a GitHub sign-in. A test scans every `INSERT` in `jobs/` for bare reserved words.
26. **Verify a provider before designing around it.** The intraday source was fetched and read
    before a line of schema was written; the crypto symbol mapping was checked against three
    real pairs; the storage cost was measured rather than estimated, and was six times what the
    design assumed. Every one of those was cheaper to learn by asking than by shipping.
27. **Never call `.timestamp()` on a naive datetime.** Every timestamp stored here is naive
    UTC, and `datetime.timestamp()` interprets a naive value in the *machine's* local
    timezone. `jobs/intraday.py` bucketed derived bars that way: invisible on the UTC workflow
    runner, and five hours wrong when the same job ran from a UTC+5 laptop, so AAPL's 15 minute
    bar at 08:00 held the open of the 13:00 bar. A timezone-dependent result is worse than a
    wrong one, because it is right on the machine that runs it in production and wrong on the
    machine that debugs it. Bucket and shift with arithmetic on the naive value. Two tests
    guard it — one states the answer and one forbids the construct, because a behavioural test
    alone passes on a UTC runner with the bug still present.
28. **An unfinished period is not an observation of that period.** The quote API's last element
    is the bar currently forming, stamped with the quote time and carrying no settled volume.
    Discard anything whose timestamp is not aligned to its interval: it is not a bar, it makes
    an aggregation group look complete, and because each run stamps a different second it is a
    new key every time rather than an overwrite.
29. **An upsert does not retract.** When a rule stops producing a row — an analog median that
    has turned, a structural level price has cleared — the previous run's row survives and the
    page keeps showing something the rules would no longer write. A job that writes a *set* per
    parent must delete the members it did not produce. `jobs/horizons.py` does this for
    `SetupTarget`.
30. **Retention must equal what each run refetches.** A row outside the refetch window is never
    revisited, so it keeps whatever derived label it was given, and a stale label silently
    degrades every read that filters on it. Intraday retention is 7 days because `range=5d`
    spans seven calendar days; changing one without the other reintroduces the problem.
31. **A batch fetch that returns nothing returned a failure.** `yf.download` answers a
    throttled or blocked request with an empty DataFrame and raises nothing, so a blocked host
    is indistinguishable from a market with no new bars unless the row count is checked. The
    nightly refresh stored 0 rows on a GitHub runner while the same fetch stored 37,537 from a
    laptop minutes later, and the step still exited 0 — the failure was only visible because
    `jobs/audit.py` compares the newest day against its own median. One asset answering
    nothing is data; none of a batch answering is a fact about the provider. `require_answer`
    in `jobs/prices.py` draws that line, the same one `jobs/marketplace.py` draws when every
    Amazon category is blocked, and two tests guard it — one states the answer and one forbids
    storing a download without the check, because the behavioural test passes on any host
    Yahoo does answer.

    The line is now drawn in every batch lane, and **what gets counted differs per lane** —
    this is the part to get right. Yahoo and Binance count rows stored, because a run always
    refetches its window. The news lane counts **feeds that parsed**, not rows written: `ON
    CONFLICT DO NOTHING` makes new rows legitimately 0 on a rerun inside the cache hour, so a
    row-count guard would fail a healthy run. It also runs *before* the 120-day retention
    sweep, or a host that fetched nothing would delete four months of articles on the strength
    of nothing. `jobs/psx.py` counts published trading days over a 120-day window, where zero
    cannot be a holiday. Pick the counter that is zero only when the source is silent.
32. **A row is built where the columns are known, or it drifts.** `insert_snapshots` grew
    `open`, `high` and `low` on 2026-10-01; the Yahoo caller was updated and the Binance one,
    thirty lines further down, was not. Six fields went to a nine-name unpack and every crypto
    insert raised `ValueError: not enough values to unpack` from that commit until it was
    found. Nothing caught it: COPY unpacks per row at run time, so the arity needs a database
    to surface, the 221 tests could not see it, and each job "passing individually" was
    measured on a path that stopped before this one. Every caller now goes through a named
    builder beside the writer — `crypto_rows` — and a test unpacks its output with the nine
    names COPY uses. When a writer gains a column, the builders are the list of places to fix.
33. **A guard that raises inside a transaction discards the run.** `prices.py` holds one
    transaction across the Yahoo, Binance and news lanes, and psycopg rolls back on *any*
    exception leaving `with conn` — so the rule 31 guard, raising `SystemExit` from the crypto
    or news lane, would have thrown away the 37,537 rows Yahoo had just written. A source
    being blocked must cost its own rows and no others. The guard raises `SourceSilent`, which
    is deliberately not a `SystemExit`; `main` catches it per lane, the transaction commits
    what did answer, and `fail_on_silent` exits non-zero after `conn.close()`. A test asserts
    the type, the three catches, and that the exit comes after the commit. The general shape:
    **a failure signal and a transaction boundary have to be designed together**, and the job
    that reports a problem is worth nothing if reporting it is what loses the data.
34. **Report coverage per source, never one total.** `PriceSnapshot` keeps growing from the
    lanes that still work, so a single row count is exactly the number that cannot see a dead
    source — the table held 123 MB while Binance had been stopped for days. Every run now
    prints a line per source with its newest date and how far behind that is, because a source
    that answers but is four days stale is a different fault from one that answers nothing, and
    those are the three numbers to read after a refresh.
35. **A measurement no reader sees is not a feature.** `audit.py` wrote a `Coverage` row per
    source on every run from the day coverage was added, and for all that time no page read the
    table: a feed that quietly died looked, to the reader, exactly like a quiet week — the
    precise confusion the table exists to end. Six of thirty-three models were in that state
    when it was audited. Before adding another measurement, check that the last one reaches a
    page, and when a job starts writing a status, the change that surfaces it belongs in the
    same commit. `AUDIT.md` holds the current list of what is written and never read.
36. **Built and unused is the recurring fault in this repository, not unbuilt.** The audit
    that found `Coverage` written and read by nothing found the same shape three more times in
    the web layer: a query measuring what past events of a category were followed by, wording
    for a reward-to-risk ratio that is stored on every target row, and intraday session health
    computed for a page that never called it. All finished, none reachable. Two further exports
    were genuinely dead — one wording helper superseded by better wording already on the page,
    one with no stored field behind it — and were deleted rather than wired, because keeping
    two vocabularies for one idea is the contradiction this file exists to prevent. A test now
    fails when any export in `lib/` or `components/` has no consumer, with an allowlist that is
    empty and a reason required to add to it. Before building, check what is already built.
37. **A scanner that cannot tell a denial from a claim will make the pages worse.** The
    language audit's first run flagged two lines, and both were disclaimers: "not as a claim
    that the readings caused the moves" is the opposite of the fault being looked for. Deleting
    them to turn the test green would have removed the honesty the test exists to protect, so
    the scanner looks back 120 characters for a negation and a test asserts both halves — a
    bare claim is caught and a denial is not. The general rule: when a guard fires on correct
    code, fix the guard, and never the code that was already right.
38. **A session-level lock and a transaction pooler cannot both be in the path.**
    `prisma migrate deploy` takes `pg_advisory_lock(72707369)` and releases it by ending its
    session. Neon's `-pooler` host is PgBouncer in transaction mode, so ending the client
    session does not end the server session: the connection goes back to the pool still holding
    the lock, and the lock outlives the process that took it. The next migration waits its ten
    seconds and dies `P1002 — Timed out trying to acquire a postgres advisory lock`. Schema run
    50 on 2026-10-02 failed that way **on a commit that changed two Markdown files**, which is
    the detail worth remembering: a red lane does not imply a broken commit, and twelve seconds
    is the signature — two of startup and ten of timeout, not work. The migration now runs over
    the direct endpoint and a test asserts the command does not inherit the pooled URL.

    Two things made it possible at once, and both were fixed, because either alone would have
    prevented it. The pooler was in the path, and **two lanes were migrating** — the invariant
    `WorkflowLanes` has guarded since the first race. The guard was true and the test was green:
    GitHub runs a workflow's *file* from the **default branch**, which is still `master`, and
    `master` was 34 commits behind `main`, where `refresh.yml` still migrated. So the repository
    asserted an invariant about files that production was not executing. **A test over a file in
    the working tree proves nothing about the file a runner used**; when a lane's behaviour and
    its test disagree, check which ref actually ran before doubting either.
39. **A measurement must compare like with like, or it reports the calendar.**
    `setup.py`'s volume gate asks whether the latest session traded at 1.2x the average of the
    twenty sessions before it. For a five day market that is one question. For a market that
    trades seven days it is two questions wearing one name, because a Saturday divided by an
    average that is five sevenths weekdays is a statement about which day of the week it is.
    Measured over the last 120 sessions of the ten stored coins: Monday to Friday run at 1.11
    to 1.23 of that average and pass the gate on 25-34% of days, while Saturday and Sunday run
    at 0.86 and 0.73 and pass on 17% and 11%. For BTC and ETH the weekend figure is 0.42 to
    0.51. So **all ten coins failed the volume leg on a weekend bar at 0.11x to 0.52x while
    every one of their trends read up**, and `core_up` needs all four legs, so crypto could not
    reach `buy` or `short` on a weekend at all. The symptom reported was "crypto is a permanent
    WAIT"; the cause was a denominator.

    The baseline is now drawn from sessions on the same side of the weekend as the one being
    judged, and falls back to the mixed baseline below four comparable bars, because an average
    of two is a pair of observations. Three properties are worth keeping in mind:

    - **It is stated once, for every market, and only bites where a market trades at the
      weekend.** A five day market has no weekend bars, so the split leaves the baseline whole.
      Measured across all 160 stored assets: ten crypto ratios moved, zero US or PSX ratios did.
      A correction that needs an `if market == "Crypto"` is a second vocabulary for one idea —
      rule 36 — and this one does not need it.
    - **`setup.py` no longer computes the ratio itself.** It had its own inline copy of the same
      average, and the copy is what made the bug possible: it had no dates, so it could not have
      told a quiet market from a Saturday even in principle. It calls `factors.volume_ratio` now.
    - **The fix was necessary and was not sufficient, and that distinction was kept.** The ten
      ratios roughly doubled — BTC 0.17 to 0.40, LTC 0.38 to 0.54 — and not one crossed 1.2, so
      no verdict changed on the day it went in. Crypto read WAIT before and reads WAIT now, and
      on that day it was the honest answer: trend up, volume genuinely thin, relative strength
      negative for six of ten. **Do not loosen a gate because a market is quiet through it.**
      The thing that was actually wrong for the reader was the wording — "incomplete" and "no
      longer-term reading stored" where the truth was "the trend is up but volume is weak".

40. **A withheld direction is still a direction, and the reader is owed it.**
    `jobs/setup.py` writes state `wait` when **the trend is clear and not all the conditions
    behind it are present** — 162 of 266 swing rows on 2026-10-07, of which 101 fail on one leg,
    volume. `directionOfState` maps `wait` to `flat`, so the rule table's fall-through printed "a
    direction is showing, but not all the conditions behind it are present" and threw away which
    way it pointed. Those names reached the reader as entries 13 to 160 of a WAIT list ordered by
    data faults, which is the same as not reaching them at all.

    The direction was never missing. It is the trend verdict inside the stored `conditions`
    string, and nothing in the web layer read that column. `Decision.developing` now carries it,
    with each absent confirmation named beside its own stored value, and the front page orders the
    list by `closeness` — the stored factor over the threshold it has to clear. 112 of 267 on the
    day it went in: 45 towards LONG, 67 towards SHORT, led by ASML at 1.19x of the 1.2x volume
    gate. That is a name one hundredth of a turn from confirming, and it was previously the
    hundred-and-something-th row of a list nobody scrolls.

    Four properties worth keeping:

    - **It is not an action and must never render as one.** The confirmations genuinely are not
      there; promoting it to LONG would be inventing them. The chip says "potential", the list
      says so above the cards, and `confidence` stays Low because a refusal is not a confident
      anything. A developing row is lifted *out* of the WAIT list rather than added beside it, so
      one asset cannot appear twice on one page under two framings.
    - **Only at the fall-through gate.** A stale close, a silent source or a missing invalidation
      level is not an opportunity forming, it is an unmeasured name; peers arguing the other way
      has already been given its reason. Every gate above the fall-through returns null.
    - **`closeness` is null when nothing missing is measurable, and null sorts last.** An FX pair
      publishes no volume at all — a fact about the instrument, not a quiet session — and rule 21
      says that is a third value, not a zero. Sorted as 0 it would read as "nearly there".
    - **It is stored nowhere.** `DecisionLog` records what the rules *decided*, and a forming read
      is by definition not a decision. A row there would be an outcome `jobs/accuracy.py` would
      then measure as though a gate had produced it. The page computes it live from the same rows,
      and `tools/decide.mjs` prints the count so the number is visible without being logged.

    One thing this cost, recorded because it is the third time: `bundleFromQuery` re-declares
    every field by hand, so `conditions` was selected by both queries, read by the rules, and
    dropped in between with nothing failing — exactly as `medianPct` and `positive` were. An
    optional field cannot fail to exist, so the guard is a test that a developing read survives
    the seam, not the type.

41. **Rule 28 applies to the daily lane too, and a schedule is not a substitute for it.**
    "An unfinished period is not an observation of that period" was written for the intraday
    quote API and enforced only there. The daily lane broke it for months in plain sight.
    `cron-us-prices` fetched at 13:50 and 19:50 UTC into a session running 13:30-20:00, and at
    `interval=1d` the provider returns the day in progress as an ordinary bar whose close is
    really the last trade. So the bar stored as the day's close was a part-day, every day.

    It surfaced three steps away and looked nothing like a clock problem. Measured 2026-10-07:
    AAPL's bar for the day held 8.0M shares against 30-50M on each neighbouring day, and across
    155 US names the newest bar's volume ran at a **median of 0.21x its own 20-session average**
    against the 1.2x `VOLUME_CONFIRMS_AT` asks for. The volume leg of every US setup failed,
    `setup.py` withheld the direction, and the rule table answered WAIT under `incomplete` for 90
    of 155. PSX read 0.84x the same day, because its closing file is only ever written after its
    own bell — **the control that identified the cause**, and the reason to always look for a
    population that should behave the same and does not.

    Three things this fixes, in the order they matter:

    - **The guard, not the schedule.** `forming_sessions` asks the chart endpoint — which carries
      session metadata, where `yf.download` does not — for one symbol per asset type, and
      `_store_frame` drops a bar for a session that has not closed. One probe per type because
      the session is a property of the exchange's calendar, not of the instrument. A failed probe
      stores everything rather than nothing: a guard against writing a bad bar must not also be
      able to stop the lane writing good ones.
    - **Both inputs to "has it closed" are untrustworthy alone, and the live data showed each
      failing.** The session's day must come from the exchange's own `gmtoffset`, not the UTC
      date of its start — `AUDUSD=X` runs 2026-10-06T23:00Z to 2026-10-07T22:59Z, which is the
      London day 10-07 and the day the bar is stamped, so a UTC reading drops a finished bar and
      keeps the forming one. And `regularMarketTime` cannot be trusted by itself: `HUBC.KA`
      returned a session ending 2026-10-07T11:00Z with a marker of **2024-07-23**, which read as
      progress would say "still trading" for ever and silently stop storing that venue's closes.
      A marker is progress only while it sits inside the session it describes.
    - **Being after the price lane is not being after the close.** `cron-decision` ran at 15:10
      and said so in a comment: "after the 13:50 US price chunks, so the run reads a day whose
      closes have landed". Both clauses were true of the ordering and false of the data. Prices
      now fetch post-close at 21:50, which clears 20:00 on daylight time and 21:00 on standard
      time with one slot and no DST table, and the decision moved to 22:10.

    The mirror image, found the same day and worth stating beside it: PSX had **one** attempt at
    12:40 UTC on a stated margin that was not there. The file for 10-07 was absent at 18:40 and
    present when fetched by hand at 19:10, so the day's close was only ever picked up by the next
    day's run. Invisible twice over — `psx.py` backfills recent sessions, so the gap closed itself
    a day late and the table always read complete, and `STALE_AFTER_DAYS.PSX` is 6, so a close one
    day late trips nothing. Three attempts now, the 20:40 one being the one that matters.

    Both ordering constraints are tests that fail on the old schedules. A sentence in a workflow
    header is not a constraint; this lane has now taught that twice.

42. **A threshold compared against a skewed mean is a different threshold in every market.**
    Rule 39 fixed *which* sessions the baseline is drawn from. This is the same class of fault in
    *what the baseline is*. `volume_ratio` divided by the mean of its window, and volume's skew is
    one sided — a session can be five times normal and cannot be below zero — so the mean sits
    above the typical session in essentially every window.

    Measured over 15,411 asset-sessions, every non-FX asset across its last 60 complete sessions,
    as the median of all the ratios produced:

        market        by mean   by median
        PSX             0.614       0.827
        Commodity       0.756       1.003
        US              0.874       0.955
        Crypto          0.931       1.063

    The bias is the smaller half. The larger half is that it is **uneven**, so one constant did
    not mean one thing: `VOL_ACTIVE` at 1.2 asked a Karachi name for roughly twice its typical
    session and a coin for roughly 1.3 times its own, and nothing anywhere said so. A threshold
    whose strictness depends on which market it lands in cannot be reasoned about from reading its
    own constant — and this one is a third of `setup.py`'s confirmations and half of what
    separates High from Medium.

    Against the median the centre lands between 0.83 and 1.06 everywhere, so 1.2x means about
    twenty percent busier than a typical session in every market, which is what the constant
    always claimed. Pooled, the share of sessions clearing it goes from 20% to 29%: a correction,
    not a loosening, because those sessions were always above a typical day and were being divided
    by a denominator no typical day could reach.

    `jobs/analogs.py` keeps its own mean-based ratio deliberately — that one is a similarity key
    for matching one past day to another, not a judgement about whether a session was busy.

    The general form, and the fourth instance in this repository: **check what a number is divided
    by, sorted by and timed against before concluding a source is silent.** Rule 9, rule 39, the
    news lane's relevance ordering, and now the volume denominator. Every one of them reported
    success honestly while being wrong.

43. **A measurement that argues against a direction is a caveat, not a veto — and the difference
    is worth 74 names.**
    Two gates sat between a measured direction and the reader and answered WAIT for 75 of 477
    names on 2026-10-09: an unusual move with thin news (60) and peers moving the other way (15).
    Every one of those names had a direction, an entry band and a stop level stored. Neither gate
    was reading a fault in the data; both were reading a real measurement and treating it as
    disqualifying.

    Neither is evidence about direction, and that is the whole case. Thin news under a move says
    the published explanation has not arrived yet — a statement about what reporters have
    written, not about what price did — and a rule table that refuses every unexplained move
    refuses exactly the moves that happen before the reason is public. A name lagging its peers is
    principle 2 and is often decisive, but it is a fact about *relative* return, and using it to
    veto an absolute direction discards the direction instead of qualifying it.

    Both now print in `Decision.notes`, in their own bordered block on the panel, above the
    missing block and above the news. The peer gap also caps confidence one step, so rule 6 holds:
    none of the 15 released names became a High.

    A third change in the same pass, and the larger one by count. `setup.py` writes state `wait`
    when the trend is clear and its conditions are not all present; 247 of 477 swing rows were in
    that state and **every one carried a trend verdict** (61 up, 186 down, 0 mixed). Rule 40 made
    that direction visible as a developing read. Gate 8 now acts on it, but only when one of two
    stored figures carries it: volume at or above `VOLUME_CONFIRMS_AT`, or a measured reward at or
    above `ASYMMETRY_CLEARS`. 30 names qualified. The other 116 with a clear trend still fall
    through and still arrive as developing reads with their shortfall named — which is the gate
    working, not failing: the condition it asks for is that the math or the volume agrees, and for
    those names neither did.

    Measured across the pool, before and after, same inputs and same day:

        action      before   after
        LONG            58      78
        SHORT           73     127
        WAIT           346     272

    `ASYMMETRY_CLEARS` is 2.0 and that number is chosen from the table rather than from habit: of
    the 717 setups carrying a `SetupTarget`, 111 reach it. At 1.0 the bar passes two thirds of
    them and means nothing; at 3.0 only 51 clear it and the bypass is theoretical.

    **What was deliberately not touched, and why.** Gates 1 to 4 — no price series, a stale close,
    a silent venue, no invalidation level — are not timidity. They are the absence of the three
    things an entry is made of, and gate 4 most of all: a plan with no level to be wrong at is the
    one output this file must never print, and demanding an exact invalidation is what makes every
    reward figure a measurement rather than a hope. Nothing here invents a direction either. Every
    direction printed was already measured by `jobs/setup.py` and stored; what changed is which of
    them reach the reader.

    **What this costs, stated plainly.** 205 directional calls instead of 131 is more exposure to
    being wrong, and the honest guard is not a gate — it is `DecisionLog`. `rewardRisk`,
    `baseRateShare` and `baseRateCount` are now stored on every decision for exactly this reason:
    `jobs/horizons.py` rewrites `SetupTarget` every run, so the figure a call rested on survives
    only if the call records it. Grouped by `gate`, the matured +1/+5/+20 columns answer whether
    `trend-long` and `trend-short` pay, and grouped by whether `rewardRisk` cleared 2.0 they
    answer whether the bar is in the right place. Principle 7 is the whole safeguard here: every
    signal is checked against what actually happened afterwards, and a rule table that loosened
    without a way to measure the loosening would be the one change this file could not defend.

44. **A past day that looked like this one did not have today's headline in it.**
    Rule 43 took "thin news" out of the way of a direction, which was right: an absent
    explanation is not evidence against a move. This is the opposite case and it is a real
    check. `jobs/analogs.py` matches past days on three factors — the one-day return, the volume
    multiple and the five-day return — and nothing else. So when the published coverage carries a
    direction and it is the *opposite* one, a matched set that agrees with the setup is not weak
    support for the trade. It is a sample drawn from days that are missing the thing most likely
    to drive the next move, and counting it is walking into the trap that the history looked good.

    Three effects, and the asymmetry between them is the rule:

    - **The history leg is withdrawn.** `analogConfirms` still answers what it always answered;
      `confidenceFor` and `confirmLine` stop counting it. One grade step, and the page says which
      set was withdrawn and how many days were in it — `confirmLine` cannot carry that sentence
      when volume also confirms, so it lives in `notes` where the qualifications are.
    - **Gate 8 refuses outright.** That gate carries a direction whose own conditions
      `jobs/setup.py` did *not* all find, on a single stored figure. Thin by construction and
      contradicted by the present is the blind trap, so the name falls through to gate 9 and keeps
      its developing read with the coverage named first in `waitingOn` — it is the only item in
      that list about today rather than about a measurement that has not filled.
    - **Gates 6 and 7 do not refuse.** There `setup.py` found and confirmed its conditions, and a
      word list over headlines does not get to overrule a measurement. A note and a grade step.

    **Coverage can take evidence away and can never add any.** An agreeing tone is not a fourth
    confirmation and cannot lift a grade. Principle 5 is explicit that current human attention is
    context and not proof, and the reading is a word list with no bodies, no negation and no
    sarcasm, as every surface showing it already says. That is good enough to withdraw a claim and
    not good enough to make one, and the two bars are different on purpose.

    Rule 21 governs the input. `jobs/human.py` writes `neutral` both for a balanced window and for
    one where too few headlines took a side, and a missing `HumanSignal` row is a third thing
    again. Only an actual published disagreement may act: 378 of 454 stored readings on 2026-10-09
    are neutral, so mapping neutral to a direction would have made this a deduction on nearly
    every name in the pool.

    Measured over the pool on the day it went in, against rule 43's table:

        action      before 43   after 43   after 44
        LONG               58         78         78
        SHORT              73        127        124
        WAIT              346        272        275

    Nine directional calls carry the note (AAPL long into negatively worded coverage; ADBE, APTV,
    IBM, INTU, MDT, RIVN, SLB and USDKRW short into positively worded coverage), four of them
    dropping a grade for the withdrawn set. Three promotions were refused: **AXP, BWA and MGA**,
    all falling trends with the volume to clear gate 8 — 1.62x, 1.31x and 1.40x — and coverage
    worded the other way, two of the three on a story-rate spike. Those three are the rule's
    whole purpose, and they are held back rather than deleted: each keeps its developing read
    with the coverage named first in what it is waiting on.

    One thing to know before checking that against a page, because it looks like a contradiction
    and is not. AXP reads **WAIT on /stocks and LONG on /asset/AXP**. That is the deliberate
    two-horizon split, not this rule: `getDecisionRows` and `tools/decide.mjs` read swing and
    longer only — a front page that re-decided itself through the session would be a different
    page on every visit — while the asset panel reads all three, and AXP's intraday row is `buy`.
    The refusal here applies to the falling swing trend, which is the read the lists and the log
    are built on. Verified on both pages on 2026-10-09.

45. **A measurement read in one direction only is a bug, and three of them were costing 275 WAITs.**
    The live site showed 34 of 36 crypto, 24 of 27 currency pairs and most of PSX sitting in
    WAIT with every input table fresh. The first instinct is that the thresholds are timid. They
    were not. Three separate things were structurally unreadable, and each one is the same shape
    of fault: a stored measurement the rules could use in one direction and not the other.

    - **Relative strength could only ever subtract.** `peersAgainst` existed and `peersConfirm`
      did not, so a name 11 points *behind* its group cost a confidence grade and a name 11 points
      *ahead* of it counted for nothing. That is principle 2 — "relative strength against peers
      matters more than a raw return" — wired up backwards. It is now the fourth confirmation leg
      and the third carrier at gate 8, on the same band `REL_AGAINST_AT` already defined, so one
      threshold still means one thing. **49 refused names cleared on it.**
    - **A currency pair could never hold an analog.** `jobs/analogs.py` matches past days on three
      factors, one of which is a volume ratio, and treats a missing factor as not-a-match. No
      venue publishes volume for FX. So all 27 pairs were skipped before a single candidate was
      considered, and held **zero** stored analogs while every other class was near-complete — two
      of the four things that can confirm a direction permanently absent. The job now matches a
      no-tape instrument on its two return factors and records in `toleranceNote` that volume was
      not among them. All 27 pairs now carry graded rows, averaging **762 matched days** each.
    - **`mixed` was being read as "no information".** `trend` requires the close, the 20 day mean
      and the 50 day mean to line up, and writes `mixed` when they do not. But the two means are
      still one above the other. Of the 123 refused names whose swing state was `none`, **119 had
      a measurable side** — 55 with the fast mean above, 64 below, 4 inside the quarter-percent
      floor. `setup.py` now writes a `bias` condition saying which, and gate 8 falls back to it.

    Three properties that keep this from being a loosening dressed as a fix:

    - **The weaker reading buys a chance at the gate, not a pass through it.** A bias is subject
      to every requirement a trend is: a carrier, a horizon that does not disagree, coverage that
      does not contradict. Its sentence says "price is between its own averages, with the 20 day
      above the 50 day" and never "the trend is up", because three things agreeing and two things
      agreeing are different findings and promoting one into the other's word is the overclaim.
    - **`bias` is a new condition, not a widened `trend`.** Rule 23: `thesis.py` parses the same
      string, and changing what `trend` may say would change what a held thesis means on every
      asset. Added tokens are ignored by `compare()`; redefined ones are not.
    - **The High bar stays at two.** A fourth leg must not re-grade the site by arithmetic. Two
      independent confirmations is High because two is what "independently confirmed" means.

    A fourth fault, found while fixing the first: **the peer band itself was one constant for
    every market**, which is rule 42 again in the one place rule 42 had not been applied.
    Measured as the median |relStrength| per market — FX 1.13, PSX 3.53, US 3.71, Commodity 4.35,
    Crypto 5.56 — a flat 3 points passed **58% of US names and 7% of currency pairs**. One number
    was simultaneously too loose to be evidence about an equity and too strict to ever fire on a
    pair. `REL_BAND` is now twice each market's own median, to the nearest half point: FX 2.5,
    PSX 7.0, US 7.5, Crypto 11.0, with Commodity and Other taking the US figure because four
    observations is not a sample to set a threshold from.

    That correction **costs** directions rather than adding them — 23 of them — and it is kept
    because the measurement says the old bar was not evidence. A threshold is set by what makes it
    mean something, never by the count it produces. Rule 39's line applies in both directions: do
    not loosen a gate because a market is quiet through it, and do not keep a loose one because
    tightening it reads worse.

    Measured across the pool, each step on the same day and the same stored inputs:

        action    rule 44   + peer leg   + FX analogs, bias   + per-market band
        LONG           78          89                   113                105
        SHORT         124         159                   173                158
        WAIT          275         229                   191                214

    By class, against the live site that prompted this: **crypto 34 WAIT to 20**, **PSX 81 to
    59**, **US 126 to 107**, **FX 24 to 23**.

    **FX barely moved, and that is the finding rather than a failure.** All 27 pairs now hold
    graded analogs averaging 762 matched days, and every one of them lands within a point or two
    of an even split — AUDUSD 363 of 728, EURGBP 513 of 1023, EURUSD 231 of 477. A pair has no
    volume, its matched history is a coin flip, and its 20-session gap against its peers has a
    median of 1.13 points. There is very little to be confident about in a currency pair from free
    daily closes, and the right output for that is a stated absence of a finding, not a direction
    manufactured to fill the column. What changed for FX is that the page can now say "checked,
    and the history says nothing" where it used to say "not measurable".

    **What is still WAIT, and why it is not timidity.** 2 names have no stored invalidation level,
    so there is no price at which being wrong is known — the one thing a sniper entry cannot do
    without. 1 sits at the horizon disagreement with a reward too small to carry it. The other 211
    fall at gate 9: a direction exists and no stored figure carries it. That is the condition the
    gate was written for, not a formality to route around, and **203 of them are on the page as
    developing reads** with the exact shortfall named and ordered by how close it is to clearing.

    **One thing that will make this look broken when it is not.** `lib/cached.ts` wraps
    `getDecisionRows` in `unstable_cache` at an hour, shared by the overview and all five class
    indexes, and those pages are statically prerendered. So after a decision pass the **list**
    pages can read up to an hour behind while the asset pages, which are dynamic, are already
    current. Seen during this very change: `/crypto` said "4 long, 32 waiting" while `DecisionLog`
    and `/asset/algo-algorand` both said 16 long. Nothing was wrong with either. `rm -rf
    .next/cache` before `npm run build` is what makes a local rebuild show the new verdicts at
    once; in production the hour simply elapses.

    **What was asked for and deliberately not built.** Deriving an asset's direction from its
    sector, its index or a beta proxy when its own feeds are thin. That is not a fallback, it is
    substitution: it prints another instrument's reading under this instrument's name, and hard
    rule 2 forbids filling a missing number from anywhere. Acting on an analog share above 50%
    rather than `ANALOG_SHARE_CONFIRMS`. HMC's own set is 377 of 748 — on that sample a fifth of
    one standard deviation from a coin flip — and the 0.55 bar exists because the page was already
    calling that "confirmed". And removing the Low grade. Confidence is a count of how many
    independent things agree; deleting the word does not change the count, it only stops the
    reader being told, which is the one thing that costs money rather than saving it.

46. **"Compression precedes expansion" is false in this database, and the measurement is the
    deliverable.**
    The brief was to scan for pre-breakout compression, volume anomalies and early accumulation so
    the engine catches a move before it happens. Every one of those is a standard, widely held
    idea. None of them survived contact with the eight years of closes already stored here, and
    the right response was to measure first rather than to build three columns that encode nothing.

    Method: every asset-session with enough history behind and 20 sessions ahead of it — **582,252
    of them** — bucketed by the condition on the day, scored by what the next 20 sessions actually
    did. Realised volatility is the standard deviation of the 20 daily returns ending on the day;
    "compressed" is the bottom fifth of that asset's own trailing history. Read-only; nothing was
    written.

        bucket                       n        up rate   median |move|   median signed
        all days               582,252          54.2%           5.53%          +0.70%
        compressed vs own 120  140,657          52.4%           5.14%          +0.36%
        compressed vs own 250  133,463          52.9%           5.00%          +0.42%
        volume >=1.5x, flat day  7,090          54.4%           5.53%          +0.80%

    **A compressed day is followed by a *smaller* move than an ordinary one**, on either baseline,
    over 133,000 observations. Quiet begets quiet. The coil does not spring; it stays coiled. An
    engine that treated compression as a pre-breakout signal would be reading a volatility cluster
    backwards and would fire hardest on exactly the names least likely to move.

    **The "institutional footprint" — heavy volume with no price move — is indistinguishable from
    the baseline.** 54.4% against 54.2%, and the median absolute move is 5.53% in both buckets to
    two decimal places. The first pass of this measurement reported 54.4% as significant against a
    coin flip, which it is: 7.4 standard errors. Against the *right* denominator it is 0.34, which
    is nothing. That is the fault this repository keeps having — rule 9, rule 39, rule 42, the
    news lane's ordering, the volume denominator — found once more, in the measurement built to
    check a new idea rather than in the idea itself.

    **What the same data does say, which is nearly the opposite.** A second pass, 680,800
    sessions, on the rule the engine already applies:

        bucket                       n        up rate   median |move|   median signed
        all days               680,800          54.5%           5.52%          +0.75%
        volume >=1.2x, any move 147,556         55.3%           6.50%          +1.23%
        volume >=1.2x, day UP    66,725         54.7%           6.80%          +1.13%
        volume >=1.2x, day DOWN  60,509         55.8%           6.68%          +1.40%
        volume >=2.0x, day UP    17,898         53.9%           7.85%          +1.06%

    Volume predicts **magnitude** and holds up well doing it: a session at or above 1.2x its own
    average is followed by a move about a percentage point wider than average, and 2x by nearly
    two and a half. That is a real, large-sample effect and it is the one thing in this whole
    exercise that works.

    It does **not** predict direction, and on a down day it mildly argues the other way: a heavy
    down session is followed by a rise 55.8% of the time against a 54.5% baseline — 6.5 standard
    errors on 60,509 observations — where a heavy *up* session is followed by a rise 54.7% of the
    time, which is one standard error from the baseline and therefore nothing.

    **This is a live problem for the rule table and it is deliberately not fixed here.**
    `volumeConfirms` treats volume at or above `VOLUME_CONFIRMS_AT` as confirming the *direction*,
    counts it as one of four confirmations, and carries a withheld trend on it at gate 8 — for
    shorts as well as longs. The measurement says that is the wrong reading of a real signal:
    volume says a move of some size is coming, not which way, and on the short side it leans
    against. Changing it would re-grade every asset on the site, so it belongs behind the outcome
    log rather than in the same session as the measurement: `DecisionLog` now records `gate`,
    `rewardRisk` and `baseRate` on every row, and `trend-short` against `short` at +1, +5 and +20
    sessions is the comparison that should decide it. Principle 7, and the first time this project
    has had the columns to honour it on its own rules.

    **What was built instead.** The class index pages now split their waiting list the way the
    overview has always split it: 203 of the 214 refused names carry a forming read — a measured
    direction with a named shortfall and a number saying how far off it is — and all 203 were
    filed under "no direction today" next to names whose feed is dead. `/crypto` said "32 waiting"
    when 14 of those had a direction. That list, ordered by closeness, is the honest version of
    "catch it before it is obvious": not an invented early signal, but the names where the
    direction is already readable and the confirmations have not all arrived.

47. **The target pass only ever looked at a quarter of the setups it had the levels for.**
    `run_targets` selected `state IN ('buy','short')` and wrote a target for every one of them,
    100% coverage, 215 rows. Every other current setup got none. Measured 2026-10-09: **745 swing
    and longer rows in state `wait` or `none`, every single one carrying both an entry and an
    invalidation level**, held no target at all. The page printed "No clear target stored" and the
    panel had no reward against risk and no expectancy to put beside it.

    Those rows are not directionless. `wait` means setup.py found the trend clear and the other
    conditions incomplete, and the trend verdict is in the conditions string — 398 of them. A
    swing `none` row carries the `bias` verdict rule 45 added — 149 more. Those are the directions
    gate 8 already acts on, so the decision had a direction while the target pass, reading the
    same column, did not.

    `aimed_at` now reads the three in order — stated state, then trend, then bias — and the pass
    covers **823 setups, 608 of them on a direction the setup recorded without acting on**. 253
    are still skipped and should be: a `longer` row carries no bias condition, and a mixed trend
    with nothing beside it names no side. A target with nothing to point at would have its
    direction chosen by the job rather than measured.

    Nothing new is computed. The same three methods, the same ATR multiple, the same pivots, the
    same analog set. A derived row carries one extra sentence in its note saying the direction was
    recorded and not acted on, so a reader is never shown a target measured toward a withheld
    direction without being told that is what it is.

    **Second fault, found by fixing the first.** `structure` takes the nearest price the series
    already turned at, whatever that is — so where the nearest pivot sits a few ticks above the
    entry the row is written with a reward of 0.02x and the panel prints "0.0x". Live on Algorand:
    entry 0.10 to 0.14, stop 0.10, structural target 0.14. Every number true, and together they
    describe a trade with no room in it, printed as though the figure were missing.
    `preferredTarget` now passes over a method whose reward is under a tenth of the stop distance
    and takes the next one — which is where the volatility method earns its place in the order,
    because a multiple of the asset's own true range cannot fail to produce a distance. Algorand
    now reads 0.16 at 0.71x. When every method is flat the real figure is still shown: a trade
    with no room is a finding, and hiding it is the only dishonest outcome available.

    **What the coverage then revealed, and it is the number to act on.** All 265 directional calls
    now carry a reward figure, none below 0.1x. The median is **0.41x**: 28 of 265 reach 1x and
    **6 reach 2x**. The engine's typical call risks two and a half times what it stands to make at
    the nearest measured target. That is not a rule-table problem and no threshold in
    `lib/decision.ts` can fix it — it is where `jobs/setup.py` places the invalidation level,
    which is the lowest close of the trailing window and is wide by construction. Sniper entries
    are a stop problem before they are a conviction problem, and this is the first time the site
    has had the coverage to say so.

48. **The stop was the whole recent range, and tightening it is the first change here that had to
    be backtested before it was made.**
    Rule 47 ended by naming the median reward of 0.41x as a stop problem rather than a rule-table
    problem. It was. `jobs/setup.py` placed the entry at one end of the 20-session close range and
    the invalidation at the other, so the risk taken on every call was the entire recent range —
    a median of **10.4% of the price**, quartiles 6.6% to 15.8%.

    **Why this one needed evidence and the others did not.** Reward against risk is a ratio.
    Narrowing the denominator raises it arithmetically and also raises the chance the stop is
    taken out by noise before the target is reached, so the ratio cannot say whether a change is
    an improvement. Only expectancy can. Backtested over the whole stored history — entry at the
    window extreme with price already there, first touch across the next 20 sessions, outcome in
    units of the risk taken:

        long, n=174,277      R:R   target hit   stopped   mean R
        window extreme      0.37        58.5%     18.3%    0.030
        0.75 sigma          2.67        37.5%     61.1%    0.401
        1.0 sigma           2.00        41.0%     56.8%    0.263
        1.5 sigma           1.33        46.8%     49.2%    0.139
        2.0 sigma           1.00        50.9%     42.8%    0.082
        3.0 sigma           0.67        55.9%     32.4%    0.033

    Mean expectancy rises all the way to the tightest stop tested, which is exactly why the
    tightest was not taken. The simulation walks **daily closes**, so a stop counts as hit only
    when a close finishes beyond it and every intraday touch is missed — the tighter the stop, the
    more of them, so the top row is the most optimistic line in the table and the least
    trustworthy. 1.5 sigma takes a 4.6x improvement in mean outcome while still finishing roughly
    half its trades at the target, rather than becoming a lottery with a good average. The level
    is bounded by the window extreme, so it can only ever tighten.

    Median risk window on the swing rows: **10.4% of price to 2.75%**. All 475 use the volatility
    stop; none fell back to the range.

    **Say which rows, though.** That figure is the swing rows, which is where the fault was.
    `horizons.py` writes the `longer` rows and has always placed their levels at structural
    pivots rather than at range extremes, so they were never the wide ones: measured on the 286
    directional calls today, **176 take their stop from the tightened swing row at a median of
    2.31% of price and 110 from a longer row at 2.94%**. Across all of them the median risk is
    2.57%. The longer rows are not touched here and should not be by this constant -- 1.5 of a
    *daily* dispersion is the wrong unit for a quarterly read, and extending an untested multiple
    to a different timeframe is the move this rule exists to argue against. If they want
    tightening they need their own backtest.

    **The target preference changed with it, and for the same reason.** `structure` led the
    preference order on a readability argument — the nearest price the series actually turned at
    is what "where would I take this off" sounds like it should mean. Measured against the new
    stop over the current setups: structure a median of **0.41x** over 446 rows, volatility
    **2.04x** over 465. The nearest level a series turned at is usually very near, and as an exit
    it is a real level with a poor payoff. The deciding argument is not the ratio but which
    configuration was tested: the backtest above used a **volatility** target, and the structural
    one — the one every card was showing — has never been through it.

    **Then the asymmetry bar had to be re-derived, and this is the part worth remembering.**
    `ASYMMETRY_CLEARS` was 2.0, chosen because 111 of 717 setups reached it: a little under one in
    six. Every reward figure then roughly tripled without a single target moving, and 2.0 went to
    catching **44%**. By its own written justification it had stopped meaning anything. Re-measured
    on the same basis, 2.75 passes 109 of 745 — 15%, against the original 111. Same property,
    re-read after the distribution moved. **Fourth time in this file.** Rule 42 is the general
    form and the lesson it keeps teaching is that a threshold is a statement about a distribution,
    so it has to be re-read whenever the distribution does. Leaving it at 2.0 would have silently
    promoted 216 extra names through gate 8 and reported it as a win.

    Across the pool, same day and same stored closes:

        measure                     before      after
        median reward against risk   0.41x      1.87x
        calls reaching 1x          28 / 265   240 / 286
        calls reaching 2x           6 / 265   122 / 286
        median risk window           10.4%      2.75%

    **The finding that matters more than any of this.** The same backtest run on the short side,
    104,336 setups: mean R is **negative at every stop width except the two tightest**, and
    negative under the current rule at −0.068. The long side is positive everywhere. The site
    issues more shorts than longs — 174 against 112 today — so the majority of its directional
    calls sit on the side with no measured edge. Nothing here changes that, and no stop width can:
    it is a statement about the direction, not about the risk. `DecisionLog` records gate and
    reward on every row and matures at +1, +5 and +20 sessions, which is the only thing that will
    settle whether the short side should be issued at all.

49. **A gate that acts on a new direction has to tell the level writers about it.**
    The report was that short targets print above the entry. They do not: measured over today's
    calls, **389 of 389 short targets sit below their entry and 282 of 282 long targets above**.
    `target_rows` has always taken a direction and signed the distance from it, and `aimed_at`
    now hands it the right one.

    What the check found instead was worse. **70 live SHORT cards had the stop on the wrong side
    of the entry** — 53 from `wait` rows and 17 from `none` ones. AHCL read SHORT with entry 16.17
    and stop 15.81, so the level the panel labelled "the price at which this is wrong" sat on the
    side the trade needs price to reach. That is exactly the WTL and STLA failure the
    `ShortLevelsAreMirrored` tests were written for, in a table of 477 names, reintroduced here.

    The cause is the one worth writing down. `setup.py` chose its entry and its invalidation by
    **state**, and until gate 8 existed that was right: the only rows anything acted on were `buy`
    and `short`, so the state was the direction. Rule 45 and rule 47 then taught two other places
    to read a direction out of a `wait` row's trend and a `none` row's bias — `lib/decision.ts` to
    decide on it and `jobs/horizons.py` to aim a target at it — and nobody told the block that
    places the levels those two are describing. Three readers of one idea, and the third was still
    answering the question it was asked before the idea existed.

    Both now derive the aim the same way, in the same order: the state, then the trend verdict,
    then the bias. `setup.py` reads it off the three locals it just wrote the conditions from;
    `horizons.aimed_at` parses it back out of the string, because it runs in a later job. All 315
    downward-aimed swing rows now put the stop above the entry, and all 290 directional calls
    carry both a stop and a target on the correct side of theirs.

    **The general form, and it is not "test the levels".** A rule that starts acting on a new
    input has to be followed to every place that input is *described*, not just every place it is
    read. The direction was computed correctly, parsed correctly and acted on correctly; what
    broke was a fourth file that renders the consequences of it and was never part of the change.
    The counter-measure is already in the repository and did not fire: `ShortLevelsAreMirrored`
    asserted on a literal source line, so when that line was rewritten the test was rewritten with
    it rather than failing. A guard that is edited by the change it guards against is not a guard,
    which is why those assertions are now calls into `stop_level` and `aimed_at`.

50. **Every measured direction now prints, and `confidence` is the only thing left holding the
    distinction a gate used to hold.**
    The carrier requirement was the last filter. Gate 8 asked for one of three stored figures --
    volume at or above its own average, a peer gap wide enough for the market, a reward at
    `ASYMMETRY_CLEARS` -- before it would act on a direction whose other conditions were
    incomplete. Measured 2026-10-09: **176 of the 187 refused names had a measured direction, an
    entry and a stop**, and were held back only because none of the three was present.

    The argument for the carrier was that such a direction should not print as an action. The
    argument that beat it: `confidence` already said exactly that, with more resolution than a
    gate can. **A gate is one bit** -- acted on, or not. The grade counts four independent
    confirmations and reports none as Low, one as Medium, two or more as High. So a carrier-less
    direction was already distinguished from a confirmed one by the field built to distinguish
    them, and the gate was the same judgement made twice, the second time by deletion.

    Three other refusals went with it, each demoted to the thing it always was:

    - **Mixed horizons** is a note. A swing read and a quarterly read measure different windows
      and answer different questions, which is the sentence the horizons block on every asset page
      has always carried; refusing both because they differ withheld the nearer one on the
      strength of the further one. It still costs a grade, because there is no agreeing second
      timeframe to count.
    - **Contradicting coverage** keeps all of rule 44's substance -- the matched past days stop
      counting, the grade falls, the contradiction prints -- and stops deleting the direction.
    - **The asymmetric-reward bypass** is gone as a concept, because there is no longer a refusal
      for it to bypass. `ASYMMETRY_CLEARS` now only marks a gate name.

        action      before   after
        LONG           112      166
        SHORT          178      301
        WAIT           187       10

    **What stayed, and why those are not caution.** 2 names have no stored invalidation, so there
    is no price at which being wrong is known -- the one output this table must never print. 8
    have no measured direction at all: a mixed trend with the two averages inside `BIAS_MIN_GAP`
    of each other, where a side would be this file's choice rather than a measurement.

    **What makes this defensible rather than reckless is that it is measurable.** The thin calls
    are written to `DecisionLog` as `unconfirmed-long` and `unconfirmed-short` -- 170 of today's
    467 -- beside `trend-long` and `long`, and the table matures at +1, +5 and +20 sessions.
    Within weeks, grouping those gates by outcome answers whether an unconfirmed direction is
    worth printing. Letting a thinner case through is only defensible because the loop that judges
    it was built first. Principle 7.

    **The one thing that was asked for and not done: the Low grade stays.** It is the count of how
    many independent things agree, and deleting the word does not change the count -- it removes
    the reader's only way to tell a four-confirmation call from a none. 129 of today's 467 calls
    are Low. With real money that label is the most valuable text on the card, and it is the one
    piece of this engine whose removal would cost something that no later measurement could
    recover.

    **Consequence to clean up if this policy holds.** `developingRead`, `Decision.developing`,
    `byCloseness`, the overview's developing block and the class pages' Forming list are now
    unreachable: everything that could produce a developing read produces a direction instead. The
    code is kept because the rule behind it is sound and this is a policy, not a measurement --
    but built-and-unused is this repository's recurring fault, and if every direction still prints
    a month from now, all of it should go.

    **And the warning that outranks the change.** 301 of 467 calls are shorts. The backtest in
    rule 48 measured mean expectancy on the short side as **negative at every stop width but the
    two tightest**, over 104,336 setups, where the long side is positive everywhere. This pass
    did not make that better; it increased exposure to it by 123 names. The geometry of every one
    is correct and the evidence behind each is published on its card. Whether the short side
    should be issued at all remains the open question, and `DecisionLog` is now the only thing
    that will answer it.

51. **These are trend readings, and the measurement that says so is the one worth keeping.**
    Asked to confirm and document that the verdicts are forward-looking entries rather than
    lagging trend chasers. They are not, and the stored history says so plainly enough that
    writing the opposite into the methodology page would have been the single most harmful line
    in this repository.

    The condition behind nearly every direction is `close > 20d > 50d`, or where those three do
    not line up, the two averages on one side of each other. Both describe a move that has already
    started; that is what a moving average is. Measured over the 467 directional readings on
    2026-10-09:

        reading      move already made (20 sessions)   range position   trend age at entry
        LONG  (166)  median +3.1%, upper quarter +11.3%        72%           median 40 sessions
        SHORT (301)  median -3.9%, lower quarter -7.2%         18%           median 24 sessions

    A typical long is a name that has already risen, sitting near the top of its own range, about
    **forty sessions** into the trend being read. Only 16% of longs and 13% of shorts are written
    within five sessions of the trend starting; 19% of longs are written after sixty.

    **This is not a defect to fix, and the attempt to fix it was already measured.** Rule 46
    tested the two standard pre-trend detectors against 582,252 asset-sessions. Compression is
    followed by a *smaller* move than average, not a larger one, and a volume spike with no price
    move is indistinguishable from the baseline. The same data does support trend continuation in
    size: a session at 1.2x its own average volume is followed by a move about a percentage point
    wider. So the engine is doing the thing the data supports and not the thing it does not, and
    the honest description of it is "a trend reading with a measured stop and a measured target",
    which is now what `/methodology` says in those words.

    **The general rule this is an instance of.** A request to confirm something is not a request
    to agree with it. Every claim this project makes about itself is checkable against the same
    stored rows the claims are built from, and when a flattering description and a measurement
    disagree, the measurement is the deliverable. Principle 8: a thin reading said plainly is
    worth more than a confident one that cannot be checked.

52. **The feedback loop is running, and what it can and cannot yet say.**
    `DecisionLog` holds 2,054 rows from 2026-10-02 onward, every one carrying the close it was
    measured from. `matureRows` in `tools/decide.mjs` returns to each past row and records what
    followed at +1, +5 and +20 **stored sessions** for that asset, and `tools/scorecard.py` scores
    the matured ones against the direction and the stop they stated. State on 2026-10-09:

        status      rows    window     measured   pending
        measured1   1,076   +1              1,100     954
        measured5      24   +5                 24   --
        open          954   +20                 0   --

    No +20 figure exists yet and cannot: the oldest row is seven days old and twenty sessions have
    not elapsed. The first will land around 2026-10-30.

    The +1 scorecard reads 124 right, 95 wrong, 41 stopped out of 263 matured rows -- and prints,
    every time, that those 263 rows are **95 distinct names over 5 sessions**, so they are repeated
    observations rather than independent trials. The per-grade split currently has Low ahead of
    High, which is noise at 37 High rows over a one-session horizon and must not be read as a
    finding. The tool refuses to publish a rate under `MIN_SAMPLE` for exactly this reason.

    **What is genuinely closed and what is not.** The measurement loop is closed: decisions are
    logged with their gate, their reward and their base rate, outcomes are recorded against them,
    and a scorer compares the two. The *learning* loop is not -- nothing reads the matured rows
    and changes a threshold. That is deliberate and it is the right order: rule 48's stop width
    and rule 50's removal of the last gate were both argued from backtests over stored history,
    and feeding a live 263-row sample back into those constants would be fitting to noise. The
    sample that can answer the open questions -- whether `unconfirmed-*` calls pay, whether the
    short side should be issued at all -- is weeks away, and the columns to answer them with are
    already being written.

53. **The short side's problem is not the short side. It is US equities.**
    Rule 48 measured the short side as negative at every stop width but the two tightest and left
    the question open. Conditioning the same backtest on what the rule table can see at decision
    time answers it. 171,010 shorts, eight years, entry at the close with a 1.5 sigma stop and a
    2.0 sigma target, first touch over 20 sessions:

        market          n        target hit   mean R
        crypto     26,545             46%     +0.057
        PSX        20,208             46%     +0.054
        FX         14,544             45%     +0.035
        US        105,705             38%     -0.111
        Commodity   4,008             38%     -0.127

    Pooled, shorts read -0.053 and that sounds like "shorting does not work here". Split, **three
    of five markets are positive and the entire loss is the 105,705 US observations**. 2018 to
    2026 is a period of sustained appreciation in US equities; a short there was fighting a drift
    the other markets did not have to the same degree. A second, independent cut says the same
    thing about timing:

        already fallen        n        target hit   mean R
        less than 3%     44,761             44%     +0.008
        3 to 10%         67,062             41%     -0.052
        more than 10%    59,187             39%     -0.101

    So `shortNeedsBacking` asks for at least one of the four confirmations when either applies:
    the market measured negative, or the name has already fallen past `SHORT_LATE_AT`. It refuses
    rather than downgrades, because a grade is a statement about evidence and this is a statement
    about the trade.

        measure                     before     after
        LONG                           166       166
        SHORT                          301       239
        WAIT                            10        72
        US shorts                      158        96
        shorts in positive markets     46%       58%
        expected book outcome      +0.0221R  +0.0424R per position

    The last line is the point and it is worth reading carefully: it is the measured per-market
    expectancy applied to today's book, so it is an estimate from history and not a result. It
    says the gate removes 62 positions and **+6.88R of expected loss**, which is the whole of the
    case for holding one direction to a different bar than the other.

    **The asymmetry is in the data, not in an opinion about the two sides.** Longs measured
    positive in the same backtest everywhere, so longs are not gated. If a later regime turns US
    equities down, this table is wrong in the direction of missing trades rather than taking bad
    ones -- which is the right way round for a number resting on one regime, and `DecisionLog`
    records every `short-unbacked` so the live record will eventually argue with it.

54. **Four candidate entry rules were measured against the moving-average stack. Three are
    earlier and slightly better, and all three are far rarer.**
    Rule 51 established that the engine enters a median of 40 sessions into a long. The obvious
    response is to replace `close > 20d > 50d` with something that fires sooner, so four
    candidates were backtested on identical terms -- same stop, same target, same forward window,
    same outcome measure -- with two numbers each: how many sessions the stack had **already**
    held when the rule fired, and what it paid.

        long side          n        stack age   fires at 0   mean R
        ma_stack      223,667               8          0%     0.128
        breakout20     90,029               5         30%     0.133
        squeeze_break  11,361               1         42%     0.153
        vol_flip       13,408               0         58%     0.146
        inflection     49,395               0        100%     0.099

    Three findings, and the third is the one that decides what to build.

    **Earlier is not automatically better.** `inflection` -- the fast mean turning while price is
    still the wrong side of the slow one -- fires before the stack exists every single time and
    pays *less* than the stack does. Being early is only worth something if the thing being
    caught early is real.

    **The squeeze result does not contradict rule 46, and the distinction matters.** Rule 46
    measured compression as a standing state and found it followed by *smaller* moves. This
    measures the **expansion bar out of** a compression, which is a different event: not "it is
    quiet so something will happen", but "it was quiet and something just did".

    **But every candidate that beats the stack is rare.** `squeeze_break` fires on 11,361
    sessions against the stack's 223,667 -- 5% as often -- and the margin, 0.128 to 0.153, is
    about two standard errors on that sample. Swapping the entry rule would cut the pool from 467
    directions to a few dozen and buy an improvement the sample can barely see. So they are not a
    replacement for the trend, and the honest use of them is as a fifth confirmation and as a
    marker on the card saying this one was caught at the start -- which keeps the coverage, tells
    the reader what rule 51 says they are owed, and lets `DecisionLog` settle the two standard
    errors with live rows instead of an argument.

55. **The two entry rules that beat the stack are stored as a fifth confirmation, and the fifth
    leg is the first one that says *when* rather than *how much*.**
    Rule 54 ended with what to build and this is it. `squeeze_break` and `vol_flip` are computed
    per session in `jobs/factors.py`, stored on `AssetFactor` as `entryTrigger` and
    `triggerDirection`, and read by `confirmationCount` beside the four legs that were already
    there. Nothing about the entry changed: the stack still decides the direction, and a name
    with no trigger is graded exactly as it was.

    **Why a fifth leg and not a better fourth.** The other four read a *state* -- a second
    timeframe, volume, matched past days, the peer gap -- and every one of them reads the same on
    the fortieth session of a trend as on the first. These two read an *event* on one bar. Rule
    51 measured the engine entering a median of 40 sessions into a long and nothing stored could
    tell a reader otherwise; this can, and the card now says so in the confirmation line:
    "Confirmed by volume 2.4x its average and a break out of its quietest stretch in six months
    this session."

    **What is measured and what is not, stated plainly.** Rule 54's table is the long side.
    `tools/research/entry_triggers.py` computes the short side on identical terms and those
    numbers were never tabulated, so the fifth leg backs a short on a claim weaker than the one
    it backs a long on. It counts anyway, for two reasons. Splitting the count by side would put
    a second implementation of "how much backs this" in the file -- the exact fault the comment
    above `confirmationCount` exists to prevent -- and `shortNeedsBacking` already refuses an
    unbacked short in a negative market whatever the leg count says. `DecisionLog` stores the
    gate on every row, so the live record settles it. **Tabulating the short side is the first
    thing to run when the database is reachable again.**

    **One deliberate divergence from the backtest.** The sweep used a mean-based 20-session
    volume ratio because that was cheap inside it; `vol_flip` here reads this file's own
    median-based ratio, which splits weekend sessions from weekday ones. So the live rule is a
    near neighbour of the measured one rather than the measured one, and the 0.146R belongs to
    the neighbour. Two definitions of "busy" inside one repository would be worse.

    **And a real bug fell out of wiring it.** `tools/decide.mjs` selects the factor row for the
    nightly `DecisionLog` and was never updated when `r20` was added on 2026-10-09, so the log
    has been deciding late shorts on half of `shortNeedsBacking`. In US and Commodity the market
    half fires anyway and only the printed reason differed; in Crypto, PSX and FX -- the three
    markets that measured positive -- the fall half was the only thing standing between a late
    short and a printed SHORT, so **the site refused those names and the log recorded them as
    taken.** That is the one disagreement this file cannot have, because the log is what the
    refusal is eventually judged by. Fixed in the same pass, with the trigger wired in beside it
    so the two cannot drift apart the same way again. The seam now has six fields and six tests,
    and the count is the argument: an optional field cannot fail to exist, so the type is not the
    guard.

56. **The pipeline could not see itself. `ChunkRun` had no writer, so the table the freshness
    panel is built on was empty and every claim made about it was a claim about an empty table.**
    `jobs/runlog.py` is a careful module -- it writes a row on the exception path before
    re-raising, on its own short-lived connection so a caller's rollback cannot take the log with
    it, and it refuses a blank note. It had **no callers**. `prices.py` imported `parse_chunk`
    and `slice_of` from it and nothing else, so the schema's "a failed chunk is a row rather than
    something to go hunting for in a log that needs a sign-in to read" described a table with
    nothing in it, and so did RESUME.md.

    The three price lanes now run inside it. That is the whole of the fix and it is worth
    noticing how little code it was: the module was finished, and what was missing was the three
    `with` statements that use it.

    **On top of it, a circuit breaker, derived and not stored.** `nbt.get`'s `RETRY_HOST_BUDGET`
    stops one *run* from spending its timeout on a dead host, and then the dictionary holding the
    count dies with the process -- so a source blocked all of yesterday is asked again today at
    full budget by every lane that touches it. `jobs/breaker.py` remembers, by reading the
    `ChunkRun` rows the lanes now write. Three states: closed, open after `OPEN_AFTER`
    consecutive non-answers, half-open once the cooldown has elapsed, which admits exactly one
    probe. Nothing is stored, for the reason `tools/scorecard.py` gives for deriving its scores:
    a second copy of the truth drifts from the first.

    Three constants carry the whole design and each one is there because of how a breaker fails.

      * `COOLDOWN_MAX_MIN` **is the most important line in the file.** An unbounded backoff is a
        permanent deletion wearing the clothes of a retry policy -- at the eleventh doubling the
        next probe is a month out. Twelve hours means every source is probed at least twice a
        day however long it has been dark, so this can only ever delay a fetch.
      * `partial` counts as an answer. "Some of the assets came back" is the ordinary state of a
        chunked lane against a venue that rate limits, and a breaker is the wrong instrument for
        degraded.
      * `skipped` is a fifth `ChunkRun` status and the breaker reads straight through it.
        **Filing a skip as `empty` would let the breaker read its own footprint as evidence**:
        the cooldown would double on every run, reach the ceiling, and keep its own streak alive
        forever on rows nothing had actually asked for. The table would then report a source
        failing continuously for months without a single request having been made.

    And it never raises. An unreadable history is treated exactly like an empty one -- closed,
    fetch as usual -- because a resilience layer that can take the lane down has made things
    worse than the problem it was added for. Demonstrated rather than argued: with the database
    refusing every connection, the lane still decides, logs the failure to write the log, and
    carries on.

    **What it refuses to do, and this is the line.** Nothing is substituted for data that did not
    arrive. No last close carried forward as though it were today's, no interpolation across a
    gap, no approximation of a missing venue from a correlated one. A synthesised close is the
    most dangerous invention available here: it is indistinguishable from a real one downstream,
    it passes every staleness gate *precisely because* it is freshly dated, and the rule table
    would then read it as evidence. A source that did not answer reaches the reader as a source
    that did not answer -- `SourceSilent`, `Coverage` and gate 3. The breaker only stops the
    pointless asking in between.

57. **A hit rate now carries an interval, and the interval is taken over the names rather than
    the rows.**
    `tools/scorecard.py` has said in its own docstring since it was written that "197 scored rows
    is closer to 60 names observed repeatedly than to 197 experiments", and then printed the rate
    over 197. The caveat was in the prose and not in the arithmetic.

    It is in the arithmetic now. `effective_n` takes the smaller of rows and distinct names,
    `wilson` puts a 95% interval around the share, and `spans_chance` says in words when that
    interval contains a coin flip. An interval over 197 is about a third narrower than one over
    60, which is exactly how a run of luck on one name comes to read as evidence about the
    engine.

    Wilson rather than the textbook normal approximation, because that approximation fails where
    this scorer lives: at small n and at shares near 0 or 1 it produces intervals running past
    100%, and an accuracy report claiming a hit rate "between 82% and 104%" has discredited
    itself in the one place it was trying to be careful. It is a frequentist interval and not a
    posterior, and calling it Bayesian would buy a word and nothing else.

    Taking the distinct-name count is conservative rather than exact -- the true effective sample
    is somewhere between the two and depends on how correlated a name's own sessions are, which
    nothing here measures. Erring small errs towards refusing to publish, which is the right
    direction for a figure whose entire purpose is to say whether these readings can be believed.

58. **A failed lane is retried once, and the word `once` is the whole of the design.**
    `.github/workflows/retry.yml` re-runs a failed data lane's failed jobs on `workflow_run`.
    Most of what kills a run here is transient -- a provider 429, a pooler dropping an idle
    connection, a runner losing DNS -- and until now nothing re-ran it, so a lane that failed at
    22:10 was simply absent for twenty-four hours over a fault that lasted a minute.

    `run_attempt == 1` is the guard. Without it a genuinely broken lane re-triggers the retry on
    every failure in a loop bounded by nothing but the free tier's Actions minutes, and **that is
    not hypothetical: on 2026-10-09 the database began refusing every connection for exceeding
    its quota**, and a retry loop against a quota-exhausted service is the fastest way to turn
    one dead dependency into two. A second consecutive failure is information -- it says the
    fault is not transient -- and a retry loop destroys that information by making every failure
    look alike.

    `schema.yml` and `tests.yml` are deliberately not watched. A half-applied migration is the
    one thing here a machine must not retry: `prisma migrate deploy` takes an advisory lock and
    can leave a migration recorded as started, which a blind re-run turns into a second partial
    apply. And re-running a failing test is how a flaky suite gets to stay flaky.

59. **Two guards were asserted against their own documentation, and both passed while the thing
    they guarded was deleted.**
    Worth its own rule because it is a category of mistake rather than one bug, and this file now
    has a lot of tests that read source text. A test that greps a whole file for a token finds it
    in the comment that explains the token. Deleting `run_attempt == 1` from `retry.yml` left its
    test green on the prose above it; asserting that a wrapper contains no `except` failed on a
    docstring that used the word "exception".

    The rule that falls out: **a source-text assertion must be scoped to the construct, never to
    the file.** Split out the `if:` expression, the function body past its docstring, the
    `ON CONFLICT` clause -- then assert. Where the behaviour can be exercised instead, exercise
    it: two of these became tests that build a stub cursor and check what actually happens, which
    is both shorter and incapable of this failure. Found by mutation testing the new guards, which
    is the only reason either was noticed.

60. **The database is one table, and the saving that was available cost nothing because the key
    nobody read was a third of it.**
    The old Neon project began refusing every connection on 2026-10-09 -- "your account or
    project has exceeded the quota" -- and no code change clears that. A fresh project was made
    and the 23 migrations applied to it, which is also the first time
    `20261009180000_entry_trigger` has run against a real Postgres.

    The rebuild gave the measurement nobody had. After the Yahoo backfill alone, with crypto,
    PSX, news, analogs, setups, factors and decisions **all still empty**:

        PriceSnapshot                          200 MB   550,968 rows, 2019-01-01 to 2026-10-08
          heap                                  91 MB
          PriceSnapshot_assetId_date_key        64 MB   unique (assetId, date)
          PriceSnapshot_pkey                    39 MB   btree (id)
          PriceSnapshot_date_idx                 5 MB
        everything else                        < 1 MB
        -------------------------------------------------
        database                               210 MB   of a 500 MB tier

    **The indexes were larger than the data.** And `id` was a 37-byte text UUID that nothing in
    the repository has ever read: no query selects it, no join uses it, no foreign key points at
    it, and neither write path names it -- `insert_snapshots` lists nine columns in both its COPY
    and its upsert and lets the default produce the tenth. About 20 MB of heap and the whole of a
    39 MB index, on the largest table in the budget, for a surrogate key on a table whose real
    identity is `(assetId, date)`.

    It is now the primary key. `ADD CONSTRAINT ... PRIMARY KEY USING INDEX` promotes the existing
    unique index in place, so nothing was rebuilt and there was no peak to pay for. Measured
    after: **PriceSnapshot 200 MB to 161 MB, the database 210 MB to 171 MB**, 550,968 rows
    unchanged and every close, volume, cap and OHLC value exactly as it was. The remaining ~20 MB
    of heap comes back on the next rewrite, because Postgres marks a dropped column dead rather
    than rewriting a table under a migration.

    **What was NOT done, and this is the part worth keeping.** The obvious way to bound this
    table is to prune old bars, and it is the one thing that cannot be done here without paying
    in decision quality. `jobs/analogs.py` reads **every stored close** -- its comment says so --
    because matching today against the past is what the whole analog leg is. A shorter history
    shrinks `analogs.count`, moves `medianPct`, and changes which names clear
    `ANALOGS_CONFIRM_MIN`. So the history stays, and `PriceSnapshot` stays in `NEVER_PRUNED`
    beside `DecisionLog`.

    Which leaves the honest position: **the two tables that drive the storage are exactly the two
    nothing may prune.** Dropping an unread key is the version of that saving which costs
    nothing. Beyond it, the levers are a shorter backfill window or a larger tier, and both are
    the owner's call rather than a thing to decide inside a job.

61. **An UPDATE that changes nothing is not free, and a lane that reruns rewrites a table to
    store what it already holds.**
    `AssetFactor` and `DecisionLog` are both keyed `(assetId, periodEnd)` and both upsert, so
    neither has ever been able to hold a duplicate row. That made the question look answered. It
    was not: Postgres implements an UPDATE as a new row version plus a dead old one plus the WAL
    for both, so a second run of a 477-name lane in one session doubles that table's dead tuples
    to store exactly what was there. On a weekend -- when `session_end` returns the same stored
    close and every factor is identical by construction -- the whole table is rewritten for
    nothing.

    Both conflict clauses now carry
    `WHERE (the written columns) IS DISTINCT FROM (EXCLUDED...)`, so an unchanged row is not
    written at all. Verified against the live database by watching `xmin`, which is the row
    version: identical write leaves it untouched, a changed value moves it, a number becoming
    null moves it, and null staying null leaves it.

    Three details decide whether this is safe, and each would be silent if wrong.

      * **`IS DISTINCT FROM`, never `<>`.** Half these columns are legitimately null -- no entry
        band, no target, no dated event, no volume on any currency pair -- and `<>` against null
        is null rather than true. A row going from null to a number would compare as unchanged
        and never be stored, which is the bug that loses data while looking like an optimisation.
      * **Every column the SET writes is in the comparison.** One named in the first and
        forgotten in the second makes a genuinely changed row vanish: no error, no row, and a log
        quietly holding yesterday's verdict under today's date. `decide.mjs` derives its list
        from the same `CORE_COLUMNS`/`SIZING_COLUMNS` the INSERT is built from rather than
        retyping it, and a test asserts the factor job's two lists match.
      * **`computedAt` is set and never compared.** It is `now()` and would differ every run,
        defeating the clause outright. The consequence is a change of meaning and it is the right
        one: that column now says when the reading last *changed*, and "the job ran" is a
        question `ChunkRun` answers properly now that the lanes write it.

    On `DecisionLog` the skip is safe for a reason that is structural rather than careful: the
    measured columns and `status` are absent from the SET -- rule 58 -- and the comparison is
    built from the same list, so they cannot appear in the WHERE either. The worst a wrong
    comparison could do on that table is write when it need not, which costs space. It cannot
    reach a maturation.

62. **The query ratchet watched `jobs/` and not `tools/`, which is where the per-row query was.**
    `tools/scorecard.py` carried the comment "One query for the whole set" above a loop issuing
    one query per scored row, and survived the session that rewrote eleven jobs for exactly that
    fault -- because the scan that would have caught it globbed one directory. The cost there is
    the worst shape available: it grows with the length of the decision log rather than with the
    size of the universe, so the report gets slower every day it is kept.

    The scan now covers both directories, and `tools/` is recorded at what it actually does
    rather than rewritten on sight: these are one-off reports run by hand, where a per-row read
    costs a person waiting rather than a nightly budget. `scorecard.py` is the exception and is
    at 0, because it is the one that runs over a table that grows.

    The general form, and it is the reason this is a rule: **a directory excluded from a ratchet
    is a directory where the thing the ratchet prevents is free to happen.** Nothing announces
    that exclusion -- the guard is green, and it is green about a subset nobody wrote down.

63. **The site's hottest query read the whole price history on every page render, and the fix was
    not an index.**
    `getDecisionRows` found the newest close per asset with
    `groupBy({ by: ["assetId"], _max: { date: true } })`, under a comment stating it "reads an
    index and returns one small row per asset instead of the table". Measured against 628,675
    stored closes on 2026-10-10, that is false: Postgres has no loose index scan for
    `GROUP BY assetId, max(date)` and plans a **parallel sequential scan of the entire table** --
    13,061 shared buffers, about 102 MB of buffer traffic, 209 ms -- and it is one of fourteen
    queries on every render of every list page.

    That matters more than latency, and it is the likeliest explanation for a quota nobody could
    account for from storage alone. Neon meters compute by active time: a page that reads the
    whole price history keeps the endpoint busy on every request, and the old project's storage
    was 339 MB of 500 MB when it began refusing connections -- near the ceiling but not at it.

    **An index was built and measured before anything was rewritten, and it did nothing.**
    `(assetId, date DESC)` cost 41 MB and the planner still chose the sequential scan: same
    buffers, same time. It was dropped. That is the whole argument against the instinct to answer
    "eliminate full-table scans" by adding indexes to the columns in the request -- `createdAt`
    is filtered by no SQL anywhere in this repository, and an index on it would have been 100%
    cost.

    The shape was the problem. A lateral probe walks the primary key backwards once per asset --
    477 index lookups instead of a 628,675-row scan -- and returns the close and the source at
    the same time, so the second price read is gone rather than merely cheaper:

        groupBy + findMany       13,061 buffers    209 ms
        one lateral               1,921 buffers    3.2 ms

    Verified to return the identical row for all 477 assets. The other five `groupBy` calls in
    the same function are left exactly as they were: they read tables `jobs/retention.py` caps at
    7 to 14 days, so each is a few thousand rows, and rewriting them would be churn bought with
    the same reasoning that was just measured wrong.

64. **A blanket rule was narrowed to the property it was actually protecting, and the narrowing
    is mechanical rather than a judgement.**
    Two tests forbade `$queryRaw` anywhere in the web layer, and their own comments say what for:
    "dynamic route params reach the database through Prisma, which parameterises", and "a single
    $queryRawUnsafe here is the only way a path segment could reach the database as code". The
    property is that **no value may reach the database as SQL**. The rule was the much broader
    "no raw SQL at all", which is a fine rule precisely because it needs no judgement.

    Rule 63 needed a lateral join, which Prisma cannot express. So the rule now bans
    `$queryRawUnsafe`, `$executeRawUnsafe` and `$executeRaw` outright and unconditionally -- they
    concatenate, and nothing in the web layer may write at all -- and permits `$queryRaw` only
    when its template literal contains no `${`. A constant string cannot carry a path segment.

    **The narrowing is only acceptable because the check is mechanical.** An interpolated
    `$queryRaw` now fails the guard exactly as `$queryRawUnsafe` does, so nothing rests on a
    reviewer noticing an interpolation. Both mutations were tested against the new guard and both
    are caught. A rule relaxed into "unless it looks safe" would have been a worse trade at any
    speedup.

65. **47% of the printed directions carried a stop that price had already passed, and the cause was
    the geometry and not any one rule.**
    Measured 2026-10-10 over the 404 live LONG and SHORT decisions: **189 had their stop on the wrong
    side of the current close** -- a LONG whose stop sat at or above price, a SHORT whose stop sat at
    or below it. AMAT read SHORT at 509.57 with a stop at 433.65. A stop is the level at which the
    reason for the trade stops being true, so these were plans whose own invalidation had already
    fired, printed as actions.

    The cause is in `jobs/setup.py`: the entry is the **20-session window extreme** and the stop is
    1.5 of the asset's daily moves from *that*, which is the geometry every backtest behind it
    assumed ("entry at the window extreme with price already there"). A name in a pullback is nowhere
    near its window extreme, so a stop measured from the extreme lands on the wrong side of the price
    it is actually at. `jobs/horizons.py` anchors the target and the reward-to-risk to the same entry,
    so all four numbers are consistent with each other and wrong against the price.

    **It refuses and does not repair.** `stopCrossed` in `lib/decision.ts` is checked first inside the
    direction builder, so all three routes to a direction (a stated state, a withheld trend, a bias)
    pass through it, and a crossed plan becomes `stop-crossed` with its reason. Re-anchoring the plan
    to the close would have changed the entry, stop, target and reward-to-risk of 189 names at once on
    a geometry the stored backtests only partly cover; refusing removes only what was never valid.
    Equality counts as crossed: a stop at the close has no distance to be wrong across.

    Directions went from 404 to 215. **`tools/rederive.py`, which recomputes every verdict from raw
    closes without the rule table, went from 300 contradictions to 1.** I had told the owner those 300
    were the engine breaking the "close above both averages" contract. That was wrong: they were
    almost entirely this. The one left (AGTL, close 0.1% above its 20-day) is a borderline.

    **What the refused signals were, measured.** Median stack age 0 and a median move already made of
    +1.1%: not late trends in a pullback but signals whose trend condition **no longer holds today**.
    The gate removes broken signals, not late ones. Of the 215 kept, median stack age is 7 sessions,
    17% are older than 20, and the 20 backed by an entry trigger have a median age of 2 (n is small).
    `tools/research/signal_timing.py` reproduces it.

    Because every refusal is logged with the side it refused (rule 66), whether a crossed stop predicts
    anything is now a question the loop can answer.

    **The printed reward:risk is a lower bound.** With the stop below the close and the close at or
    under the entry (a LONG; mirrored for a SHORT), the ratio from today's price is at least the
    printed one, which is measured from the entry. It understates and never flatters.

66. **The log could not learn, because it recorded the grade and not what earned it.**
    `DecisionLog` held `confidence` and `gate` and not **which confirmation legs backed each call**, so
    nothing could ever be learned about whether a leg earns its place -- the entry trigger was added
    with no way to tell afterwards whether the names it backed did any better. And a refusal did not
    record the side it refused, so it could not be scored, though "this was not worth doing" is a claim
    and principle 7 says every claim is checked.

    Two nullable columns, `legs` and `intent`, written at decision time because they cannot be
    reconstructed: the rows they are computed from are rewritten every night. `confirmationCount` is
    now the length of `confirmingLegs`, so the grade, the short gate and the log are one computation.
    NULL and the empty string are different findings and are kept apart: "no legs backed it" is a
    finding, "this row predates the column" is not.

    **What was asked and deliberately not built: automatic re-weighting.** The directive wanted
    successful predictions to reinforce and failures to penalise decision weights. There are no
    weights: the grade counts independent confirmations. The thresholds the table does carry were each
    argued from backtests of 100,000 to 220,000 observations; a live log is hundreds of rows that are
    repeated observations of a few hundred names, a far smaller and far more correlated sample.
    Letting it move those numbers automatically trades a large measurement for a small, correlated one
    on a loop that rewards whatever happened last month. That is noise-chasing with a feedback path,
    and it is the opposite of principle 8.

    What `tools/scorecard.py` does instead: per leg, the outcomes of names it backed against names it
    did not, with a Wilson interval over the **distinct names**, and the verdict "not separable" until
    both arms hold 30 effective names and the intervals stop overlapping. It never says to apply a
    change; a change to the rule table is a proposal with evidence, reviewed by a person. Refusals are
    scored on the sign of the move alone, because for a plan whose stop was already crossed "stopped
    out" is true by construction.

    **State of the loop, honestly.** The log holds one session. Nothing has matured, so nothing has
    been learned, and the earlier history (the matured rows from 2026-10-01 to 10-09) is in the old
    Neon project, which is still over quota. `jobs/mirror.py` (rule 69) is the path for bringing it
    across, translating asset ids by (industry, symbol), when that project's quota resets.

67. **No market page had a single column header, and at desktop width the per-row labels were hidden
    because a header was assumed to be carrying them.**
    `SectorBoard`, which every market page uses, rendered `DecisionRows` with no `DecisionHeader`; only
    the older `DecisionList` rendered it. Measured in the live DOM at 1280px: no header word anywhere
    in the sector block, and the per-row labels `display: none`, so a reader saw eight unlabelled
    values per row. Worse than a missing header, because it looked complete.

    The header is now inside each sector's scroll container and pinned (`sticky top-0`, opaque ground),
    verified to hold at the scroller's top after scrolling 400px. The row labels are `lg:sr-only` and
    not `lg:hidden`: gone visually where the header carries them, still in the accessibility tree --
    the header is `aria-hidden`, so `lg:hidden` left a screen reader with no names for any value.

    Two columns were added: **Reward:risk**, from the same target the Take-profit column prints, and
    **Confirmations**, "n of 5" with the legs by name ("volume, peers"). A WAIT prints "not
    applicable" and not "0 of 5", which would read as a call nothing supports.

    Found only by looking: "Reward : risk" wrapped onto two lines at 1280px (`1.4 :` over `1`). The DOM
    probes said the header existed; the screenshot said it was unreadable. Verified after the fix at
    1280 and 1024 (table, header pinned), 768 and 375 (labelled cards, header hidden), and on the PSX
    page -- the stress case, 621 rupee cells, none clipped. No horizontal overflow at any width.

68. **The exchange lists 1,057 symbols and the project follows 157; the unfollowed ones mostly are not
    stocks.**
    "Add everything listed" would have put government securities (`P03GHS151026`, Rs 2.2 trillion of
    face value in a day) and monthly futures (`PRL-OCT`, `OGDC-OCTB`) into a rule table that reads a
    20/50-day stack. The crypto ranking has the same shape: stablecoins, wrapped and staked copies,
    gold-backed tokens. So the question is never "what is listed" but "what is an independent reading".

    `tools/universe.py` is read-only and proposes by stated criteria, and prints why it refused each
    of the others. The universe lives in `jobs/seed.py` as reviewed rows, not in the database.
    **Crypto, 30 added** (36 to 66), from the top 150: refused 29 wrapped/staked/bridged, 16 stable,
    3 pegs, 38 with no Coinbase pair, 1 too thin. **Coinbase is required and Binance is not enough**:
    Binance stopped answering from GitHub's runners on 2026-09-29, so a coin only it carries is stored
    from a laptop and never updated in production. The visible casualty is Toncoin, rank 36, listed as
    `GRAM` on CoinPaprika and reachable only through Binance. Its bridged namesake `TONToken` trades
    $0.1m a day against Toncoin's $42.8m and was refused as too thin.

    **PSX, 69 added** (157 to 226): ordinary shares that traded on at least 70% of the last 60 sessions
    with a median value over Rs 1m, in a sector the project already files. Refused: 570 contracts and
    securities, 157 illiquid, 101 in a sector the project has no industry for. Placement uses the
    exchange's own sector code, mapped through the names already filed by hand and **only where they
    agree** -- a code two of our industries share places nothing. One collision was caught by a test
    rather than noticed: the exchange's own ticker `PSX` is also Phillips 66, and the asset page is
    looked up by symbol alone.

    A ticker is not an identity (`GRAM` and `TON` were both live), so every crypto candidate's venue
    price is checked against CoinPaprika's within 15%. And `jobs/psx.py full` was never run on the
    rebuilt database, so every existing PSX name had ~85 closes against the 220 a longer-horizon read
    needs; after the backfill 217 of 226 clear it.

69. **A standby is a copy plus a connection that switches, and the dangerous parts are the ones that
    look easy.**
    Two Neon projects do not replicate, so the work is in two halves, each with a way to do harm.

    **The copy (`jobs/mirror.py`).** Every asset id is a random UUID assigned when the seed ran, so two
    projects seeded separately hold *different ids for the same stock*. A plain row copy of
    `DecisionLog` would violate the foreign key or, if an id happened to exist, file one name's
    decisions under another. It translates through `(industry slug, symbol)` and skips what has no
    counterpart. It is one-way, additive, **never deletes from the target** (a mirror that propagates
    deletions turns one bad run against an emptied source into an emptied backup), refuses to copy a
    database onto itself (the pooler host and its direct twin compare equal), and copies by
    `IS DISTINCT FROM` so a rerun writes nothing. It covers `DecisionLog`, `PriceSnapshot`,
    `SignalLog`, `AssetThesis`; everything else is derived and cheaper to recompute than to copy.

    Verified against a throwaway schema whose asset ids shared none with the source: all 477 decision
    rows filed under the same stock (symbol, industry, action and gate agreeing), a rerun writing 0, a
    maturation carried to the right stock, a deleted source row surviving in the copy, an unmatched
    asset counted and skipped. **That test deleted a row from the live `DecisionLog`** to prove the
    last-but-one property. It should have run against a copy; the nightly writer regenerated it.

    **The switch (`lib/failover.ts`).** A `pg.Pool` that tries the primary and, only while *establishing
    a connection* and only on a connection-class failure (unreachable, or Neon's quota arriving as
    Postgres class 53), hands out a standby connection. It is not mid-transaction, not for writes (the
    lanes never import it, and a test says so), and not triggered by a bad password: an absorbed
    credential fault would run broken in production for as long as the standby held out. The primary
    is left alone for 60 seconds after a failure, so a down primary costs one slow request and not
    every request, and is retried afterwards, so it is never a permanent switch.

    Proven on a real outage, because the old project is genuinely over quota: primary pointed at it,
    standby at the new project. Control with no standby: HTTP 500. With the standby: HTTP 200 and real
    data, first request 6.8s and the next two 1.75s, one log line, no credentials in it.

    **Off in production.** `DATABASE_URL_FALLBACK` is unset, because there is no second project to hold
    a mirror: the old one is quota-blocked and nothing here can create a Neon project. To turn it on:
    create or revive a project, run `prisma migrate deploy` and `jobs/seed.py` against it, run
    `jobs/mirror.py`, schedule it nightly with `--since` a month back for `DecisionLog` (maturations
    land up to 20 sessions later), and set the variable in Vercel. Pages print the date their figures
    are as of, which is the only thing between "serving the standby" and "serving stale numbers as
    current" -- and why every switch is logged.

    **"Without quota limitations" is not achievable, and the directive's phrase should not be
    believed of any design.** Two free projects each have their own cap. The quota was beaten by
    spending less -- rules 60, 61 and 63 -- and a standby is for surviving the next outage, not for
    having no limit.

70. **Whether a signal is predictive cannot be guaranteed, and the engine says so; what can be done is
    to measure how late it is.**
    The directive asked for a guarantee that Long and Short signals are forward-looking and not
    lagging descriptions of price that has already moved. No rule built from stored prices can offer
    one, and this project's first principle says the same: the site reports a trend, never a
    forecast. Claiming otherwise on the page would be exactly the false confidence the rest of the
    system is built to avoid.

    By construction, four of the five legs read a state or a past window: the two trend states and
    their agreement (moving-average stacks), peer-relative strength (a 20-session return gap), and
    volume (same-session activity). Only two bear on the future at all: the analog set, which measures
    what *followed* similar days, and the entry trigger, which is an event on the latest bar rather
    than a standing state. Rule 51 measured the engine entering a median of 40 sessions into a long.

    What was done is rule 65's measurement: median stack age 7 sessions, 17% older than 20, and
    trigger-backed signals at a median age of 2. The only valid test of "predictive" is out-of-sample
    outcomes at +1, +5 and +20 sessions, and that is the loop in rule 66. It starts producing them on
    2026-10-12 for the +1 window and has nothing to say before then.

71. **The standby became a cascade of three, and the test that proved it was wrong twice before it was
    right.**
    The failover now takes an ordered list: the primary, the second Neon project, then Supabase. The
    rule 69 pool tried two endpoints; `Failover` in `lib/failover.ts` tries N, strictly in priority
    order, and a later tier is never touched while an earlier one works.

    **What was given and what was needed.** The URL and `sb_publishable_` key are for Supabase's REST
    API and cannot run a Prisma migration or accept the mirror's inserts; a Postgres connection needs
    the database password. The direct host (`db.<ref>.supabase.co`) does not resolve at all -- it is
    IPv6-only on the free tier, which neither a Windows machine on IPv4 nor GitHub's runners reach --
    so the **Session pooler** is the only usable address, and its region (ap-northeast-2) was found
    by probing, because a wrong region answers "Tenant or user not found" rather than refusing the
    login. The password was pasted into a chat and should be rotated.

    **Schema parity was compared, not inferred.** "Both ran the same migrations" is a claim about a
    table of names. `tools/schema_parity.py` compares every column's type, nullability and default and
    every index and constraint by definition: 37 tables, 515 columns, 123 indexes, 78 constraints,
    identical. It excludes `NOT NULL` as a named constraint, which PostgreSQL 18 (Neon) records and 17
    (Supabase) does not -- that would have reported the server version and not the schema.

    **TLS, measured against the real pooler with the Node driver.** With no mode the driver connects
    **unencrypted**. `sslmode=require` fails ("self-signed certificate in certificate chain"), because
    node-pg reads `require` as full verification and Supabase's CA is not in Node's store.
    `uselibpqcompat=true&sslmode=require` connects encrypted. Python's driver rejects that parameter,
    so one URL cannot serve both and `withEncryption` adds it Node-side, only when the URL names no
    mode. It is libpq's `require`: encrypted, chain not verified.

    **Design, and what each rule is for.** Per-tier cooldown, or one dead tier freezes the others.
    Every tier down at once is still retried, or a recovery waits out the window. A standby that
    answers but holds no data is refused (`SELECT 1 FROM "PriceSnapshot" LIMIT 1`), because "0 names"
    served as the site is worse than an error; a merely old standby is left to the rule table, whose
    stale-close gate and printed as-of dates make an old copy honest. The primary's bad credential is
    raised; a *standby's* is logged loudly and skipped, never at the cost of the request. And every
    pool now has a **connect timeout**: `pg.Pool` defaults to none, so a black-holed primary would
    have hung the request forever instead of failing over, which is the opposite of "instantly".

    **A capacity bug the cascade test found by accident.** Supabase's free session pooler admits 15
    clients *in total*. Three test servers (5 pooled connections each) and the running mirror
    exhausted it, and the code mishandled that twice: the error arrives as `XX000`
    "(EMAXCONNSESSION) max clients reached", not class 53, so a full standby was classified as a
    configuration fault and the request failed; and a ceiling of 5 per process is far too greedy,
    because in production every concurrent serverless instance has its own pool. `STANDBY_MAX_CLIENTS`
    is 3 and capacity exhaustion is a connection failure.

    **The test setup misled me twice, and both are worth keeping.** The "control" servers returned 200
    with the primary over quota, which is impossible, for two reasons: they shared one `.next`
    directory, so one server's render went into the ISR cache and the rest served it from disk; and
    **`.env` is loaded underneath the shell**, so a variable I had only set for one server (the new
    `SUPABASE_DATABASE_URL`) was silently present in all of them -- the control was a cascade. Then the
    status code lied in both directions: Next sends 200 before a mid-render error and puts the error in
    the body, and my own "real page" check matched the coin's name inside the URL echoed in an error
    payload. The valid version sets every variable explicitly (empty for "none"), uses a different
    never-rendered page per scenario, and judges by body size and content: 12 KB of error shell against
    112 KB of real page.

    **Proven result.** Primary pointed at the genuinely quota-blocked old Neon project, the second
    standby at a refusing address, Supabase as the only tier left: three different asset pages, all
    HTTP 200 with real content, zero server errors, and a log naming each tier once. The Supabase
    price for DOT is identical to Neon's.

    **The mirror takes several targets.** Each is its own unit of failure, because with three databases
    the one most likely to be down is the one being copied to, and a run that stopped at the first dead
    target would leave every later one stale. Exit 0 only if all completed. Every printed error passes
    through `redact`; psycopg's "invalid connection option" echoes the whole string, and a CI log is
    readable by anyone with repository access. The first test of that used addresses that cannot
    resolve, whose errors never contain a URL, so it could not have failed -- found only by removing
    the redaction and watching nothing go red. `cron-mirror.yml` runs nightly after the decision lane,
    skips cleanly with no standby configured, and uses a 7-day window for prices and 40 days for
    decisions, because a `DecisionLog` row is updated for a month as its outcomes land.

    **What was claimed and is not true.** The directive says this expands total capacity to 1.5 GB. It
    does not: a mirror copies the *same* data, so the volume the site can serve from is still one
    project's 500 MB. Three projects buy survivability and nothing else. And a free Supabase project
    has been documented to pause after a week without activity, so the nightly mirror is also what
    keeps the standby awake.

    The directive asked for the tests in `lib/failover.test.ts`. They are in `tests/failover.test.ts`:
    `npm run test:web` globs `tests/*.test.ts`, so a file in `lib/` would never be run.

    **Verifying a copy is itself a trap.** The first comparison said the two databases differed, twice,
    and neither was real. `sum(volume)` over 783,000 doubles differed by 1,300 in 4.5e16: floating-point
    summation order. And an exact text hash of every row differed because the two servers *print* a
    float differently -- `50.900001525878906` against `50.9000015258789` -- since Supabase runs with
    `extra_float_digits = 0`, which truncates text output to 15 digits while storing the same double.
    Comparing the renderings compared the servers' settings, not the data. With
    `SET extra_float_digits = 3` on both sessions, an order-independent hash (`ORDER BY symbol COLLATE
    "C"`, because the two servers also collate differently) is identical for every price, decision and
    thesis row. A copy is verified by exact, order-independent content, never by an aggregate of floats.

72. **A language model was given the power to say no, and nothing else.**
    `lib/macroGate.ts`, `tools/macro_gate.mjs`, the `MacroGate` table and the `macro-veto` gate in
    `lib/decision.ts`. A nightly job shows a model one LONG or SHORT the rule table already produced,
    with the last day's headlines and each source's stored Beta(alpha, beta), and asks whether they
    describe an extreme macro shock. The answer is stored. The rule table reads a fresh stored REJECT as
    one more input to `decide` and turns that name into a WAIT. That is all it can do.

    **Why it is a stored input and not a call.** The site computes every verdict at read time, so a
    nightly job that only wrote a log row would change nothing a reader sees. And a model is not
    deterministic: the prompt asked for "deterministic" output, which no model can promise. Storing the
    answer is how `decide` stays a pure function of what is stored and a page refresh can never show a
    different verdict. The determinism lives in the rule table; the model's contribution is one stored
    row that is honest about being one.

    **What it cannot do, and where that is enforced -- not asked for.** Telling a model "never invent a
    number" is a request. Here the reply schema has four fields and none is a number, the parser
    (`parseGateReply`) rejects a reply with any extra key, a fence, a preamble, the wrong symbol, a
    REJECT with no reason, or an EXECUTE with one, and the rule table prints fixed words per reason and
    never the model's rationale (stored for the log only). The asymmetry rule 44 gives coverage -- it can
    withdraw a claim and never make one -- holds here for the same reason.

    **It fails open, in three places.** An unusable reply, a refusal by the model, a timeout or an API
    error resolve to EXECUTE and are stored as `valid = false` so they are visible and retried. A read
    of `MacroGate` that throws (a standby the migration has not reached, a dropped connection) is "no
    veto" in both the site query and the decision job. And the job exits 0 whatever happens and the
    workflow steps are `continue-on-error`: the one thing this layer must not do is turn a third party's
    outage into a red decision lane or a blank site.

    **Headlines are an attack surface.** A feed anyone can publish to is text copied into a prompt.
    Control characters are removed (an earlier draft of this layer's prompt contained a literal vertical
    tab from a stray escape), both angle brackets are neutralised so a headline cannot close its own
    block, the system prompt says the contents of those blocks are data and never instruction, and a
    symbol is refused rather than cleaned if it is not an identifier. One mutation check slipped: with
    only the `>` neutralised the test still passed, because the closing tag was destroyed anyway; the
    test now asserts that no angle bracket survives outside the template's own tags.

    **Two things found by running it, not by reading it.** `pg` returns a `@db.Date` as local midnight,
    so east of UTC the seam read 2026-10-09 as 2026-10-08 and a veto filed yesterday looked two days old:
    six inserted refusals changed nothing in the decision job until the job passed `dayOf(...)`. Every
    pure test had passed. And the SDK's zod helper, at the pinned zod, rendered the two enums as
    description text rather than `enum` constraints, so the schema is written out by hand and the zod
    dependency is gone.

    **Verified against the live database, with no model.** Six temporary REJECT rows produced exactly six
    `macro-veto` rows in the decision job's dry run (LONG and SHORT fell by four and two), and removing
    them restored 280 WAIT / 189 SHORT / 107 LONG. Neon and Supabase carry the table with identical
    structure (38 tables, 527 columns, 126 indexes, 80 constraints). **No call to the real API has been
    made**: there is no key here, so the request shape was checked against the SDK with a fake transport
    and the first real answer will arrive when the secret is set.

    **What was claimed and was not delivered.** "Deterministic grounded reasoning" and "the gate
    guarantees zero invented numbers" are properties of the surrounding code, not of the model, and are
    described that way above. The user's source-reliability weighting is given to the model as data
    (Beta statistics and the implied mean per source); whether the model uses it well is not something a
    test here can say, and the scorecard should be asked after the first sessions, like every other claim
    (principle 7): what the refused names did next against the ones let through. Every answer, EXECUTE
    and fallback included, is stored for that reason. Cost: only names with a direction and a headline in
    the last 24 hours are asked about, at most 60 a run, `MACRO_GATE_MODEL=claude-haiku-5-5` is the cheap
    switch.

    **The adversarial exam, and what it can and cannot show.** Twenty cases (`tests/macroGateCases.ts`):
    fake pumps and lookalike domains, genuine shocks, stale decoys, malformed replies, edge cases. Seven
    are decided by code and the offline suite asserts them exactly (`tests/macroGateAdversarial.test.ts`):
    a stale or empty feed is never asked about, and every malformed reply fails open and is recorded as
    unusable. The other thirteen are a *model's judgement* -- whether a 0.5/20 telegram channel is a
    pump -- which no test of code can answer. Offline, the suite proves only that the model is shown what
    it needs to judge (each source's alpha, beta and mean; the headline inside a data block; the levels as
    read-only context) and that a correct answer survives the pipeline; the scripted "model" there reads
    the answer key and is labelled as plumbing. `tools/macro_gate_exam.mjs` scores the real model, and
    **has not been run**: there is no API key here. Anyone quoting a pass rate for the judgement cases
    before it is run is inventing one.

    Where the gate is stricter than the exam's own comments, on purpose: TC-12's clean reply is rejected
    for its fence, and TC-13's reply is rejected whole where the exam says extra keys are "stripped or
    ignored". The expected verdict (EXECUTE) is the same, and a REJECT carrying an invented number cannot
    veto. Four of the exam's cases (TC-12 to TC-15) had no headline, so the gate would never have called
    the model and the mock output would never have been read; a benign headline was added so the parser is
    what is tested. Two expectations are labelling judgements and will be the first to disagree with a
    real model: TC-08 (an auditor resigning over fraud is called `sentiment-conflict`, though it could as
    fairly be `macro-warning`) and TC-20 (a vague "emergency regulatory statement" six hours old is
    expected to pass, which depends on how much a headline with no content is allowed to weigh).

73. **The gatekeeper that costs nothing, and the finding that it has nothing to read.**
    `lib/macroGateLocal.ts` decides the macro veto from a fixed word table and the stored Beta statistics,
    with no model, no network and no key. It is the job's default engine (`MACRO_GATE_ENGINE=local`);
    the model of rule 72 is opt-in by name. The reason it is the default is the reason the rule table is
    what it is: same input, same answer, forever, so it can be put through an exam in CI and nothing it
    does needs a bill or a secret.

    **Trust is judged before any word is read.** A source is believed on a shock only at a mean of 0.70
    *and* at least ten observations' worth of mass (alpha + beta), so a new source with one success
    cannot score 1.0; below 0.30 it is ignored whatever it says; in between, or unlisted, it can never
    veto alone. Hedged, denied, reversed or proposed news ("may", "denies", "lifted", "resumes") is never
    a trigger, because refusing on a rumour is the pump-and-dump this layer exists to resist. A systemic
    warning applies to a LONG and a SHORT alike; corporate bad news (audit resignation, fraud, federal
    enforcement) conflicts only with a LONG and only when the headline is attached to the asset itself --
    it supports a short and a sector headline is about other names. Crypto-only headlines bear on crypto
    only. This direction-awareness is a deliberate departure from the written spec, which refused on
    corporate bad news whichever way the trade pointed.

    **Scored.** 20 of 20 on the adversarial exam, and 17 tests in all, including shocks and decoys written
    afterwards in different words (an exam a table was tuned to pass proves little) and every trust
    boundary. Twelve mutations of the engine were run; three first slipped, and each was a real
    gap in the tests, not equivalent mutants (the macro-over-conflict ordering, a throw swallowed by the
    outer guard, a prefix of a trusted name accepted as that name). One test found a real defect in the
    design: capped at the model's eight headlines, a genuine shock buried under newer routine ones was
    invisible, so the local engine reads every headline in the window.

    **What it cannot do.** It reads words, not meaning. A shock phrased outside the table passes -- a
    miss, and the safe direction -- and the test pins three real ones that do, so the limit is on the
    record and not a surprise. A headline that uses the listed words for something else could refuse a
    name wrongly; every answer is stored, so the scorecard can say which, once outcomes mature.

    **The gate is inert on today's database, for two reasons found by reading the data and not the code.**
    The new database holds no `News` rows at all (the news lane's GitHub secret still names the old
    project), and `SourceReliability` is empty -- and even when the audit fills it, it holds *price-feed*
    reliability keyed by `h.source`, not the reliability of a news publisher. So no headline arrives and
    none could be trusted if it did. Both fail open, by design, and the job says so in its one line of
    output. Inventing a Beta(45, 1) for Reuters would make the gate fire, and would be exactly the
    invented number this project refuses.

    **Decided afterwards: a short declared list, labelled as a declaration.** `DECLARED_TRUSTED` in
    `lib/macroGateLocal.ts` names thirteen outlets (wire services, national financial papers, the main
    business daily of each market covered, one crypto specialist). A veto resting on one says
    "declared-trusted publisher" and quotes no credibility figure, because there is none. Names match
    exactly after normalisation, so a lookalike ("bloomberg-news-corp.co") earns nothing. Measured
    statistics outrank a declaration where they have evidence behind them: a mean under 0.30 over at
    least ten observations ignores a listed outlet, while three bad observations do not. Trust is keyed
    on the **publisher** -- Google News appends the outlet to the title, `News.source` is only the feed
    label -- and the suffix is stripped from the text the rules read, so an outlet called "Federal News
    Network" cannot satisfy a word in the table. The list is a judgement and not a measurement; the
    scorecard is where an entry should be removed if its vetoes prove wrong.

74. **"Real time" was asked for. The lag was not a cadence problem, and the floor is five minutes.**
    The directive described a site that lags and asked for one-minute micro-batches. Measured first:
    on 2026-10-10 at 01:16 UTC the newest US and crypto closes were 2026-10-08 -- two days old -- because
    no GitHub lane had written to the new database since it replaced the old one (the `DATABASE_URL`
    secret still names the over-quota project). The lanes' designed cadence (crypto every 2 h, US four
    times a day, PSX three) was never the problem; they were not running. Refreshed by hand the same
    night (crypto, all four US chunks, the derive lane and a new day of decisions: 576 rows for
    2026-10-10). The permanent fix is the secret, which only the owner can set.

    **What was built: a quote layer beside the closes, never instead of them.** `LiveQuote` holds one
    row per asset, upserted in place by `jobs/live.py`, so it stays the size of the universe -- a row per
    tick would be 576 x 288 a day, the growth that took the first database over its quota. A quote only
    moves forward (`WHERE "quotedAt" < EXCLUDED."quotedAt"`), so a closed market costs no writes and a
    late slice cannot put an old price over a newer one. Crypto comes from CoinPaprika in one request for
    every coin (0.7 s measured); US names, ETFs, futures and FX from Yahoo 1-minute bars, batched over a
    rotating slice of the active set (60 symbols in 12 to 16 s measured). Binance is not used: it stopped
    answering GitHub runners on 2026-09-29. PSX has no free quote endpoint and keeps its closes.
    `cron-live.yml` runs every five minutes through the US session and every fifteen around the clock for
    crypto, opt-in by the `LIVE_QUOTES` variable.

    **A quote is never an input to a decision.** A price for a session still trading is not a close (rule
    41), and a verdict that moved with the tape would change on every refresh. A test fences every file
    that decides (`lib/decision.ts`, the seam, both macro engines, `decide.mjs`, the factor, setup,
    horizon and analog jobs) against reading the table, and the list row still takes its `priceNow` from
    the close. The column headed "Current price" was printing a close that could be days old, which is
    the mismatch the directive described; it is now "Last close", with the last trade under it and the
    UTC time it was struck. A quote that only repeats the close is not printed.

    **Refreshing in the browser.** `/api/quote` is read-only: it answers the stored quote and, if that is
    more than five minutes old, asks the provider once (1.5 s timeout, the answer held a minute per symbol
    so a page of readers costs one request a minute), returning it marked `revalidated` without storing
    it -- a public endpoint must not be a way to put a price in the database. `components/LivePrice.tsx`
    is the third client component on the site, held to the error boundaries' rule (no server module, no
    environment) and to one more: it fetches exactly one same-origin URL, polls only while the tab is
    visible, and asks at once when a tab comes back. Checked in a real browser: a hidden tab made no
    request, and on becoming visible it fetched once and moved from "16 min ago, delayed" to "2 min ago".

    **What was asked for and is not true here.** A one-minute schedule: GitHub Actions will not run one
    more often than every five minutes. Under 500 ms per tick: no HTTP round trip to a free provider is
    that fast from a runner; the job prints what each stage took instead (crypto 0.7 s, a Yahoo slice
    12 to 16 s, the write 0.25 s). A WebSocket: a scheduled job cannot hold one open, and Vercel functions
    are request-scoped. Edge runtime: the quote is read through the same TCP Postgres client as every
    page, which does not run on Edge; the route stays within Edge-like bounds anyway. Redis: not in this
    stack, and not needed for 576 rows.

    **Placeholders.** "none stored", "not stored", "not applicable", "N/A" and "waiting" were each a cell
    saying it was empty and nothing about the name. A held-back row now prints the rule table's own reason
    in a "Why no call" cell instead of a Low badge and a dash; the Low badge is gone from every WAIT
    (asset panel, overview card, rows), because a grade grades a direction and a WAIT has none; an absent
    size is explained by what the asset is (`sizeAbsence`); an absent level says which. No number was
    invented to fill a cell and no grade was raised: directional rows keep the grade the rule table gave.
    A guard bans the strings from every page and component, the methodology prose exempt.

    **Found on the way.** The price lane keeps a futures bar out until the provider's 24-hour session
    window ends (Friday 04:00 to Saturday 03:59 UTC for `BZ=F` and `GC=F`), so commodity closes arrive a
    few hours after the real settle. That is the forming-bar guard doing its job, not a fault, and the
    quote layer now shows the last trade in the meantime. And `with_backoff` first compared a DataFrame
    with `[]`, an elementwise comparison that raised inside the retry and made every successful download a
    miss -- found by running the tick against the provider, not by any test of the pure code.

75. **"Self-healing" on a serverless site is a scheduled look and a restart, not an infinite loop.**
    The directive asked for an infinite heartbeat loop, one-minute ticks, a 3-minute stale rule, automatic
    recovery and no human in the loop, without loosening any rule. Sorted against what was already true:

    * **Already true, and pinned:** connection recovery (the read failover, rules 69 and 71: per-tier
      cooldown, a connect timeout, a dead tier skipped and retried); bounded retry and backoff in every
      fetch (`nbt.get`, the circuit breaker in `jobs/breaker.py`, `with_backoff` in `jobs/live.py`);
      bad rows skipped rather than fatal; `retry.yml` re-running a failed lane once; a binary macro gate
      with no pending state (rule 73); no paid dependency (the local engine is the default); and quotes
      never entering a decision (rule 74). None of it relaxes a threshold.
    * **Built:** `/api/health` reports how old every stored reading is and judges it with the rule
      table's own `STALE_AFTER_DAYS`, imported and never copied, so the health page and every decision
      cannot disagree about one close. `tools/watchdog.py` (`cron-watchdog.yml`, hourly) reads it and
      dispatches the lane each problem names. Its limits are the point: five lanes only, because the
      health document comes over the network and a lane name in it is a request, not an instruction;
      never on top of a running copy; once an hour per lane; and a lane that has failed twice in three
      hours is not restarted again but escalated, by turning the run red, which is GitHub's own failure
      email to the owner. A restart cannot fix a wrong secret, and pretending otherwise only adds red runs.
      `retry.yml` catches runs that failed; this catches the ones that never ran.
    * **Tightened:** a quote is stale after three minutes, not five. Between two five-minute ticks a viewed
      page asks the provider itself, at most once a minute per symbol. When the provider has nothing newer
      either, the market has stopped, and the page says "no newer trade" instead of calling a Friday close
      on a Saturday "delayed".
    * **Not possible here, said plainly:** an infinite loop (no process on this platform lives between
      requests); one-minute ticks (GitHub's floor is five); 500 ms per tick (no HTTP round trip to a free
      provider from a runner is that fast; the job prints what each stage took); WebSockets and the Edge
      runtime (rule 74). And "every asset must resolve to an active calculated state": a WAIT *is* a
      calculated state, the rule table's answer that a direction is not supported, and turning it into a
      LONG or SHORT to remove it would be the invented number this project exists to refuse.
    * **Zero human intervention is not available while the GitHub secret names the old database.** The
      watchdog will find every lane stale, restart them, watch them fail, and escalate. That is it
      working: the one fix it cannot make is the one only the owner can.

    Found while testing: rounding the news age to one decimal before comparing it with the six-hour limit
    turned 6 h 1 min into "6.0" and passed it; the comparison now uses the raw age. And the first guard
    against redefining the stale limits matched `DECISIONS_STALE_AFTER_DAYS` as a substring.

76. **The first full run on GitHub found four faults that every local run had hidden.** On 2026-10-10,
    with the secrets finally pointing at the new database, every lane was dispatched on GitHub in order
    and its log read. Each fault below was green or invisible locally:

    * **The `DATABASE_URL` secret held the Supabase string** (both lines of `.env` contain
      `DATABASE_URL=`). Every lane went green while writing to the standby the site does not read.
      `jobs/schemacheck.py`, which runs before every lane, now names the provider ("Neon", "Supabase";
      never the host, because a public repository's logs are public) and refuses the standby.
    * **The forming-bar guard held Friday's futures and FX bars all weekend.** Its allowance for "the
      minutes after the bell" had no bound on our clock, and futures and FX stop trading hours before
      Yahoo's nominal session end, so Brent, gold and EUR/USD read "still trading" until Sunday night.
      Now the marker counts only while the last trade is within two hours (`LANDING_WINDOW`).
    * **The news lane failed on its clean-up after storing 1,405 headlines.** Its final prune ran on a
      connection that had sat idle inside a read transaction for twelve minutes, and the server killed
      it. The read transaction is closed before the fetch, and the prune goes through the `Link`.
    * **The mirror copied `SignalLog.productId` untranslated** and broke Supabase's foreign key. It now
      goes through the product's slug, as assets go through (industry, symbol).

    Plus two that were configuration rather than code: a secret pasted with its trailing line break
    (whitespace is now stripped from every connection string, though no data job may even name a
    standby to do it), and the macro gate's 60-name cost cap applying to the free local engine, which
    left 99 of 159 names with fresh headlines unchecked on its first production run.

    **Verified afterwards, on production:** all ten workflows green on their latest run; 576 of 576
    names priced and decided for 2026-10-10 (every US stock, ETF and future at Friday's close); 289
    WAITs, of which 279 are evidence (236 stop-crossed, 43 short-unbacked) and 10 are named (7 with no
    readable setup direction, 3 listings too new for a stop); the local macro gate checked all 159
    names with fresh headlines and refused none; 2,469 headlines stored; Supabase holds the same 576
    decisions and 316 signals; `/api/health` clean; the watchdog's own run reported "healthy, nothing
    to restart".

    **The lesson is the one rule 71 already taught, at larger scale:** a green local run proves the
    code, not the deployment. Each of these lived in the gap between the two -- a secret, a clock, a
    connection's lifetime, a foreign key on the other database -- and was found only by running the
    real thing where it really runs and reading its log.

77. **Horizon and validity are read from what decided, and the learning loop reports without rewriting.**

    **Horizon.** Every direction comes from the swing setup (20/50 session averages) or the longer one
    (100/200). That is the horizon: Swing (1-7 days) or Position (1-4 weeks). The directive suggested
    deriving it from the stop-to-target distance; that distance is a consequence of the setup's window,
    not a second measurement of it, so it is not used. **Validity** runs from the day the current call
    began -- the start of the decision log's run of identical verdicts -- for 7 days (swing) or 28
    (position), and a call older than that reads "Expired". There is no "Invalidated" on a direction:
    a crossed stop is already a WAIT (`stop-crossed`) with its reason printed. One function
    (`lib/validity.ts`) and one component (`HorizonValidity`) serve the list rows and the asset panel,
    and the two now share one column set; a test pins the shared labels. The grade moved into the Action
    cell beside the verdict it grades.

    **The learning loop.** Every decision was already logged and measured at +1, +5 and +20 sessions;
    the report reading those measurements (`tools/scorecard.py`) only ran by hand. It now runs nightly in
    the decision workflow. It still only reports. The directive asked for automatic down-weighting of
    sources and parameters that "yield false signals"; a rule that rewrote its own thresholds from a few
    weeks of outcomes would fit those weeks' noise, unreviewed, which is the opposite of sharper. As of
    2026-10-10 no outcome has matured (583 logged, 0 matured), and the scorecard prints no rate, which
    is the correct output for that state.

    **GitHub drops scheduled runs, and a schedule cannot fix a schedule.** Measured the same day:
    `cron live quotes` (every 15 minutes) fired once in three hours, the watchdog (hourly) once, and
    `cron crypto` (every two hours) about every six. The watchdog now also runs on `workflow_run` after
    every data lane, which is an event and is not dropped; proven on GitHub when a live-quotes run
    finished and the watchdog started by itself. That makes recovery chain off any run at all. It does
    not make the 15-minute live cadence real; the on-demand refresh in `/api/quote` is what keeps a
    viewed quote fresh between ticks. A fully reliable clock would need an external scheduler calling
    the dispatch API, which means a token held by a third party: the owner's decision, not made here.

78. **The rising-star marker is rule 54's own recommendation, and it is fired by measured events only.**
    Rule 54 backtested four early entry rules and concluded the two that beat the trend
    (`squeeze_break`, the expansion out of a six-month compression; `vol_flip`, momentum turning on a
    busy session) belonged on the card as "a marker saying this one was caught at the start". That is
    what `lib/earlySignal.ts` is: "Rising star" for an upward event, "Falling star" for a downward one,
    on the list rows (beside the action and grade) and on the asset page (header and an "Early signal"
    field), from one function. It says how the event sits with the call -- with it, against it, or on a
    name the rule table still holds back -- and it never instructs: the requested tooltip "Enter ASAP
    within Entry Zone" was not used, because urgency is the one thing this site never adds.

    Two requested triggers were not built. Price/RSI or MACD divergence is not computed and has never
    been tested, and rule 54 found that a rule which is merely earlier (`inflection`) pays less than the
    trend. A news "sentiment velocity spike" cannot promote a name, because news may only ever withdraw
    confidence (rule 44); a headline that lifts a name onto a highlighted list is exactly the pump the
    macro gate refuses. On 2026-10-10, 64 names carried the marker (45 up, 19 down).

79. **A verdict change is a stored fact, and the price a row leads with is one trade, not two.**
    `lib/stateChange.ts` reads each name's newest run in the decision log -- the verdict before it, the
    gate that began it, the cycle it began in -- and names the change: REVERSED (a direction flipped),
    INVALIDATED (`stop-crossed`), OVERRIDDEN (`macro-veto`), WITHDRAWN (another stated reason) or NEW
    CALL. The first three are red warnings; the reason is the gate's own words. A row shows a change
    only if it happened in the newest cycle and the page shows the verdict the log recorded. The asset
    page opens with a banner listing the last changes with the close each side was read from. On the
    first two logged days there were 58 real changes (1 reversal, 21 invalidations), so the requested
    mock mode was built as test fixtures for every kind, not as invented verdicts on the public site.

    **The price column.** It led with the close and put a newer last trade under it, so the row showed
    two prices that looked like one stale and one fresh. When a stored trade adds something, the row
    now leads with that trade, its own day and UTC time directly beneath (one fact, so the two cannot
    disagree), and the close the decision reads on a third, labelled line. The column, and the asset
    panel's matching field, are "Price & time". The decision still reads the close: a price for a
    session still trading is not a close (rule 41), and that is now said on the row rather than hidden.
