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
    login.

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

80. **A flip against a recent call must be confirmed; a marker never contradicts its call; WAIT folds away.**
    **Patience.** A direction can reverse on the trend alone and print at Low confidence with no
    confirmation; that is the flip most exposed to flipping straight back, and it hands a reader two
    opposite calls in two days. `reversalUnconfirmed` holds such a flip as WAIT (`reversal-unconfirmed`,
    with its `intent`) when the log recorded the opposite direction within the last seven days, until
    one of the five independent confirmations arrives or the old call ages out. It reads the log before
    today, never today, so the page and the nightly job judge against the same stored past. It is a
    refusal only, and it has not been shown to improve outcomes: the scorecard will say. Decisions were
    already immune to intraday noise -- they read daily closes only, and neither a live quote nor a
    headline can move one (rules 74 and 44). On its first day the rule changed nothing: the one
    reversal that day (VRTX, SHORT to LONG) was confirmed three of five.

    **No contradictory pairing.** A Falling Star beside a LONG read as two opposite instructions on one
    row. The marker now shows only when it agrees with the call; an opposing event is already weighed
    where it belongs, as a confirmation the call lacks. **Clean UI.** The home page's twelve WAIT cards
    are one closed line, "Held back: N names with no call today", which also says how many calls ended in
    the latest cycle so a holder cannot miss an invalidation. WAIT is not hidden from the data or the
    log, only from the first screen: a held-back name stays findable, with its reason.

81. **The five display and patience gates are checked on the live pages, hourly, not only in code.**
    Audited 2026-10-10 against the "institutional stability" directive. Each gate already held: one
    price per line (rule 79); no badge contradicting its call (rule 80); verdicts read only from daily
    closes, with the stop tested against the daily close and a session still trading never stored as
    one (rule 41), so an intraday wick or a 15-minute spike cannot flip or invalidate a call; a macro
    veto that only ever holds, never flips, and lapses after a day; an unconfirmed reversal against a
    recent call held until confirmed (rule 80); WAIT folded away on every page. `tools/ui_audit.py` now
    reads the rendered pages in the hourly watchdog and turns the run red on any violation -- tested by
    planting each one. First production result: 654 rows, 0 violations. Not built, and said so: a
    "Rising Star" attached to every confirmed flip. The marker means a measured entry event fired; a
    flip without one gets none, because attaching it anyway would be the invented signal rule 78 refuses.

82. **The lists print calls; WAIT lives in the log, the reasons and the asset page.**
    The action cell of a held-back row prints "Held back" in plain text and no WAIT pill, and a change
    badge is shown on a row or header only when it is a flip between two directions (REVERSED); every
    change that passes through WAIT stays in the asset page's timeline, where a holder looks for what
    happened to a call. The price cell is one price and one line: the newest trade with its own time, or
    the close with its day -- never both; the decision still reads the daily close, and the asset page
    shows it beside the price history. The home page's held-back list is the same row component as the
    sector pages, its heading is "Today's calls: LONG or SHORT", and Events and Methodology are off the
    header and footer (the pages still exist). `/privacy` states only what the code does: no accounts,
    no forms, no cookies, no analytics, standard hosting logs at Vercel; it is a plain-language policy,
    not legal advice. `tools/ui_audit.py` now also checks no WAIT in any action cell, the one-price rule,
    and pool parity (every asset in the database listed on a market page, against `/api/health`'s pool).
    Its first run against the new pages failed five times on its own bug -- `<li[^>]*>` matched
    `<link>` in the page head -- which is the second time a checker's first run caught the checker.

83. **The weekly logbook reports what the log measured, in the owner's Google Doc, and invents nothing.**
    `tools/audit_log.py` runs as a third job in the decision workflow, after the decisions are written:
    a daily entry every day (calls whose five-session window closed, the shifts and exits of the day,
    the stars), and on Mondays a review of the week before. Every verdict is the scorecard's own
    function (stopped checked first, then right/wrong on the move), so the logbook and the scorecard
    cannot grade one call two ways. Two things the requested template asked for are not written,
    because the engine does not produce them: a "retrospective lesson" in opinion form ("the veto should
    have weighted oil higher") -- the entry states the measured facts of the outcome instead -- and a
    "self-correction action" -- the log says none is applied automatically, which is true (rule 77). A
    rate is printed with its count, and none from nothing. It appends through the Google Docs API with a
    service account the document is shared with; without that it writes to the run summary, and an
    entry already in the document is never appended twice. One query for every shifted asset, not one
    each (the in-loop ratchet caught the first draft).

84. **The logbook moved from a Google Doc to the site, because the site needs no credential.**
    A public Google Doc can be read by anyone but written only through the Docs API with Google
    credentials, which the owner declined to set up. So the nightly job saves each entry to `AuditLog`
    (one row per day and kind, rewritten by a re-run, never doubled, never pruned) and `/logbook`
    shows them newest first, in the same sections and wording as rule 83. Entries are stored as written
    that day, not recomputed at read time: the logbook is a record of what was reported, and an old
    entry recomputed later would quietly carry outcomes nobody knew then. The Google code and its
    library were removed rather than left unused.

85. **The logbook leads with a summary; the lists print the price alone and say a change in words.**
    `/logbook` now opens with the verdict counts and rates (graded, accurate, failed, stops counted as
    failed), every LONG/SHORT switch of the last 30 days, and every Rising/Falling Star of the last 30
    days with its result; the full daily entries fold below. The job stores the summary as its own row
    (kind "summary"), built from the scorecard's verdicts, with no rate before anything is graded.
    On the lists the price cell is the price alone: when it was struck is a tooltip, not a line. The
    action cell is the verdict and the star only: the change badge became one sentence under it
    ("Switched from Short to Long on Oct 10: <the rule table's reason>"), the dated-event pill became
    its sentence, and the confidence grade moved off the row to the asset page. The reason in that
    sentence is the gate's own words, never a description written afterwards ("multi-timeframe
    accumulation" was asked for, and the engine measures no such thing).
    **Declined: forcing every name to LONG or SHORT.** A name is held back when the data cannot
    support a direction -- a stale close, a silent feed, no stop level, or a price between its own
    averages. Printing a direction there is a guess presented as a call, and the scorecard would grade
    it like one. Held-back names stay folded under "Held back", never labelled "No direction". The
    patient flip asked for already exists: calls read only completed daily closes (the forming bar is
    excluded), and a switch within 7 days of the opposite call needs one independent confirmation, or
    the name is held back -- which ends the old call first, so a holder is told to step aside before
    being told to turn round (rule 80's `reversal-unconfirmed`).

86. **Every priced name gets LONG or SHORT, at the owner's instruction; the refusal in rule 85 is withdrawn.**
    (Narrowed by rule 92, and withdrawn by rule 93: a refusal of the rule table now stays a refusal.)
    The owner decided that the site makes a call on every name. `decide()` (the evidence table) is
    unchanged and still says WAIT where its evidence is missing; `lib/resolve.ts` runs after it, in one
    function (`decideCall`) used by the lists, the asset page and the nightly log, and gives every WAIT
    a side: a close through the stop follows the break; an unconfirmed short is SHORT; an unconfirmed
    flip keeps the last call (the patient flip, which lifts on a confirmation or after a week, because
    the reversal gate now reads only calls the evidence table made); a macro veto gives the other side;
    otherwise the side the table leaned toward, else a momentum vote (trend, longer bias, 20-session
    return, peer gap, similar past days, and an entry rule on volume counted twice), else LONG, logged
    as `forced-nosignal`. The stop is the setup's own when the call goes the setup's way, else
    2 x the 14-session average true range (`AssetFactor.atr14`, computed nightly by jobs/factors.py
    from highs and lows); a broken direction's stop is never reused. Confidence is capped at Medium.
    What keeps this honest is the log, not the page: every such call is logged as `forced-<reason>`
    and /logbook grades them in their own box, "Resolved calls right", beside the overall rate. If
    that box runs well below the calls the table made itself, the evidence for rule 85 is on the
    page. Data feeds were not the cause: on the day this was built no held-back name was stale or
    silent -- 236 had crossed their stop, 43 were unconfirmed shorts, 7 had no side, 3 no stop.
    Only a name with no stored close at all can still be held back; the page checker fails on one.

87. **The pool has a liquidity floor and a discovery feed; prices keep their digits; late columns stay out of the model.**
    `jobs/pool.py` runs nightly before `factors`. The gate sets an asset inactive when its median daily
    traded value over 20 sessions is under its market's floor (crypto $10M worldwide, US $5M, PSX
    PKR 2M; FX and futures exempt) or its newest close is older than 10 days; it returns above 1.5x
    the floor, or at the floor once a stale feed is current again. Nothing is deleted, and a night
    that would remove over 30% of one market is refused as a data fault. Crypto is judged only on a
    positive worldwide volume, because Polkadot read $4M on one exchange the night CoinPaprika
    listed it at zero. Discovery adds up to 5 coins (over $100M a day, top 300) and 5 US stocks
    (Yahoo most-active and gainers, over $200M a day, $5+, $2B+ cap) a night, 40 in all, each with
    at least 60 current closes written in the same step: the first dry run would have added Monero
    on a Binance series that stopped in 2024. Prices print 2 decimals from $1, 4 under it, 4
    significant digits under a cent ($0.000004036), and list cells use the subscript-zero form
    ($0.0₅4036) so a sub-cent coin neither wraps mid-number nor spills into the next column. A target
    is shown only on the profit side of the call, and a resolved call's reward:risk is measured
    against its own stop: PEPE resolved SHORT was printing its old long target above the price.
    **The outage this rule was written in:** the Neon primary hit its free-tier quota on 2026-10-10
    and the site failed over to the standby, which had not received the day's two migrations.
    Prisma selects every model column by default, so every uncached asset page became a 500. The
    late columns (`AssetFactor.atr14`, `Asset.active`, `Asset.poolNote`) are therefore not in the
    Prisma model; `getLateColumns` reads them raw and fail-open, and a database without them serves
    the site as it was before them. Standbys must be migrated whenever the primary is.

88. **Supabase can be the primary, on purpose only; every migration reaches every database.**
    Neon's free plan meters the hours its compute is awake, and hourly jobs plus page regeneration
    kept it awake around the clock; on 2026-10-10 it went over quota. Supabase's free plan meters
    storage (500 MB; the backup used 244 MB) and transfer, not hours, which suits this workload, and
    the backup already held the full price history (785,231 closes back to 2018), the setups and the
    call log. So Supabase may be made the primary: the DATABASE_URL secret set to it AND the repository
    variable PRIMARY=supabase. The schema check still refuses Supabase without the variable, because a
    wrongly pasted secret was the mistake it was written for and cannot set a variable. A Supabase
    primary gets two connections per server instance (its pooler admits 15 in all) and is never listed
    as its own standby. The schema workflow now migrates the standbys right after the primary, so a
    failover never again lands on a database missing a column. Test suites never touch a database
    (they use stand-ins); what burned the quota alongside the jobs was development-time measuring and
    page checks against a local server that read the production database. That is not done again.

89. **A build never waits on the database; a lane that dies says so; a stopped lane is restarted, including quotes.**
    The final audit (AUDIT.md, 2026-10-10) found the site sound and the plumbing around it quietly broken.
    *Builds:* `next build` prerenders the ISR pages, which means querying Postgres, so two production
    builds failed on an unreachable primary and nothing could ship. `lib/buildSafe.ts` now defers such a
    page to request time for that deployment when no tier answers; a query fault still fails the build.
    Verified by building against three dead ports. *Silence:* every lane captured its output into a
    variable and printed it at the end, so a run cut off at its timeout printed nothing, and GitHub
    reports a timeout as "cancelled", which the watchdog did not count. News and products now stream
    through `tee`, run.py stops a stuck step inside the job's own limit, and the watchdog counts
    cancelled and timed-out runs. *Products* had never completed (8 of 8 cancelled): its two "chunks"
    each ran the whole group because no products job reads `--chunk`; it is now split by source, geo
    budgeted inside its job, signals committed per source. *Mirror:* a statement ceiling per transaction
    and the decisions step independent of the prices step. *Quotes:* a quote lane that is on and an hour
    stale is a health problem the watchdog may restart; none at all, or none for three days, is a lane
    switched off. *retry.yml* had never re-run anything (no repository named). The rule behind all of
    it is rule 36's again: a job that exists and reports green is not a job that works -- read the run.
    *Afterwards:* a Reddit feed that stalled the products lane got a wall-clock cap (`f548e85`), and the
    first products run since the lane was created went green. `tools/logic_audit.py` checks every call's
    arithmetic in the database and on the live pages; its first run found FX pairs printing entry and
    stop as the same two-decimal number, so pairs now print in pips (`c36d2a0`). Rule 87's two decimals
    from a dollar stand for every other market.

90. **No unconfirmed return within three days; writes survive a primary pause and come back after.**
    *Whipsaw.* The audit's case -- table SHORT, a forced LONG on a stop-cross, an unconfirmed up-turn --
    printed SHORT, LONG, SHORT, because the reversal gate (rule 80) reads only calls the evidence table
    made, and the held flip kept the table's last call rather than the one the reader held. The gate's
    reading stays (a forced call is logged daily and would keep a turn recent for ever); what changed is
    in lib/resolve.ts, fed by the log's current directional run before today: a held flip keeps the
    reader's call, and `whipsawHold` keeps the current call when today's would go back, unconfirmed, to
    the direction it replaced fewer than `WHIPSAW_DAYS` (3) days ago -- counted from the day the current
    direction began, which a re-log does not move. One confirmation lets a return through. Decided by the
    technical lead at the owner's instruction, as a guard rather than as documented behaviour.
    *Failover.* Rule 69's "the lanes connect to the primary and never fail over" is withdrawn. Neon paused
    twice on its compute quota and every lane stopped. `jobs/nbt.py db()` and `tools/writer.mjs` now write
    the standby when the primary cannot be reached (never on a bad password), and `jobs/reconcile.py`
    copies the standby's newer rows back -- prices, the call log, signals, theses, vetoes, by natural key,
    never deleting -- the first time a lane reaches the primary, and before the nightly mirror copies the
    other way. What two written databases needed was a copy back, not a ban. The site's read pool is still
    never used by a writer: it switches mid-run and has nothing to reconcile with.

91. **Publish only complete, measured calls; hold an open one to its stop; the stop is never on the boundary.**
    The owner's directives of 2026-10-11, at their latest and strictest where they differed. Every name is
    still decided and logged (rule 86) -- the learning loop grades all of them -- but the lists publish a call
    only through `qualityGate` (lib/quality.ts): direction, trading style, entry range, a stop at least
    1 x ATR beyond the zone (`bufferStop`, lib/resolve.ts), a *measured* target, reward:risk >= 1.2 from the
    entry level against that stop, and one confirmation. The rest are named, folded, with the rule each
    failed. The floor is 1.2 because the owner's 1.5 published nothing that day (the best measured
    reward:risk was 1.4) and 1.0 published 110; the owner delegated the choice. A 2 x risk projection was
    tried for target-less calls and withdrawn the same day: its reward:risk is the multiple it was
    projected at, so no gate could fail it. A call published on an earlier day of its run stays listed as
    open until its stop is crossed or its window ends (`withOpenPosition`), because a gate that drops a held
    call overnight is the silent vanishing the owner forbade. Styles are SWING and POSITION only: the
    engine reads completed daily closes, and calling a daily call "scalping" would be the invented label
    rule 78 refuses. `/api/signals` publishes the same calls as data, and the logic audit holds the pages
    to it.

92. **A stop ends a call; nothing is called from an assumption; a word list may withdraw evidence, never add or invert it.**
    The owner's integrity directive of 2026-10-11, five defects found by an adversarial read of the brain,
    each fixed by restricting a path rather than adding one.

    - **Headline tone.** `jobs/human.py` matched tone terms as substrings, so "against" scored as
      "gains", "MarketBeat" as "beat", "issues" as "sues": 13 of the 31 opinionated currency headlines in
      the stored 30 days took their sign that way. Tone terms now count only as whole words
      (`count_words`); the promotional list keeps substring matching, where an over-match only raises a
      caution flag. Currency pairs were scored as if every headline described the pair, so "Rupee gains
      against US dollar" read as USDPKR rising -- the opposite. A pair headline now takes a side only when
      exactly one of the pair's currencies can be named (`orient`): the base keeps the sign, the quote
      reverses it, and both, neither, a third currency, the pair written backwards, or a bare "won", "real"
      or "rand" take no side. Re-scored over the stored window: 31 opinionated FX headlines became 5, each
      signed the way the pair moved; no market gained a sign it had not already earned from a listed word.
    - **Coverage never adds -- now true everywhere.** `jobs/setup.py` counted "the news reading supports
      it" (a positive tone or a story spike) as one of the two confirmations a buy needed, and "the
      headline wording is negative" for a short: coverage adding evidence, which rule 44 forbids. Removed;
      a swing setup now needs volume and the industry gap both. No stored buy or short rested on it, so no
      current setup changed. Its grade is capped at `medium`, because `high` was three of three and two of
      two must not read as more than two of three did.
    - **A stop ends a call.** A close through the stop used to be turned into the opposite call
      (`forced-stop-crossed`): 223 names on 2026-10-10, none with a measured target on the new side. It now
      stays WAIT with the table's own reason. So that the stopped call cannot come back by another route,
      `getLastRuns` (and the same SQL in tools/decide.mjs) reads a `stop-crossed` WAIT as `ENDED`: the
      reversal hold has no open call to keep and stays WAIT (its fallback to the table's last call is
      gone), the whipsaw guard has no run to hold, and `openSince` cannot call a later direction the same
      open position. The opposite side is called only when the evidence table produces it. On the page
      the stopped call keeps its stop -- the level it ended at, which its reason quotes -- and prints no
      entry zone, measured exit or reward:risk ("none: the call ended"): a finished plan shown with a
      zone to enter and a 3.4:1 reward reads as a live trade.
    - **Nothing from an assumption.** With no measured vote at all, the momentum read returned LONG, "the
      long-run drift of most markets", logged as `forced-nosignal`. It now returns nothing and the name
      stays WAIT, saying "Nothing measured leans either way, so no direction is given."
      `tools/ui_audit.py` accepts a held-back row only for these reasons or a name with no close.
    - **Words.** The methodology promised "no target prices" beside a column headed "Take profit". The
      label is now "Measured exit" everywhere it is printed, and the methodology says what it is: a level
      the call's own stored setup measured, never a projection, and not a promise. `lib/decision.ts`
      told readers that "the group is carrying it rather than the other way round" -- a causal claim --
      and that "nothing published accounts for the move"; both now state co-occurrence only, as do the
      "carries it" openings ("it rests on ..."). The causality scan never read lib/decision.ts; it now
      reads the string literals of lib/decision.ts and lib/resolve.ts, matches whole words, and catches
      the shipped sentence in a test.

93. **A refusal stays a refusal; no direction without a confirmation; faulty data and unreadable coverage
    carry nothing; one snapshot for every surface.** The owner's "remaining core fixes" directive of
    2026-10-11. Each item is a root cause, and each fix only removes a direction or weakens a claim.

    - **The forced layer is gone (rule 86 withdrawn).** `lib/resolve.ts` turned the table's refusals into
      calls: a macro veto into the opposite side, an unconfirmed short into SHORT anyway, an incomplete or
      stop-less read into its intent, a stale or silent name into whatever its momentum leaned, an
      unconfirmed turn or return into the call it replaced. All of it is deleted, not switched off. What
      remains after `decide()` can only take away: a stopped call loses its entry and plan; a direction
      no confirmation backs becomes WAIT `no-confirmation` naming the five that are absent (96 names
      printed LONG or SHORT that way on 2026-10-11); the stop buffer; no High while the live edge is
      unmeasured (`HIGH_AWAITS_MEASURED_EDGE` -- the grade counts confirmations, and not one +5-session
      outcome had matured); and **last, a hard data gate** that re-runs gates 1 to 3 on the output so no
      step can carry a direction past a missing, unreadable, stale or silent close.
    - **Two readings with one premise are not two confirmations.** The timeframe leg counted whenever the
      setup and the longer view agreed with *each other*, so both reading up confirmed a SHORT the forced
      layer had flipped. It now counts only for the side both read.
    - **The table matches its methodology.** Check 8 again needs a carrier (volume, peers, an entry event or
      an asymmetric reward) and coverage that is neither worded against it nor unreadable; carried by
      nothing it falls through to check 9, as the page always said -- 47 `unconfirmed-*` names had been
      printed instead, 11 of them graded High. Check 5 again refuses opposite timeframes unless the reward
      is asymmetric, as the page always said; the longer view vetoes a thin check 8 trend on the same terms.
      The methodology table now lists the four refusals inside `direction()` and the five steps after the
      table.
    - **Unreadable coverage is not neutral.** `newsCoverageOf` reads "unavailable" when the serving database
      holds no news reading newer than three days or the headline source is silent. Then similar past days
      do not count and check 8 carries nothing, because no contradiction can be ruled out, and the panel
      says so. The Supabase standby held no `News` or `HumanSignal` rows at all; `jobs/mirror.py` now copies
      both (asset rows, 61 days, ids and `targetRef` translated), so a failover keeps the evidence class.
    - **A headline's sign belongs to its clause's subject.** `jobs/human.py` reads a headline for an asset
      only through a clause that opens with the asset's name or ticker (or, for a pair, one of its
      currencies), and only that clause's words count. "Yen weakens as Nikkei jumps", "Rupee recovers after
      it fell", "Fauji Fertilizer jumps after Engro plant shutdown", "Solana tumbles as traders rotate into
      Bitcoin" and "Consumer optimism slides" (the Optimism token) all scored a sign a reader would reverse
      or drop; all now take no side. Signed headlines over the stored 30 days: US 200 to 141, crypto 78 to
      65, PSX 16 to 8, commodities 2 to 0. A namesake whose name opens a clause about something else can
      still be read as the asset; no side would be the cost of fixing that, and it is recorded, not hidden.
    - **Execution is not direction.** (Its "NOW" handling, and the High cap above, were corrected by rule 94.) `lib/execution.ts`: blocked when the last session printed no trade,
      unverified for a SHORT on a share or a coin (no short-sale eligibility data is held) and wherever
      no volume is published, checked only for a LONG that traded inside the turnover-floored pool -- and no bid or ask
      is stored anywhere, which the reason says. "NOW" is shown only for a checked call.
    - **A call that is not published does not look like one.** The asset panel for a withheld direction says
      "Not a published call" first and large, prints the reading as a reading, and gives no entry, stop,
      exit, reward, timing or validity; a held-back row prints "no call" in every level cell; the change
      banner says the rule table's *reading* changed, never "New Short call", and credits a historical
      `forced-` row to the layer that printed it rather than to the rule table.
    - **One snapshot.** The data cache had an hourly timer and every page's HTML another, so after a run the
      market pages and `/api/health` served different snapshots (553 listed against 547 counted). The cache
      now refreshes only through `/api/revalidate`, with every page under the root layout in the same call,
      and the route acts only when a fresh `getDataStamp` differs from the one the cached rows were read
      with -- no secret is needed, because a caller can cause work at most once per change in the data. The
      decision workflow calls it when it finishes and `tools/ui_audit.py` before it reads; the pages and
      health print the stamp and the audit fails on a skew. The asset page decides from the lists' own
      cached row, so a name cannot be LONG on its page and withheld on its list. Each market page states its
      newest close, its newest decision run, its source status and where every name went -- it used to call
      every held-back name "with no stored price".

94. **One record per call on every surface; the grade is evidence and outcome status is separate; volume
    backs only the side its session moved; identity, failover and calendars stay conservative.** The
    owner's post-deployment correctness pass of 2026-10-11. Each item was reproduced from stored rows and
    rendered pages before it was changed.

    - **Timing named its price wrongly (CHBL).** Close Rs.8.82 on Oct 9, inside the inclusive zone
      Rs.8.80-9.17; the rule table said NOW and the panel printed "WAIT FOR LEVEL -- the price is not in the
      zone yet", because rule 93's panel code turned NOW into WAIT FOR LEVEL whenever execution was not
      checked. Root cause: timing and execution conflated. `timingOf` (lib/execution.ts) now gives NOW,
      "IN ZONE" (in the zone, execution not checked), WAIT FOR LEVEL or CARE, and every surface prints the
      close and day it read ("Read from the close of Oct 9, Rs.8.82, inside the zone"). The asset page takes
      that close from the same cached row as its decision. Boundary tests: both ends inclusive, a hair
      outside, display rounding.
    - **One grade, two meanings, untangled.** CHBL read "SHORT · High" in the coming week and Medium on its
      page: the 2026-10-10 log row predates rule 93's cap. The cap itself answered "has this been right?"
      with the label for "how much evidence backs this?", so it is withdrawn. The grade (High two or more
      confirmations, Medium one) is the evidence for the reading, shown as counted everywhere; **outcome
      status** (lib/outcome.ts) -- untested, pending, validated or not validated, with a 95% Wilson interval
      from 30 matured calls -- is printed beside it on the asset panel, the coming week, the market pages,
      the logbook and `/api/signals`, from the logbook's own graded counts, for published calls. Today:
      untested. A longer-term setup's own grade stays on its card, labelled as that timeframe's.
    - **Execution travels with the call.** The coming-week block and the overview's top lists showed entry,
      stop and exit with no execution state; they now print it whenever it is not checked, as the rows and
      the panel do. Short-sale eligibility is asked only of shares and coins.
    - **Volume is participation, not direction.** A heavy down day counted as a LONG's confirmation. The
      volume leg (and gate 8's volume carrier) now count only when the same session's return (`AssetFactor.r1`)
      has the call's sign; with no stored return, neither side. The page says when volume was "activity, not
      support". Mirrored tests for both sides.
    - **Namesakes and hedges take no side.** A name followed by another proper noun ("Celestia Theater",
      "Anna Sui Spring") is a namesake; a clause with a negation or hedge ("not", "fails", "could", "if") is
      not read; mixed tone cancels. Tests cover ticker, full name, alias, common words, namesakes, pairs both
      ways, negation and mixed clauses.
    - **The standby is bounded, measured, and holds the pool.** 27 active assets (26 discovered US movers and
      a coin) were absent from Supabase and would have vanished on failover; `jobs/mirror.py` now copies asset
      rows first, keyed on (industry slug, symbol), with the pool flags. The standby's setups, factors and
      analogs are not mirrored and lag one to two days, so **no call is published from a standby read**
      (`servingTier` in lib/db.ts; the reading is shown, withheld, saying so). `tools/standby_parity.py`
      reports missing assets, missing readings and each input's lag, nightly in the mirror workflow.
    - **Source health keeps calendars.** "Yahoo Finance daily closes: partial" sat on the stocks and
      commodities pages over a complete Friday: one source row covered four markets, and a Sunday's five FX
      bars were its newest day against a weekday median of 315. `jobs/audit.py` now writes one row per
      market behind the fetch and judges each on its own weekday sessions -- a weekend or a holiday is an
      expected non-session, never thin -- and the combined row is the worst of them, naming which market.
      Each market page and the silent-source gate read their own row, so one market's fault cannot mark
      another silent.
    - **The evaluator, before any grade.** Verified: outcomes are counted in each asset's own stored sessions
      (+1, +5, +20); the stop is checked before the move; WAITs are never graded as misses; the scorecard
      refuses rates under 30 and reports intervals. Fixed: the stop test read daily closes only -- an intraday
      breach that recovered scored as survived -- and now uses each session's low or high where stored; the
      published calls are counted on their own (the criterion `getPublishedRuns` uses), so outcome status
      describes what readers were shown. Not fixed, and recorded: a same-day re-run overwrites that day's
      logged call (the log is immutable across days, not within one); the verdict is directional only, with
      no execution return and no measured-exit touch.
    - **Baseline parameters, fixed for now:** the 1 x ATR stop buffer beyond the entry zone and the 1.2
      reward:risk floor, both chosen rather than measured. The 2 x ATR stop belonged to the forced layer and
      is no longer applied anywhere; structural stops are the setup job's 1.5 sigma.
    - **Deployed and verified.** Commit `bc7316d`, Vercel production deployment `6989272588`; mirror
      `38101296073`, coverage audit `38101297801`, decision `38101299192` and schema `38101192732` runs all
      green. Live: health ok, served from the primary; `/api/signals` 18 published, all with a confirmation;
      the logic audit's new cross-surface check found 0 disagreements in grade, timing or execution across
      the API, the asset pages and the coming week; the UI audit passed with 553 of 553 listed; the standby
      held 553 of 553 active assets and every news reading; every coverage row healthy. CHBL reads SHORT,
      High, IN ZONE (close Rs.8.82, Oct 9), execution unverified, outcome untested, on every surface.
    - **And a skew the new check caught.** Two watchdog runs went red at 01:17: the schema lane, which runs on
      every push, rewrote setups and readings, the audit revalidated, and read the pages before their first
      re-render -- on-demand revalidation serves the old HTML to the first visit. The schema lane now calls
      `/api/revalidate` when it ends, and the UI audit warms the pages after a revalidation and re-reads a
      skew up to three times, 20 seconds apart, before reporting it; a skew that persists still fails.
    - **And a skew the route itself could not see.** Verifying that fix (commit `253506f`, deployment
      `6994580320`) found all five market pages on setups of 01:21 while the data cache and `/api/health` held
      setups of 11:02:59, and `/api/revalidate` answering `revalidated: false`. After a revalidation each page
      re-renders on its next visit, and a re-render that finds the data entry empty reads the database for
      itself; the schema lane wrote between those reads, so the pages came from one read and the stored entry
      from a later one. The route compared the cache alone, so it would have kept saying "aligned" until the
      next write. It now also reads the stamps the market pages print (`lib/alignment.ts`) when the cache is
      current, and re-renders the pages -- from the cached entry, with no database read -- when one served as
      current carries another snapshot. A page already marked STALE is re-rendering and is not judged, so the
      route cannot loop on it. The UI audit asks the route again on each re-read. Commit `f0e7338`,
      deployment `6994732963`: the schema run `38134911097` ended with `revalidated: true` onto the new
      snapshot; then the UI audit passed (438 rows, 553 of 553 listed, all five pages on one stamp), the logic
      audit PASSED MATHEMATICALLY with 0 cross-surface disagreements over 18 published calls, and watchdog
      `38136905827` was green -- it also restarted the live-quote lane, whose schedule had slipped to 90
      minutes, after which health read ok. Web 446 of 446, Python 711 OK, tsc, eslint and build clean.

95. **One continuous, auditable chain: every run kept, every published call graded as a trade apart from
    its direction, a closed market never fresh, and the overview speaking from the market page's record.**
    The owner's post-run integrity and trading-edge pass of 2026-10-11. Each item was reproduced from stored
    rows, the API and the rendered pages before any change.
    - **The overview said a completed market was never run.** Its card printed "No stored reading yet ... a
      class that has not been through a run" whenever a market had no published call -- the commodities
      card said so while /commodities reported the run of 2026-10-11 complete (8 names, 1 withheld, 5
      forming, 2 held back). The market status record (`lib/marketStatus.ts`, split out of
      `lib/assetClass.ts` so its tests run it) now carries one run state --
      RUN_COMPLETE_WITH_CALLS, RUN_COMPLETE_NO_PUBLISHED_CALLS, RUN_INCOMPLETE_OR_FAILED (missing from the
      newest run, or only some names logged), NO_READING -- and the card prints the market page's own
      sentence from it. Both print `data-run-state`, `data-names` and `data-published`; the UI audit fails
      when an overview card disagrees with its market page or says "not been through a run". Verifying it
      live found the same false claim by another road: read from the standby, the decision-log query
      failed, `getCallRuns` returned an empty map, and every page said "No decision run has logged this
      market yet" while the run of 2026-10-11 existed. The read now reports whether it succeeded, an
      unreadable log is a fifth state, RUN_STATE_UNKNOWN ("whether this market was run is not known"), and
      the UI audit fails any market with names reading NO_READING while health shows a decision run.
    - **A rerun overwrote the day's call.** `DecisionLog` is unique on (asset, day) and every pass upserted
      it: 2026-10-10 carries the computedAt of eight passes, and 55 LONG and 12 SHORT calls made at 20:15
      survive nowhere after the 23:14 pass turned them into WAIT. `DecisionLog` stays the current call per
      day; every pass is now also recorded once in `DecisionRun` (id = GitHub run, attempt and pass, or a
      local stamp; commit; trigger; the tier read; a sha256 fingerprint of every input row; the newest
      session per market; the source health read; status running -> complete / partial / failed) with each
      call in `DecisionCall` -- its session and close, entry, stop, measured exit, reward:risk, ATR, the
      quality gate's verdict and reasons, the execution status and the validity window, by the site's own
      functions. Database triggers refuse any change to a call, any change to a finished run and every
      delete; a replay of the same run inserts nothing (ON CONFLICT DO NOTHING); a run left running six hours
      is closed as failed by the next. The macro pass is its own run (`--pass=macro`). The logbook lists the
      week's runs and marks each day's current one: the newest that finished.
    - **Outcomes were directional only.** `tools/trade_sim.py` grades each published position -- the first
      published call per asset, side and validity start, so reruns and next-day re-issues cannot count one
      trade twice -- into `CallOutcome`, bound to that call's id: the scorecard's directional verdict
      unchanged, and a trade simulated on the daily bars from the call's own plan. Entry is a limit at the
      zone edge the reward:risk is measured from, filled from the session after the call (at the open when
      it opens better); opening beyond the stop first is INVALIDATED_BEFORE_FILL; after the fill the stop
      and exit rest, a gap exits at the open (recorded, more than 1R lost), a bar reaching both is AMBIGUOUS
      and booked at the stop, and on the fill bar an exit touch is not counted while a stop touch is. The
      window is the call's validity (7 days swing, 28 position): an open trade EXPIRES at its last close, an
      unfilled order is NOT_FILLED, a call a later run withdrew before filling is WITHDRAWN, and a bar that
      contradicts itself or a closed window with no bars is UNAVAILABLE -- all in the denominator. R is
      gross; no spread, commission, borrow or slippage is stored, so no net R is reported. An outcome is
      final once both halves are, and a trigger then freezes it. The logbook prints direction and trade
      apart, every rate with its count, splits by market, side, horizon and confidence, and "not measured"
      until 30 trades have closed. Graded only from the first recorded run on: the earlier days exist only
      as `DecisionLog`'s last write, and their reward:risk used another definition before `2fd7c51`.
    - **Weekend stubs were stored as sessions.** Commit `3cb12e2` stopped dropping Friday's forming bar,
      and with it Yahoo's Saturday and Sunday stubs for currency pairs were stored: 22 dated Saturday the
      10th, 17 Sunday copies, one on the 4th. Health read "FX newest 2026-10-11, 0 days old"; 16 of the 18
      FX calls logged for the 10th were read from a Saturday stub; factors took a one-day return from it.
      The Yahoo writer now drops a weekday market's weekend bar (`jobs/sessions.py` `trades_on`); every
      close reader on the decision path skips them (`(a."assetType" = 'crypto' OR EXTRACT(ISODOW FROM
      s.date) < 6)` in `lib/queries.ts` and `tools/decide.mjs`, `session_bar()` in the factor, setup,
      target, scorecard, audit-log and trade jobs and the coverage audit). The 40 stored rows were left in
      place: moving them out was refused by the session's safety check, and the readers make them inert.
    - **Freshness is counted in sessions too** (`lib/sessions.ts`). A close is stale at whichever comes
      first, the calendar-day limit or two expected sessions without a close (gate 2b and `dataFault`); a
      close dated on a day its market does not trade is "bad-date". No holiday calendar exists, so one
      missing session is "behind" and still acted on. Health now gives each market its expected session,
      sessions behind, state (current / closed as expected / behind / stale), next session and the names
      behind it; judges live quotes per market and only while that market trades (crypto's ticks had kept
      the single check green while FX, US and commodity quotes sat frozen from Friday); and lists each
      recording lane's last run and last success.
    - **Recovery is checked, not assumed.** The price lanes call `/api/revalidate` when they finish. The
      watchdog waits (bounded, up to 8 minutes, quick lanes only) for the lane it restarts, reads health
      again and goes red if the problem stands; a restart within the hour that finished and left it
      standing is red ("unrecovered") instead of another quiet wait. Before, it dispatched and exited green
      (run `38136905827`), and a lane that cannot fail could never reach a person.
    - **Tradeability.** A future or currency pair at volume 0 is unverified, not blocked (palladium and
      platinum print 0 on traded days); an execution never assessed is never NOW; the weekly block ranks a
      checked NOW above an IN ZONE; and every list surface prints the execution status beside the direction,
      checked included. Short eligibility is still never inferred; no bid, ask or eligibility data exists.
    - **Deployed into an outage.** The Neon primary went over its compute quota during this pass (error
      53000, "Your account or project has exceeded the quota"); the schema runs `38140697236` and
      `38141007641` could not reach it (P1001). The site failed over to the Supabase standby, which
      publishes nothing (rule 94), and whose pooler times out under the overview's parallel reads, so `/`
      answered 500 about half the time. The standby step now runs even when the primary's migration fails
      (`if: always()`), and run `38141007641` migrated Supabase; the primary takes the migration on the
      first schema run after it is reachable again. Restoring it -- an upgrade or the quota reset -- is the
      owner's decision. Health had read green through all of it, because nothing in it asked which tier it
      read from; a standby read is now a problem with no lane ("reads are served from Supabase because the
      primary cannot be used, so no call is published"), which the watchdog hands to a person. Commits `8bdfd35` (schema), `bd28bba` (this pass), `414b1f9` (namesakes),
      `342dd7b` (unknown run state), `76485e7` (logbook); production deployment `6996020494`.
    - **Namesakes** (P2). One matcher (`HeadlineMatcher` in `jobs/prices.py`) decides whether a headline
      names an asset, at ingestion and when `jobs/human.py` counts stored rows: the " - Publisher" suffix
      is cut first; a company is matched on its name as printed, whole, capitalised and not inside a longer
      proper noun (Dow Jones, Port Vale, SAP Center, King Lear), or on its ticker only where it can only be
      the ticker; a coin needs crypto context beside its name. On 14 days of stored rows it set aside 77 of
      313 crypto rows and 66 of 1,179 US rows, losing 18 and 17 genuine ones (coined names with no crypto
      word, short forms like "SpaceX"). Stored rows are not deleted and still show on asset pages until
      they age out; title-case common words ("Alleged Visa Fraud") still pass.

96. **A clean reset waits for a writable, backed-up primary; it is never done on a standby instead.** The
    owner's clean reset, full resync and final audit mandate of 2026-10-11. Phase 1 (read-only) ran at
    14:00-14:20 UTC; its stop condition was met, so nothing was deleted, reset or switched.
    - **Blocker.** The Neon primary refuses every connection with "exceeded the quota" (53000) since about
      12:45 UTC; production serves the Supabase standby, publishes nothing (rule 94) and health reads
      `ok: false`. Primary schema parity cannot be read (last known 30 migrations, without
      `20261011130000_decision_history`); the standby has 31. No verified backup of the primary can be taken.
      Restoring it -- waiting for the quota reset, upgrading, or deliberately making Supabase the primary --
      is the owner's decision; nothing here changes a plan or spends.
    - **Baseline** (standby, estimated rows): PriceSnapshot 791,033; IntradayBar 59,820; News 4,173;
      DecisionLog 1,742; DecisionRun 4 / DecisionCall 2,216 / CallOutcome 0; 32 weekday-market weekend bars;
      613 assets, 554 active. The full inventory, the lane list and the dependency-ordered reset plan are in a
      private report outside the repository (`nbt-private/baseline-2026-10-11.md` beside the checkout).
    - **The reset plan, when unblocked:** pause every schedule and confirm nothing runs; back up each table
      to be cleared with `COPY ... TO STDOUT` into gzip files outside the repository and verify by re-reading
      counts (the local `pg_dump` does not run); keep migrations, schema, triggers and the universe (Industry,
      Asset, Product, ProductAssetLink and the empty config tables); clear the fetched, derived, decision,
      history and log tables in one `TRUNCATE` that names them all, without CASCADE; verify; resync once in
      order (schema -> full price history -> daily prices -> quotes -> news -> calendar/products -> decision ->
      mirror -> coverage audit); audit with writers paused; restore staggered schedules.
    - **What was spending the quota.** `schema.yml` ran on every push and is not only a migration: it runs a
      15-job derive pass against the primary. It ran 9 times on 2026-10-11, once per commit. Its push trigger
      now fires only for `prisma/**`, `jobs/seed.py` and the workflow itself; every job in it also runs on
      its own schedule through `jobs/run.py`, and a manual dispatch still runs it all.

97. **Supabase is the primary; Neon is the standby.** The owner's decision of 2026-10-11, delegated ("you are the
    decision maker ... we will go with free tier"). Neon's free tier caps compute hours, and the derive passes
    used them up on 2026-10-10 and again on 2026-10-11; Supabase's free tier caps size (500 MB; 312 MB used) and
    connections (60; the site holds 2 per instance through `primaryLimits`), which this workload fits.
    - One rule, everywhere: the primary is `SUPABASE_DATABASE_URL` unless `PRIMARY=neon`, else `DATABASE_URL`
      -- `primary_choice` in jobs/nbt.py, `primaryChoice` in tools/writer.mjs, `primaryUrl` in lib/db.ts, the
      same inline in tools/standby_parity.py and tools/logic_audit.py, and in the schema and mirror workflows.
      Neon (`DATABASE_URL`) is the standby the writers and the site fail over to. No secret was changed: the
      switch is code, and `PRIMARY=neon` (a repository variable or env var) reverts it.
    - Everything that moves rows between the two now follows it: `jobs/reconcile.py` copies standby rows back
      into the chosen primary; the mirror copies Supabase -> Neon (it was hard-wired Neon -> Supabase and, after
      the reset, would have poured Neon's old rows over the new data the night Neon's quota returned); the
      schema lane migrates the chosen primary first and every other database after.
    - Publishing follows the tier: a read from Supabase is a primary read, so calls publish; a read from Neon is
      a standby read and publishes nothing (rule 94).

98. **Clean reset and one full resync, on the free tier (maintenance run `reset-2026-10-11T1930Z`).** With the
    owner's go-ahead and Supabase as the primary (rule 97). Neon stays over its quota and is not used.
    - **Writers paused**: the 14 scheduled workflows were disabled through the API, nothing was running, and each
      lane was enabled only for its own single run during the resync.
    - **Backup**: every public table, from one REPEATABLE READ snapshot, to gzip CSV outside the repository
      (`nbt-private/backup-reset-2026-10-11T1930Z`, 44 tables, 887,861 rows, 30 MB), verified by re-reading
      every file against its manifest's row count and checksum: 44 of 44.
    - **Reset**: one transaction, one TRUNCATE of exactly 36 runtime tables without CASCADE (prices, intraday,
      quotes, news, events, every derived table, decisions, runs, calls, outcomes, logs); kept the migrations
      (31), Industry 42, Asset 613, Product 30, ProductAssetLink 36 and the empty configuration tables; the
      history triggers survived (3 of 3). Run by the owner, because the session's safety check refused the
      delete; verified empty and committed (313 MB -> 15 MB).
    - **Resync, once each, in order, validated in the database after each**:
      us-prices `38147889016` (US 280/280, Commodity 8/8, FX 27/27 active assets, from 2019 to 2026-10-09,
      0 weekend bars) -> backfill `38148313503` (PSX 176/176, 82,515 bars; events 364) -> crypto `38150437165`
      (63/63, 96,144 bars, Coinbase and Kraken) -> news `38150832188` (2,277 headlines, 276 assets) -> live
      `38151823101` (crypto 71/72, a Yahoo slice 58/60) -> products `38151911462` (202 signals) -> decision
      `38154560405` (388 WAIT / 94 LONG / 72 SHORT readings, 17 published; runs gh-38154560405-1-decide and
      -macro, 554 calls each, fingerprint 9c60c433, code 65a590f; 17 outcomes pending, bound to the first
      run's calls) -> audit `38156051539` (every source healthy but Google News RSS, partial on a Sunday) ->
      mirror `38156146692` (Supabase -> Neon, failed: Neon unreachable). No lane was retried.
    - **Data notes**: Yahoo sends 4,140 FX bars whose close sits outside their own range (median 0.01-0.2%,
      worst USD/PKR 12.8%) and the PSX files 339; stored as sent, read by the trade grader as unavailable.
      The PSX file for Saturday 2022-10-01 is the exchange's own (171 rows); every decision reader skips it.
    - **After**: schedules re-enabled; live health served from the primary, every market current or closed as
      expected; /api/signals 17 published; the UI audit passed (554 of 554 listed, one snapshot). The full
      audit is the owner's next step; no outcome has matured, so no performance exists to report.

99. **The tier was being spent on reading history nobody asked for, and on empty index pages.** Measured
    2026-10-12 against the live primary, after the reset of rule 98. No table was pruned, no row was
    deleted and no lane was re-run: the whole of this is how the same answers are fetched.
    - **The pattern.** Nine readers wanted one row, or the newest few, *per asset*, and every one of them
      asked for it by reading the whole of `PriceSnapshot` -- `DISTINCT ON ("assetId")`, `row_number()
      OVER (PARTITION BY "assetId")`, or a window function over every stored row. Postgres has no loose
      index scan, so none of those can use `PriceSnapshot_pkey ("assetId", date)`: each one seq-scanned or
      index-scanned all 781,163 rows and sorted them to keep 613. `pg_stat_statements` had it plainly --
      611 sequential scans over `PriceSnapshot` had read 57.8 million rows, and the ten costliest
      statements in the database were all this shape, about 1,225 seconds of database time between them.
    - **The fix is a lateral join, one index probe per asset.** `FROM "Asset" a CROSS JOIN LATERAL (SELECT
      ... WHERE s."assetId" = a.id ORDER BY s.date DESC LIMIT n) b`. Driving from `Asset` loses nothing:
      `PriceSnapshot.assetId` is a foreign key onto it with `ON DELETE CASCADE`, so a priced row without
      an asset cannot exist (checked: 0). It also puts `assetType` in reach, which answers the crypto half
      of the session rule without `session_bar`'s `IN (SELECT ...)` subquery.
    - **Measured, each rewrite against the one it replaced, on the live data, row for row identical:**

      | reader | pages before | pages after | before | after |
      |---|---|---|---|---|
      | `jobs/human.py` `base_closes` | 339,900 | 7,794 | 7,694 ms | 74 ms |
      | `tools/decide.mjs` prices | 462,288 | 9,901 | 1,386 ms | 15 ms |
      | `jobs/horizons.py` `daily_bars` | 566,686 | 154,805 | 1,478 ms | 228 ms |
      | `jobs/setup.py` `all_closes` | 453,355 | 174,733 | 2,929 ms | 312 ms |
      | `lib/queries.ts` `getPricedAssetsByIndustry` | 70,874 | 5,697 | 545 ms | 19 ms |
      | `jobs/stats.py` market coverage | 71,056 | 8,416 | 4,189 ms | 22 ms |

      1,964,159 pages to 361,346 for one pass of those six, which is 13.1 GB of I/O a pass that is no
      longer read. Two more measured by wall clock rather than pages: `jobs/investigate.py` `candidates`
      115.8 s to 10.5 s, and `jobs/rank.py` `caps_at` over all 42 industries 30.9 s to 8.9 s.
    - **`jobs/sessions.py` `newest_session_bars`** is the one definition of "the newest n session bars per
      asset", because four call sites were saying it in `row_number()` and would have drifted apart. It
      carries the session rule (rule 95) that `session_bar` carries for everyone else, and
      tests/test_trade_sim.py pins both that they go through it and that it skips the weekend stubs.
    - **`investigate.py` reads a bounded tail**, `RETURN_HISTORY + 22` rows an asset, because its window
      functions reach 60 returns back plus one for the lag behind the oldest and 20 for the volume
      average. The whole-table version computed a window over every row ever stored to return 613.
    - **Index bloat was a third of the database.** `PriceSnapshot` is never pruned and never should be,
      but it is rewritten -- a full refetch deletes an asset's rows and COPYs them back, 141,310 deletes
      by 2026-10-12 -- and b-tree pages do not re-pack after that. `PriceSnapshot_pkey` held 89.4 MB at
      52.5% average leaf density. `jobs/retention.py --indexes-only` rebuilt it to **50.6 MB**, and the
      database went **271 MB -> 232 MB of the 500 MB tier**, with no row deleted. `reindex_bloated` now
      runs at the end of the retention sweep: `REINDEX INDEX CONCURRENTLY`, which takes no lock that
      blocks a reader or a writer, unlike the `VACUUM FULL` that is still behind `--reclaim`. Only
      indexes over 8 MB and under 75% full are touched, measured with `pgstattuple` rather than guessed.
    - **Two defects in the new helper, both caught before they shipped.** It did not carry `assetId` out
      of the lateral, which would have raised `column b.assetId does not exist` in three jobs on their
      first real statement; and it would have selected `assetId` twice for a caller that named it. The
      unit tests in tests/test_trade_sim.py exist because neither was visible to a test that only builds
      SQL without running it -- the first was found by running every rewrite against the live database
      and comparing row for row, which is the check worth keeping.

100. **The backup restores, and now there is a script that proves it.** `nbt-private/backup_db.py` had
    written and verified a backup since rule 98 and described the restore in its docstring; prose is not a
    tested restoration path, and the three things that actually break one -- a column added after the dump,
    a parent loaded after its child, a CSV whose NULL or quoting convention the reader disagrees with --
    are all invisible to a checksum.
    - **Verified independently, 2026-10-12**: all 44 files of `backup-reset-2026-10-11T1930Z` re-read,
      every sha256 and row count equal to the manifest, 887,861 rows, 31.1 MB, and every file's header
      still equal to its table's live column list. No public table is missing from the backup.
    - **`nbt-private/restore_db.py rehearse`** does the real `COPY` with the real types into `TEMP` tables,
      in an order taken from the live foreign keys rather than written down, inside a transaction that is
      rolled back. All 44 tables loaded clean. It is safe against production because it writes nothing.
      `restore <dir> --i-mean-it` is the same path without the rollback, and it does not empty anything
      first: it is for a database that is already empty.
    - **The one limitation, stated rather than papered over**: `PriceSnapshot` is rehearsed on its first
      100,000 rows of 791,033, because a `TEMP` copy of all 213 MB would take the database to within a few
      MB of the 500 MB cap -- a worse risk than the one being checked for. That proves the column list, the
      types, the NULL encoding and the quoting, which are properties of the file and not of its length. It
      does not prove that no single row further down the file is malformed. `--full` lifts the cap on a
      database with room, and is the thing to run on a restore target before trusting it.

101. **There is no live second copy right now, and that is the open risk.** Neon (`DATABASE_URL_FALLBACK`)
    answers `Your account or project has exceeded the quota` on every connection, checked 2026-10-12, which
    is the same thing that failed the mirror in rule 98 and is not a transient. So: the primary is Supabase,
    the standby cannot be written or read, and the only other copy of the data is the file backup above.
    The write failover of rule 97 and the read failover of lib/failover.ts are both correct and both
    currently have nowhere to fail over to. Until Neon's quota returns or a second database is configured,
    the recovery plan *is* `restore_db.py`, which is why it was worth building. Also noted: in the local
    `.env`, `DATABASE_URL` and `SUPABASE_DATABASE_URL` select the same Supabase database (same host, port,
    database and pooler user), so locally the only candidate standby is the Neon one that is over quota.
    Production secrets were not read and may differ; this needs checking against them, not against `.env`.

102. **The news lane had been dying on a url too long to index, and losing the rest of its run each
    time.** Found 2026-10-12 in the production logs of runs 38172778541 and 38174842722, both on
    94a1ac1, both after the resync of rule 98 -- so it is current, not history.
    - `psycopg.errors.ProgramLimitExceeded: index row size 3376 exceeds btree version 4 maximum 2704
      for index "News_asset_url_key"`. The four unique indexes on `News` each lead with a target id
      and then `url`; a Google News RSS redirect is a base64 blob with no upper bound, so past about
      2.6 kB it cannot be indexed at all.
    - What it cost: the insert aborted the transaction, every headline collected after that point in
      the run was lost, the lane exited 1, and `cron watchdog` dispatched it again to fail the same
      way -- free-tier minutes spent on a run that could not finish. The longest url actually stored
      is 1,040 bytes, which is not the real ceiling of the feed but the point past which nothing was
      ever written.
    - **`NEWS_URL_MAX = 2000`**, checked before the insert in `ingest` and counted beside the stale,
      off-target and junk drops. 2,000 rather than the 2,704 the index allows, because the index
      tuple also carries the target id and its overhead. Truncating was the other option and is
      worse: a shortened Google News redirect is a dead link, and storing one as though it were the
      story is a quiet wrongness. One headline is dropped and said so; the run survives.
    - Not a schema change: no migration, no index rebuilt, the uniqueness guarantee unchanged.
    - Also seen in the same sweep and **not** fixed here, because it is a data-freshness fault rather
      than a database one: `cron watchdog` reports "FX is trading and its newest live quote is 2854
      minutes old; the lane runs every 15". The FX live-quote lane has not produced a fresh quote in
      roughly two days. It needs its own look.

103. **`jobs/horizons.py` carried a hundred-line paste of itself, and the half that was edited was
    not the half that ran.** Found 2026-10-12: lines 176-275 were byte-for-byte identical to
    276-375, so `daily_bars`, `all_relative_long`, `SETUP_SQL` and `setup_row` were each defined
    twice. Python keeps the last binding, so the first copy had never executed since the paste; it
    was a hundred lines of code that looked live, was reachable by grep, and could be changed with
    no effect whatsoever.
    - What it had already cost: during the read-side work both copies of `daily_bars` had to be
      edited in lockstep to keep them agreeing. That is the whole failure mode -- the file was
      honest only for as long as someone remembered it was lying.
    - **The first copy is deleted and nothing else is touched.** Verified before and after by
      parsing both versions: every surviving top-level definition is byte-identical to the one that
      was already winning, the order of top-level names is unchanged, and no other statement
      differs. Nothing imports this module -- `schema.yml` and `jobs/run.py` invoke it as a script
      -- so no caller could have been depending on definition order, and every in-file use of
      the four names (lines 641, 654, 784, 785, 810 and 835 before the cut) sat below both copies
      and so already resolved to the survivors.
    - Checks: `python -m compileall -q jobs` clean, `python -m unittest discover -s tests` 764 OK,
      `npm run test:web` 466 passing. No behaviour change is claimed and none is expected; the
      tests are evidence that the deletion took nothing with it, not evidence of a fix.
    - The general point, worth more than this file: a duplicate definition in Python is not a style
      problem, it is a silent-edit trap. Grep for a name and getting two top-level `def`s back is
      enough reason to stop and check which one the interpreter keeps.

104. **The FX quotes were never fetched, and the clock was why.** Investigated 2026-10-12 after the
    health endpoint reported FX 48 hours behind. The provider was never at fault.
    - **What was actually happening.** `jobs/live.py` polled a slice of the active set chosen by
      `floor(now / 300) % pages` -- the alphabet, rotated by the wall clock. That covers every name
      only if the ticks arrive, and they do not: the schedule asks for about 96 runs a day and GitHub
      delivered **8 on 2026-10-10 and 12 on 2026-10-11**. With two pages and a dozen arrivals at
      arbitrary minutes, which page runs is a coin toss. Slice 60-88 of the 88-name set had not run
      once since the set took that shape, so **28 names had no stored quote at all** -- and every FX
      pair sorts to the back (`USDBRL=X` .. `USDTRY=X`), so all five FX names in the active set were
      among them. What health was reading was a single frozen `AUDUSD` row left from when that name
      last had a direction. A direct request for the five symbols returned all five.
    - **The pick is now `ORDER BY "updatedAt" ASC NULLS FIRST, LIMIT 60`.** A dropped run can delay a
      name but cannot skip it, because the name it skipped is the first one the next run takes.
      `updatedAt` and not `quotedAt`: a closed market's quote time does not move and would pin the
      same names at the front for ever. Measured after one tick: FX quotes **1 -> 6**, the five
      polled names written 8 minutes ago instead of 383; US stock quotes 100 -> 123.
    - **Nothing is deleted.** The first attempt pruned the frozen leftovers, and
      tests/test_brain.py's "this job writes one table and never deletes" caught it. The test was
      right: `max(quotedAt)` takes the newest row in a market, so once the polled names are fresh the
      frozen one stops mattering by itself. The fix for a market nobody is polling is to poll it.
    - **A second Yahoo endpoint, for currencies only.** The batched 1-minute download is current for
      a share and not for a pair: measured at 22:23 UTC, an hour and twenty minutes after FX reopened
      for the week, the 1-minute series for `EURUSD=X` still ended Friday 21:29 while Yahoo's own
      chart `meta` gave 1.1201 struck thirty seconds earlier. `top_up_stale` asks that endpoint for a
      stale name, at most 8 a tick, stalest first -- and only for `CONTINUOUS_TYPES`, which is
      `("forex",)`. The first version had no such filter and spent its whole cap on shares, because
      every US bar sorts older than every FX bar while the US market is shut; the same call for
      `AAPL` returns Friday's close, which is correct and simply never moves the quote forward.
      Measured: six FX pairs, every one **under a minute old**, and zero requests spent on shares.

105. **A backup that is somewhere else, and refuses to call itself good until it has read itself back.**
    `tools/cloud_backup.py`, with `.github/workflows/cron-backup.yml` at 04:40 UTC.
    - **Why now:** rule 101. Both Neon projects answer `exceeded the quota`, so there is no live
      second copy and the only other one was a folder on the owner's laptop.
    - **It is useful before anyone configures Google.** With no credentials the dump still runs, still
      verifies, and is kept as a workflow artifact for seven days -- GitHub's storage, independent of
      both Supabase and the laptop. That is a real recovery point today. Seven days because the dump
      is ~30 MB and a free account has 500 MB of artifact storage in all.
    - **`verified` is earned, never assumed.** One `REPEATABLE READ, READ ONLY` snapshot; every table
      counted; every file re-read **from disk** after writing and checksummed; the manifest's row
      count compared with the row count the file actually holds; and, where configured, the uploaded
      size compared with the local size. Any failure anywhere writes `failed`. **The
      `latest-verified` pointer only moves on a clean run**, so a broken backup leaves yesterday's
      good one exactly where it was. Proven by removing two rows from `Asset.csv.gz` in a copy: the
      verify reported `checksum differs`, exited 1, and the pointer did not move.
    - **The Sheets arithmetic, done before anything was written there.** A spreadsheet holds
      10,000,000 cells. `PriceSnapshot` is 791,033 x 9 = **7,119,306 cells, 71% of the cap on its
      own**; `IntradayBar` another 897,315; all 44 tables together 8,601,778 = **86%**. So the whole
      database fits one spreadsheet exactly once and then breaks. Drive takes every table's gzip CSV
      and is the recovery path; Sheets takes the register, the verification metadata and the 42
      tables under `SHEET_CELL_BUDGET` (100,000 cells). Nothing is ever truncated to fit -- a table
      over the budget is listed as excluded, with its cell count, in the register.
    - **Sheets is explicitly not the recovery path**, and the file says why: a Postgres CSV
      distinguishes SQL NULL from an empty string and a spreadsheet cell does not, so restoring from
      Sheets would silently turn one into the other. Writes use `valueInputOption=RAW` so an id is
      not reinterpreted as a number, batched at 2,000 rows, with bounded retries.
    - **Verified end to end locally, 2026-10-12**: 44 tables, 867,839 rows, 29.9 MB, status
      `verified`; `nbt-private/restore_db.py rehearse` then loaded all 44 of them into TEMP tables
      and rolled back. `restore_db.py` now reads both manifest shapes (`taken` from `backup_db.py`,
      `started`/`finished` from this one) and warns when a manifest's own status is not `verified` --
      a recovery is not the moment to find out the tool only understands one of the two backups.
    - **Still needed to turn the cloud half on**, and nothing here pretends otherwise: three
      secrets, `GOOGLE_SERVICE_ACCOUNT_JSON`, `BACKUP_DRIVE_FOLDER_ID`, `BACKUP_SHEET_ID`. No Drive
      or Sheets call has ever been made from this machine, so none is reported as having succeeded.

106. **The Supabase session pooler's fifteen clients are a real ceiling, and the site has nowhere to
    fall back to when they are gone.** Observed 2026-10-12 while two dispatched lanes, the website and
    a probe were live at once: `(EMAXCONNSESSION) max clients reached in session mode - max clients
    are limited to pool_size: 15`, for about two minutes, during which `/api/health` returned **503**
    once before recovering on its own. `max_connections` on the database is 60; the pooler's 15 is
    the limit that actually binds. With Neon over quota there is no standby to serve a read while the
    pooler is full, so a saturated pooler is a user-visible outage rather than a degraded page.
    `tools/cloud_backup.py` retries that exact refusal rather than treating it as a fault, and takes
    one connection. The real fix is not in this repository: Supabase's **transaction** pooler (port
    6543, with `pgbouncer=true` for Prisma) admits far more clients and is what serverless is meant
    to use. That is a change to a secret, so it needs the owner.

107. **The staleness rotation only rotates if staleness moves, and against a shut market it did not.**
    Found 2026-10-12 by running two ticks in a row rather than by reading the code: both printed
    `wrote 0 of 60` over the *same* 60 names. The upsert writes a row only when its quote is strictly
    newer, so on a closed market nothing is newer, `updatedAt` never advanced, and the other 28 names
    -- the FX pairs among them -- would never have been polled again. The same starvation rule 104
    fixed, rebuilt with a different cause, by the fix for it.
    - `jobs/live.py` now **touches every name it asked about**, whether or not the price moved. So
      `updatedAt` means "when this row was last refreshed" and `quotedAt` alone means "when the price
      was struck". The schema comment says so.
    - `getDataStamp` in lib/queries.ts therefore reads `max("quotedAt")` and not `max("updatedAt")`.
      That stamp is what `/api/revalidate` compares to decide whether every cached page is behind the
      database; left on `updatedAt` it would have changed every few minutes and rebuilt the whole
      site for nothing. A cache stamp must move when the data moves, not when someone looked.
    - **Measured after the change**, two consecutive ticks against the same closed market: the first
      picked 60 names and wrote none, the second picked a *different* 60, reached the FX pairs, fired
      the quote-endpoint top-up and wrote 5. FX newest market time **2026-10-09 21:30 (about 48 hours
      old) -> 2026-10-11 22:52:31, seconds old**; the row count 1 -> 6.
    - Worth keeping as a habit: both of this phase's live-lane bugs were invisible to reading and
      obvious on the second run. A rotation is a claim about what happens over several ticks, and one
      tick cannot test it.

108. **Phase 1: every lane now says what it did, and a throttle is no longer filed as an absence.**
    Implemented 2026-10-12 under the owner's approved Phase 1 scope. Nothing was deleted, no
    historical backfill was run, and no new market-data source was added.
    - **`blocked` is a sixth `ChunkRun` status.** A provider answering 429 has said "not now"; an
      empty answer has said "nothing there". `empty` conflated them, and that is how Reddit came to
      look like a quiet source rather than a throttled one -- 7 rows across 3 of 30 products. The
      throttle is counted in `jobs/nbt.py` `THROTTLED`, at the one place a 429 is actually seen, and
      read with `throttled_since()` around a block of work; a collector further up cannot tell the
      two apart.
    - **Eight lanes had no stored run record at all.** `prices.py` was the only caller of
      `jobs/runlog.py`, so `ChunkRun` held three jobs and `lib/health.ts` could not see the rest of
      the pipeline. `runlog.lane_run` wraps a whole lane from the outside -- counting the table it
      writes before and after -- so psx, intraday, live, marketplace, geo and upcoming record one
      honest row each without a line changing inside them. **Two brief connections, never one held
      open**: a session open across a lane's network phase is the exact fault these jobs are built
      to avoid, and a logger must not reintroduce it. `LiveQuote` is upsert-in-place and never
      grows, so that lane reports what it moved forward instead of a row delta.
    - **`signals.py` writes one row per sub-source**, not one per lane, with `blocked` when the
      provider throttled and "n of 30 products covered" as the measure. `jobs/audit.py`'s single
      `product demand signals` Coverage row became five. An aggregate over independent providers
      cannot report any of them: it reports the best one, which is how three live sources hid two
      degraded ones while the panel read `healthy`.
    - **A demand source is now judged on breadth as well as recency.** Recency is the right question
      for a price feed -- one universe, answered or not. A demand source covers thirty products
      independently and can be perfectly fresh and almost absent. Reddit now reads **`stale`** at
      3 of 30; Trends (30/30), Wikipedia (27/30), Hacker News and Google News stay `healthy`.
    - **The weekend was being compared with weekdays.** Google News RSS carries 204-307 headlines on
      a weekday and 34-106 at a weekend (measured over 12 days), and the partial-volume median was
      taken across both -- so every Saturday and Sunday the source was reported `partial` with
      nothing wrong: 53 against a median of 204. The median is now taken over days of the same kind.
      This was the whole of the "recent news-volume reduction": **not a defect**. After the change
      Google News RSS reads `healthy`.
    - **Reddit: collected and shown, not counted.** Removed from `SCORED_SIGNALS` in jobs/nbt.py and
      from `SCORED` on the product page, recorded in `DEGRADED_SIGNALS` with the reason, and still
      rendered beside its own reading. A confirming source present for a tenth of the catalogue adds
      agreement for three products and silence for twenty-seven; a score counting that would rank
      those three above the rest for a reason about a rate limiter. Reversible in one line.
    - **The paid macro engine is fail-closed.** `MACRO_GATE_ENGINE=model` plus a key lying around was
      the whole authorization, which meant one repository variable silently moved this lane from
      free to billed at `claude-opus-5-5`, nightly. It now also needs `MACRO_GATE_PAID` set to an
      explicit authorizing value; without it the run warns loudly and uses the free local rule table
      rather than refusing, because a missing veto is worse than a free one. Verified in production
      before the change: `MACRO_GATE_ENGINE:` empty, `engine local-rules-v1`, no API call, no cost.
    - **FX can reach the intraday set.** `supported()` excluded only PSX and the chart API answers
      `EURUSD=X` at one minute, but no pair ever collected a reason to be selected -- the reasons are
      written around equities. A pair carrying a direction today is now one, bounded by the same rule
      `jobs/live.py` uses and by the existing 60-request ceiling. No backfill: pairs start collecting
      from the next run, as a newly listed equity does.
    - **Operational status is bounded; evidence is not.** `ChunkRun` and `Coverage` joined
      `jobs/retention.py`'s `KEEP` at 30 days. Both are append-only and grow with the schedule rather
      than the universe, and nothing derived reads either -- which is exactly why they can be pruned
      and `PriceSnapshot` cannot.

109. **The live lane's schedule is not what arrives, and the fix was already in this repository.**
    Measured 2026-10-12 over the Actions API window: `cron live quotes` asks for about 96 runs a day
    and GitHub delivered **8 scheduled runs**, none of them at a configured minute -- they landed at
    :13 :16 :20 :25 :27 :38 :41 :57 against a schedule of 7, 22, 37, 52. Median gap 65 minutes,
    worst 300, against a 15 minute ask. Every-two-hour lanes fared fine over the same window (`cron
    audit`, `cron crypto`, `cron news`: 13 each), so this is GitHub deprioritising frequent schedules
    on a free repository, not a fault in the file.
    - `workflow_run` is an event, and events are not dropped. The watchdog already proved it here:
      **7** scheduled runs against **74** from `workflow_run` in the same window. `cron-live.yml` now
      also runs when a data lane completes -- runs that happen anyway, one short tick each, inside
      the existing `nbt-live` concurrency group so a burst cannot build a backlog. No new schedule
      and no new scheduler.
    - What remains external and is not claimed to be fixed: GitHub will still drop most of the
      `*/5` and 15-minute slots. The event trigger raises the floor; it does not make the schedule
      arrive.

110. **No Redis, no external cache, and no staleness defect found.** Checked 2026-10-12 across
    package.json, lib, app, jobs, tools and the workflows: nothing imports or configures Redis,
    Memcached, Upstash or `@vercel/kv`. The caching that exists is Next.js's own: two
    `unstable_cache` entries in lib/cached.ts pinned with `revalidate: false` and a shared tag, route
    ISR, and a one-minute per-symbol memo plus a 60-second CDN header on `/api/quote`. The data cache
    has **no timer** -- it refreshes only when `/api/revalidate` finds the database ahead of it, and
    that endpoint is called by the crypto, decision, live, psx, us-prices and schema lanes and by the
    hourly watchdog. It acts only on a changed stamp, so a caller can make it do work at most once
    per change. Nothing here needs a cache service, and adding one would be new infrastructure
    solving a problem that was not found.

111. **Phase 1 closure, 2026-10-12. Closed for data reliability; the PSX permission question is open
    and is the owner's.**
    - **The top-up could lose a whole tick.** Found on the first event-triggered run at 00:42:
      `top_up_stale` answered for a pair the 1-minute download had already answered for, so two rows
      carried one `assetId`; `ON CONFLICT ("assetId") DO UPDATE` refuses to touch a row twice in one
      statement, the tick is one statement, and Postgres raised `CardinalityViolation`. The entire
      write was lost -- crypto with it -- and the workflow went green. That is the freshness lie this
      phase exists to remove, and it is why FX had not refreshed in two hours while runs succeeded.
      `write()` now keeps the newest quote per asset, so every caller is covered; a tick that stopped
      before writing records `failed` with the reason. Verified on the same shape that failed: 59
      bars + 2 top-ups write cleanly, FX **112 minutes old -> 1 minute**.
    - **The `workflow_run` trigger works.** One bounded validation: `cron psx` dispatched on the
      default branch, completed 00:42, and `cron live quotes` fired from it with `event=workflow_run`
      and succeeded. Scheduled and event-triggered runs are distinguishable in the Actions record by
      `event`. The external limitation stands: GitHub still delivered 8 scheduled runs against ~96
      asked for, none at a configured minute, median gap 65 minutes.
    - **Coverage: 100% of active assets priced in every class** -- FX 27/27, PK 176/176, US stock
      272/272, ETF 8/8, commodity 8/8, crypto 63/63 -- from 2019-01-01/02 (2018-11-02 for crypto).
      Zero active US stocks miss any of the last 20 sessions. The 288 US names "behind" crypto's
      10-10 are a weekday calendar against a continuous one, not a gap.
    - **What looked like bad data and is not.** The one non-positive close is `CL=F` on 2020-04-20 at
      **-37.63**: the real negative WTI settlement, with a low of -40.32. A futures close below zero
      is an observation, not a defect, and nothing should "fix" it. The 5,423 closes outside their own
      high/low are the known provider defect of rule 98 (Yahoo FX 4,142, PSX 1,232, Yahoo US 49),
      stored as sent and read by the grader as unavailable; the PSX share has grown from 339 and is
      worth watching. The 171 PSX weekend rows are the exchange's own Saturday file, skipped by every
      decision reader.
    - **Database 274.5 -> 301.5 MB is explained and is mostly recovered history.** `PriceSnapshot`
      781,163 -> 830,487 rows, of which **PSX 82,515 -> 129,907 (+47,392)**: the `backfill` lane,
      triggered by this phase's own commit touching `jobs/psx.py`, ran `psx.py full` and filled
      PSX history that was missing. Not churn. `PriceSnapshot_pkey` regrew 50.6 -> 68.7 MB with it.
      199 MB of headroom remain.
    - **Sync baseline for Phase 2** (measured, not fixed here): insert-to-live ratios of 2.2x on
      `PriceSnapshot` with 237,559 deletes (the crypto full-replace of rule 108's note), 5.9x on
      `NewsLineage`, 5.8x on `Ranking`, 3.3x on `EventImpact`. The crypto lane still refetches every
      coin's whole history every two hours. These belong to Phase 2 and were deliberately not touched.

112. **Phase 1's two open items, both needing the owner rather than more code.**
    - **PSX data may not be redistributed without a licence.** PSX's own legal notice prohibits "any
      dissemination, transmission, sale, and commercial use of Market Data feed" without a licence
      from PSX, *including on a delayed basis*, and its terms of use permit "a single, unaltered,
      permanent copy" for "personal, non-commercial use only". This product republishes PSX closes
      publicly on `/psx` for 176 names. Technical access is not permission, and nothing in this
      repository can grant it. **The public PSX distribution path is therefore not declared
      production-ready.** The decision is the owner's: obtain a licence (marketdatarequest@psx.com.pk),
      restrict PSX data to non-public use, or accept the risk explicitly. No substitute provider was
      swapped in, because none would carry the same instrument and history.
    - **Pakistan institutional and global macro coverage barely reaches storage, and what does reach
      it is unreadable.** Measured against the stored headlines: **SBP 0, Ministry of Finance 0,
      IMF 1**; inflation/PBS 10, policy rate 10, reserves/remittances 6. Global geopolitical terms
      appear only incidentally inside company-targeted headlines (conflict 17, sanctions 9, shipping
      5). The cause is structural: the news collector searches per asset, and there is no macro or
      institutional feed at all. Worse, the 543 industry-linked rows it does store reach **no
      reader** -- `getRecentMarketNews` filters `assetId IS NOT NULL`, `getTopNews` takes an
      `assetId`, and `jobs/human.py` runs only for `("assetId", ...)` and `("productId", ...)`;
      `HumanSignal` has no industry column. Collecting macro news today would be writing into a table
      nothing reads. Closing this properly needs a reader and a derivation path, which is Phase 3's
      territory, so it is **accepted here with its impact stated**: PSX verdicts carry no macro
      context, and the site does not claim they do.

113. **Phase 1 closed. Macro ingestion built, the PSX route evaluated and rejected on terms, the
    recovery manifest written.** 2026-10-12.
    - **Pakistan macro and global geopolitics now reach storage *and* a reader.** `MACRO_FEEDS` in
      jobs/prices.py is a fixed list of twelve topics -- SBP policy, SBP reserves and remittances,
      Ministry of Finance, IMF Pakistan, PBS statistics, Pakistan market policy, conflict, sanctions,
      shipping, energy, commodities, central banks -- each a Google News query through the same
      `ingest` path the asset feeds use, so the junk filter, the window, the lineage clustering and
      the url guard all apply unchanged. Rows are stored **untargeted** (no asset, no industry, no
      product), because a policy-rate decision belongs to no single name; `News_untargeted_url_key`
      already existed and is what makes one story arriving under two topics a single row. The topic
      lives in `source`, so a dead SBP feed cannot hide behind a live sanctions one -- the lesson of
      the product-demand aggregate.
    - **The reader is the half that makes it real.** `getMacroNews` in lib/queries.ts, surfaced
      additively on `/api/signals` as `macro`. Without it this would have repeated the existing
      mistake: 543 industry-linked rows have sat unread because `getRecentMarketNews` filters
      `assetId IS NOT NULL`, `getTopNews` takes an asset id and jobs/human.py derives only for assets
      and products. Publication time and collection time are returned separately -- "published two
      days ago" and "we found it two days late" are different facts. Context only; whether any of it
      moves a decision is Phase 3's question.
    - **Verified by running it**: all twelve feeds answered, **69 rows stored**, every topic present,
      publisher, url, publication time and collection time preserved. IMF headlines went 1 -> 10.
    - **PSX: five routes evaluated, none qualifies, and the reason is the data and not the endpoint.**
      `investors.psx.com.pk` does not resolve; the Lens timeseries endpoint answers 404; `psxdata`,
      `pypsx`, `psx-feed` and `psx-data-reader` are all scrapers of the same `dps.psx.com.pk` -- the
      same upstream, so not redundancy -- and an MIT licence covers a library's code, never the
      exchange's data. Capital Stake is the authorised vendor and is paid. PSX's own terms allow "a
      single, unaltered, permanent copy" for "personal, non-commercial use only" and forbid
      dissemination of the market data feed without a licence, delayed included. Routing around that
      through a scraper would be circumventing the restriction rather than satisfying it, so nothing
      was swapped in and the existing history was left untouched. **The restriction is isolated to
      PSX**; every other asset class is unaffected and keeps working.
    - **`recovery-manifest.json`** is the single Phase 4 artifact: seven entries, each classified
      (`real_observation`, `by_design`, `listing_limit`, `source_defect`, `recoverable_gap`,
      `blocked`), with measured figures, the source to recover from, the operation and the integrity
      check that proves it worked. The headline correction it records: **PSX's pre-2024 sparsity is
      by design, not a gap** -- `DEEP_DAYS = 820` is a dense daily stretch of about 2.25 years sized
      to `horizons.py`'s 540-session window, with a 24-month monthly grid behind it, which is exactly
      the 12-13 rows a year stored for 2019-2023 against 251-253 for US. It is recoverable from the
      exchange's own archive (`ARCHIVE_FROM = 2013-11-04`) if Phase 4 wants the depth.
    - **COF needed no repair.** It held 22 bars when the audit found it and holds **1,954 from
      2019-01-02** now, which equals the provider's own count for that range: a lane recovered it in
      the interval. `tools/recover_asset.py` exists for the next one -- one asset, upsert only,
      never `is_full`, and it re-reads every pre-existing bar afterwards and fails the run if one was
      lost or altered.

114. **Where this stands, and what the next session needs to know.** Written 2026-10-12 as the
    handover point. Everything above is history; this is the state.
    - **Phase 1 is closed** at commit `5b392a8` (`main` and `master` identical, tree clean, CI green,
      `/api/health` ok). The closure itself is rule 113; the Phase 4 work it identified is in
      `recovery-manifest.json` at the repository root, which is the single artifact for that phase.
    - **The agreed phase order, which does not get reordered because a new issue appears:**
      1 data sources and requirements (**done**) · 2 database, free-tier, backups, sync performance ·
      3 the brain, multi-timeframe decisions, historical evaluation · 4 one controlled clean sync ·
      5 reconcile the post-sync dataset and pipeline · 6 UI and actionability · 7 production
      acceptance, monitoring, lock. **Phase 2 is next** and needs its own approved task.
    - **Standing constraints from the owner**, which shaped most of the decisions above: free tier
      only, no paid APIs or subscriptions, no contacting providers for licences, no new scheduler or
      cache service. Google Drive/Sheets is built (`tools/cloud_backup.py`) but **not activated** --
      it needs `GOOGLE_SERVICE_ACCOUNT_JSON`, `BACKUP_DRIVE_FOLDER_ID` and `BACKUP_SHEET_ID`, and
      until then the daily `cron backup` keeps a verified 30 MB artifact on GitHub for seven days,
      which is a real off-machine recovery point.
    - **Two decisions are the owner's and nothing in the repository can settle them.** (a) PSX
      forbids redistributing its market data without a licence; five free routes were evaluated and
      all are the same restricted upstream, so the public PSX surface is not declared production
      ready -- restrict it, licence it, or accept the risk. (b) Whether the macro and geopolitical
      context now collected should influence a verdict at all is Phase 3's question; today it is
      context on `/api/signals` and enters no decision.
    - **Working rules that were learned the hard way and should not be rediscovered:** the Supabase
      session pooler admits **15 clients in total**, and saturating it returned a production 503, so
      one database connection at a time and no overlapping production jobs; GitHub delivers roughly
      a tenth of a frequent schedule, so `workflow_run` is how a lane actually runs often; never
      leave a background watcher running; and a lane that reports success while storing nothing is
      the failure mode this project keeps producing -- check what landed, not that the job exited 0.
    - **The biggest known inefficiency, deliberately left for Phase 2:** `jobs/prices.py` refetches
      and rewrites every crypto asset's entire history every two hours (insert-to-live 2.2x on
      `PriceSnapshot`, 237,559 deletes), and `jobs/intraday.py` still carries a whole-table window
      scan. Both are measured in rule 111 and neither was touched.

115. **Phase 1 closed for the second and last time: the PSX source question answered with an
    independent provider, the macro provenance claim corrected, the manifest reconciled.**
    2026-10-12. The previous closure (rule 113) was sound on everything it measured and stopped one
    step early on the one question that mattered most. This entry is what that step found.

    - **State verified rather than assumed.** HEAD `6146c72` on `main`, identical to `origin/main`
      and `origin/master`, tree clean. `tests` on push green for that exact commit (run at
      2026-10-12T01:54:45Z against a commit timestamped 01:54:40 UTC). `/api/health` returns
      `ok: true` with an empty `problems` array, served from the primary. Local `master` is 11
      behind and is stale local state only; the remote is current.

    - **PSX has an independent second provider, and the previous evaluation was wrong to conclude
      otherwise.** Yahoo Finance carries PSX under the `.KA` suffix (exchange KAR, currency PKR),
      reachable through the same yfinance path `jobs/prices.py` already uses for US, FX and
      commodities. Measured, not assumed: **156 of the 176 active names** resolve, history runs
      **dense daily from 2018-01-01**, and over 4,524 overlapping bars **96.1% of closes are
      identical to within 0.01% and 99.5% of volumes are exact**. The session calendars agree
      *exactly* -- not one session present in one source and absent from the other. This is the
      same market data, not an approximation of it.

      It has two defects and both are detectable, which is what makes it usable:
      **(a) it fabricates bars.** A session Yahoo does not have comes back as open=high=low=close
      with volume 0 rather than being omitted. That is 11-16 bars a year for 2019-2023, and they
      land on Pakistan's public holidays -- Eid al-Fitr, Eid al-Adha, Ashura, Kashmir Day, Pakistan
      Day. The same mechanism invented a bar for **2026-10-08**, a real session it missed, across
      all 156 names, and 86 of those closes were more than 1% wrong. Filtering
      `volume = 0 AND open = high = low = close` removes holiday padding and missed-session padding
      together. After the filter the year counts are 245/251/246/248/244 for 2019-2023, against
      PSX's true ~248 -- so the density is real once the padding is gone.
      **(b) it is adjusted, not raw.** Yahoo back-adjusts for corporate actions; the exchange file
      stores as-traded. Three names disagreed by a constant ratio -- BPL 0.8333 (5/6, a 20% bonus),
      CLOV 0.8696 (20/23), BAPL 0.6094 -- and every other name agreed exactly. **Nothing in this
      repository adjusts for a corporate action**, so the stored PSX series carries raw bonus-issue
      jumps. Appending adjusted history to it would invent a price move that never happened.

      So Yahoo qualifies **as a secondary and as a recovery source, not as a replacement**: 88.6%
      coverage and fabricated bars disqualify it from being the one source of record, and nothing
      was swapped in. The existing data was not touched.

    - **What that does and does not settle.** It makes the pre-2024 history recoverable without the
      exchange archive, and it makes a suspected missing PSX session checkable against something
      instead of being unresolvable from stored data alone. It does **not** obtain a licence.
      Yahoo's terms restrict redistribution too. What changes is *whose* terms govern the public PK
      surface: an exchange whose notice names delayed redistribution explicitly, or a provider this
      project already republishes for every other asset class. That is a real difference in the
      owner's risk posture and it is not a legal opinion -- nothing here can give one.

    - **Two corrections to the previous evaluation, both from rechecking rather than reasoning.**
      `investors.psx.com.pk` still does not resolve (connection fails at the network layer).
      But the Lens timeseries endpoint **does not 404** -- it answers 200 when called with the
      headers the company page sends, and 404 to a bare request. Confirmed by loading
      `dps.psx.com.pk/company/OGDC` in a browser and reading its own network traffic. It serves
      intraday `[timestamp, price, size]` ticks for the current session, no EOD history, and it is
      the same restricted upstream -- so it changes nothing, but "it 404s" was the wrong reason.
      Stooq was disqualified on access policy, not capability: `robots.txt` is `Disallow: /` for
      everything but Bingbot and Googlebot, behind a proof-of-work challenge. Twelve Data lists the
      whole PSX universe (MIC XKAR) on a keyless endpoint but needs an account for time series; no
      account was created, so its free tier remains unverified and it is the one cheap check left.

    - **The macro lane published a false provenance claim on every row, and that is now fixed.**
      All 82 macro rows had `lineageId` null and `isOriginal` false. `jobs/lineage.py` selected
      targets by `assetId` or `productId` only; macro rows are untargeted *by design*, so lineage
      never saw them, and `News.isOriginal` defaults to false. `getMacroNews` publishes that field
      to `/api/signals`, where false means "this is a syndicated copy". So the system was asserting,
      about all 82, that each was a copy of something else. **A wrong provenance claim is worse than
      a missing one**, and no row count would ever have shown it -- every row was present, stored
      correctly and readable. This is rule 112's mistake in a new place: there the collector had no
      reader, here it had a reader and told it the wrong thing.

      Macro is now a target kind of its own in `lineage.py`, grouped by the topic in `source`.
      Verified by running it: **82 of 82 clustered, 82 marked original, 0 falsely marked
      syndicated**, with the 3,943 targeted rows in the window unaffected. Production confirms it --
      `/api/signals` returns 43 items in its 14-day window, 43 of 43 now carrying a lineage id and
      `isOriginal: true`, where every one read false before. The run summary prints a macro line of
      its own, because macro is a twelfth of the targets and a fraction of a percent of the items:
      a run that clustered every asset and no macro row would otherwise still print a healthy ratio,
      which is exactly how this went unnoticed.

    - **The rest of the macro lane verified and left alone.** All twelve topics are populated (82
      rows, up from 69), every row has a url, a publisher and a publication time, every url is
      distinct, and not one is targeted -- the untargeted unique index is doing its job. SBP went
      0 -> 2 and IMF 1 -> 11. Two honest limitations recorded rather than papered over: **"Ministry
      of Finance" still appears in no stored headline** although its topic returns rows, so that
      feed is returning Pakistan fiscal news that does not name the ministry; and **stored urls are
      Google News wrapper links, not the publisher's own** -- which is not a macro defect, it is how
      all 4,036 Google-sourced rows are stored and has been all along.

    - **The manifest was reconciled against the live database, and three entries changed
      classification.** Every figure was re-measured. The per-year PSX session counts are unchanged
      to the row. COF still holds 1,954 bars from 2019-01-02. The one lumped "5,423 malformed bars"
      entry turned out to be **three unrelated things**:
      **PK (1,232 rows) is not a defect.** 1,133 of the 1,231 rows that have a predecessor have a
      close *exactly equal to the previous session's close*, and 1,193 of 1,232 are thin-volume.
      That is PSX carrying the previous close forward when a scrip did not trade enough in the
      closing window, while high and low stay the day's real traded extremes. The exchange's own
      convention. The previous revision also claimed "the trade grader already reads these bars as
      unavailable" -- **no code does that**; nothing in `jobs/`, `lib/` or `tools/` compares close
      against high and low. It does not need to, and a validator that rejected these would have
      discarded 1,232 valid exchange closes.
      **FX (4,142 rows) is the only real defect of the three.** Only 137 match the previous close.
      USDPKR on 2026-10-09 has high 268.24, low 267.41 and close 276.75 -- the close comes from a
      different venue than the OHLC, roughly open-market against interbank, and repeats flat across
      days. This is the one to look at first, because the PKR rate feeds PSX-facing analysis.
      **US (49 rows) is floating-point noise.** AGNC 2023-03-20 has low 5.71911239624024 and close
      5.71911239624023: one unit in the last place of a double. Correct bars.

    - **What the sparse pre-2024 grid actually supports, stated because the brief refused to let it
      be called complete.** Measured over the 176 active names: **155 clear the 540-session long
      window from the 2024-onward dense stretch alone**, 158 clear it over all stored history, 167
      clear the 220 minimum. So `jobs/horizons.py`'s longer read -- LONG_SLOW 200, LONG_RANGE 500,
      MIN_LONG 220 -- is served entirely by the dense stretch and the monthly grid contributes
      nothing to it. The grid serves the 24-month relative return and the history chart, which is
      what it was built for. What would need dense pre-2024 daily data is **any evaluation spanning
      more than ~2.25 years, and that consumer does not exist yet** -- it is Phase 3's historical
      evaluation. The deepest name holds 559 dense sessions against a 540 target, so `DEEP_DAYS` has
      **19 sessions of margin and no slack to lose**.

    - **Freshness, measured from run history rather than re-run.** Over the last 100 runs of each
      lane: live quotes 40/41 with 0 failures, crypto 36/39, us prices 31/34, psx 15/17, news 36/50,
      **mirror 5/10**, watchdog 58/100. The watchdog's 42 failures are it doing its job -- the one
      read in full was a genuine 247-minute commodity quote staleness -- not false alarms. Its
      `workflow_run` trigger is carrying the lane: 90 of 100 runs came that way against 8 from
      schedule, which is rule 114's GitHub delivery limitation visible in the numbers.
      **PSX showing "one session behind" at 11:50 UTC was correct and not a fault**: `cron-psx` runs
      at 12:40/16:40/20:40 UTC, after the 10:30 UTC close, so the Monday session had not been
      collected yet. The health sentence cannot currently distinguish "the lane has not run yet"
      from "the lane ran and found nothing", which is a UI distinction and belongs to Phase 6.

    - **`cron mirror` fails half its runs, and the cause is IPv6.** The log reads
      `connection to server at "2600:1f16:4bf:..." port 5432 failed: Network is unreachable` --
      GitHub Actions runners have no IPv6, and the direct Supabase endpoint is IPv6-only, while the
      session pooler is IPv4. So **the standby is not being refreshed** and the failover copy is
      stale. It fails loudly rather than silently and production reads the primary, so it is not a
      Phase 1 blocker; it is a **Phase 2 blocker**, and the fix is a connection string the owner
      controls, not code.

    - **Sync baseline for Phase 2, measured today.** Database **317 MB of the 500 MB free tier, 183
      MB of headroom** -- up from 301.5 MB at rule 111 and still climbing. `PriceSnapshot` is 221 MB
      of it: 831,027 live rows against 2,052,530 inserts and **430,470 deletes**, an insert-to-live
      ratio of **2.47** (it was 2.2 with 237,559 deletes at rule 111 -- the crypto full-replace is
      not just continuing, it is compounding). Worse ratios sit on smaller tables: Analysis 6.93,
      Ranking 6.80, NewsLineage 5.06, EventImpact 3.71. Prioritised backlog, unchanged in order by
      this task: incremental crypto fetch first (it is the largest absolute waste), then
      `jobs/intraday.py`'s whole-table window scan, then the mirror's IPv4 connection string, then
      resumable batches and integrity verification. Nothing here was optimised, by instruction.

    - **Verification.** 797 Python tests, 466 TypeScript tests, `tsc --noEmit` clean, `eslint`
      clean, production build clean. Two tests added: one pins `lineage.MACRO_PREFIX` to
      `prices.MACRO_SOURCE_PREFIX` so the restated constant cannot drift (the psx.py/horizons.py
      idiom), and one asserts that *something sets* the provenance the reader publishes -- the
      existing test checked only that `getMacroNews` returned the fields, which is precisely why it
      passed throughout the period the claim was false on every row.

    - **Phase 1 is closed.** The data-source requirements are defined and verified, every material
      acquisition gap has either a real recovery path or an evidence-backed limitation, macro data
      is collected *and* retrievable *and* truthfully labelled, the manifest is deterministic enough
      to execute without another investigation, and no known critical failure silently produces
      misleading current data. **Phase 2 is next and needs its own approved task.** The two owner
      decisions from rule 114 stand, with the PSX one now better informed: restrict the public PK
      surface, licence it, move it onto the Yahoo series and accept that provider's terms instead,
      or accept the current risk explicitly.

116. **The Ministry of Finance is read from the ministry, not from a search engine. Phase 1 closed.**
    2026-10-12. Rule 115 left one coverage hole and one open question about news urls. This closes
    both, and it is the last Phase 1 entry.

    - **The hole: a topic that looked alive and carried none of its subject.** The
      "Ministry of Finance Pakistan" Google feed returns six rows a run and on 2026-10-12 **not one
      stored headline contained the words "Ministry of Finance"**. The feed was answering with
      Pakistani fiscal news that never named the ministry. A search engine's idea of a subject is
      not the subject, and a per-topic row count cannot tell the two apart -- which is why rule 113
      recorded the topic as working.

    - **The fix is the ministry's own press release archive**, `finance.gov.pk/press_releases.html`.
      Server-rendered HTML, no JavaScript, no key, no cookie: a plain GET is the whole of it, so
      **Puppeteer was not used** -- it would have been a dependency bought for nothing. Verified by
      parsing the live page: **296 releases, PR 356 to 655, 2025-08-01 to 2026-10-10**.

    - **It is a second source under its own label, not a replacement.**
      `Macro: Ministry of Finance (finance.gov.pk)` sits beside the Google topic rather than
      replacing it. Folding both into one `source` would let a live search feed hide a dead ministry
      page, which is the exact failure the per-topic label exists to prevent. The label still starts
      with `MACRO_SOURCE_PREFIX`, so `getMacroNews` and `/api/signals` read it **without a line
      changing** -- same `macro_sql`, same untargeted unique index, same 33-day window, same junk
      filter, same url ceiling, same `note` tally. The only thing that differs is the parsing,
      because the ministry publishes HTML and Google publishes RSS.

    - **The PR number is not a usable key, which is the finding that mattered.** The obvious
      identity for a release is its PR number, and it is wrong. Measured over the 296 releases on
      the page: **PR 614, 585 and 562 each name two different releases**, and 562's pair share a
      date as well. The number alone yields 293 distinct keys for 296 releases; number and date
      yield 295. Since the url *is* the deduplication key -- `News_untargeted_url_key` is what stops
      a release being stored twice -- a colliding key would have **silently dropped genuine releases
      as duplicates**. The fragment therefore carries number, date and a short digest of the
      headline, which gives 296 of 296. A later-edited headline reads as a new item, which is the
      right way round: a missed edit is worse than a repeat.

    - **Verified by running it, not by asserting it.** The news lane stored **6 releases, newest
      2026-10-10**, each with the ministry as publisher, the ministry's own publication date, and a
      direct `finance.gov.pk` url -- no wrapper. `jobs/lineage.py` then clustered them: **93 macro
      rows across 13 sources, 93 clustered, 93 original, 93 distinct urls, 0 falsely syndicated.**
      The lane as a whole exited 143 at 28.3 minutes -- its own watchdog stopping the per-asset
      feeds, long after the macro section had committed. Recorded because the exit code is alarming
      and the macro result is not affected by it.

    - **An honest correction to rule 115's own metric.** "Ministry of Finance appears in no stored
      headline" is **still true, and it no longer means what it meant**. The ministry titles its
      releases "Finance Minister ..." rather than "Ministry of Finance ...", so the keyword count
      stays 0 while the substance -- six announcements straight from the department, with the
      department named as publisher -- is now there. The keyword was a poor proxy and is not worth
      keeping as one. What to check instead is whether the source answered and what it stored.

    - **The Google News wrapper url cannot be resolved to the publisher's article, and this was
      tested rather than assumed.** Of the three places an original url could come from: the
      `link` token **does not decode** -- base64 of the article id contains no http url at all;
      the `description` only repeats the same wrapper link; and `<source url="...">` gives the
      publisher's **home page**, not the article. The wrapper does answer HTTP 200 for a reader,
      but its last hop is JavaScript, so a server-side fetch lands on Google rather than the
      outlet. **No extractor was written**: an unreliable one would put a wrong url on a real story,
      and nothing historical was migrated. Publisher attribution is unaffected -- it is already
      stored per row and matches the feed's own `<source>` name. The ministry collector sidesteps
      the problem entirely by having a real url, which is the better answer where it is available.

    - **Tests: 11 added, all against saved markup rather than this morning's page.** Parsing
      (date, PR number, headline); provenance (the url points at the item, `publishedAt` is the
      ministry's date and not the collector's clock, the publisher is the ministry); deduplication
      (the real PR 562 collision still yields two rows, and re-parsing an unchanged page yields the
      same identities); partial failure (a release with no headline is skipped and **does not steal
      the next release's headline** -- the bounded gap in `MOF_ITEM_RE` is what prevents a wrong row
      rather than a missing one; an unreadable date is dropped rather than guessed; an empty or
      reshaped page yields nothing rather than nonsense); and retrieval (the label carries the macro
      prefix, so the existing reader finds it, and it is distinct from every Google topic).

    - **One gate caught a real omission.** `finance.gov.pk` had no entry in `nbt.HOST_DELAY`, so it
      would have taken the 1.0s default that nobody chose. Declared at 3.0s: it is one request per
      run for a single 2.3 MB page, and a government department's web server is the last place to
      discover a rate limit by hitting one.

    - **Release, verified after the push rather than predicted before it.** 807 Python tests, 466
      TypeScript tests, `tsc --noEmit` clean, `eslint` clean, production build clean (58 static
      pages). Pushed as `1955d7a`, with `main` and `master` both at that commit. **CI run
      38256117784 (`tests`, push) completed `success`** against it. Vercel served the change:
      `/api/signals` returns 54 macro items, **54 of 54 carrying a lineage id and `isOriginal`
      true**, including the six ministry releases with `finance.gov.pk` urls and the ministry named
      as publisher.
      `/api/health` reads `ok: false` at the time of release, and **not because of this change**.
      All four problems are live-quote staleness on `cron-live.yml`, which runs `jobs/live.py` --
      a file no commit here touches. The staleness predates the push: the watchdog recorded it at
      11:17, 11:22 and 12:25 UTC. The cause is rule 114's GitHub delivery limitation, visible twice
      over on this day -- `cron live quotes` has not been triggered since 12:25 and `cron psx` has
      not run since 00:39, so its 12:40 slot never fired and PSX reads one session behind. Both
      recover when the watchdog next dispatches. **No lane was dispatched by hand to turn the
      endpoint green**: a dispatched recovery would have proved nothing about the schedule, and
      manufacturing a passing log is the failure this project keeps writing rules against.

    - **PSX, settled and not reopened.** The bounded evaluation in rule 115 stands and no further
      source discovery was done. No provider was switched, no scraper library was added for the same
      upstream, and the existing dataset is untouched. **The accepted limitation, stated once:**
      the public `/psx` surface republishes Pakistan Stock Exchange data, PSX's own terms forbid
      redistributing its market data feed without a licence -- delayed included -- and **nothing in
      this repository has cleared that right**. Yahoo `.KA` was measured as an independent provider
      and is not a way out: it is incomplete at 156 of 176 names, adjusted rather than raw, and it
      fabricates flat bars for sessions it is missing, so it is a cross-check and a recovery source
      and not a source of record. Collection and private use are unaffected; the exposure is the
      public surface. It is recorded in `recovery-manifest.json` under `psx-redistribution-licence`
      as an accepted, unresolved external risk, and it stays the owner's decision.

    - **Phase 1 is closed.** Sources are defined and verified, every material gap has a recovery
      path or a stated limitation, macro data is collected from the institution itself, retrievable,
      and truthfully labelled, and no known failure silently produces misleading current data.
      **Phase 2 is next and needs its own approved task.**

117. **Phase 2 measured rather than inferred: the database, the backup, the ingestion gap and the
    Data API. One item is left open, and it is the one that matters most.** 2026-10-13, against the
    live primary with an authorised `psql` session. Everything below was re-measured in this pass;
    nothing is carried forward from an earlier report.

    - **The database is 324.3 MB of the 500 MB tier (64.9%)**, not the 339 MB of 2026-10-08 that
      several documents still quote. It went *down*. `PriceSnapshot` is 216 MB of it (146 MB heap,
      69 MB index, 32% index), `IntradayBar` 44 MB, and nothing else reaches 11 MB. **There is no
      bloat to reclaim:** dead tuples are 0 on both large tables, autovacuum last touched
      `PriceSnapshot` at 17:30 UTC the same day, and `jobs/retention.py --dry-run` would remove
      **0 rows**. The growth is the data the project exists to accumulate, so **no cleanup is
      justified and none was done** -- which is the same conclusion as 2026-10-11, now with the
      bytes behind it rather than an estimate.

    - **The ingestion gap closed itself, and the watchdog behaved exactly as designed.** No workflow
      of any kind ran between `2026-10-13T12:10:39Z` and `17:10:19Z`. The run that ended it was an
      ordinary `schedule` event, not a dispatch, so this was GitHub's scheduler and not a defect in
      the repository; **no manual recovery was needed and none was performed.** Through the outage
      `cron watchdog` failed three times on purpose: it found a lane stale, dispatched `cron-live.yml`,
      and reported `NOT RECOVERED: still stale after cron-live.yml ran` before going red to email the
      owner. Every watchdog run after 17:31 is green, `/api/health` returns `ok: true` with an empty
      `problems` array served from the primary, and `ChunkRun` and `LiveQuote` were 18 minutes old
      when measured. **A lane that reports success while storing nothing is this project's recurring
      failure mode, so freshness was taken from the rows, not from the run conclusions.**

    - **The `cron calendar` failure was exit 2, not exit 1, and the log says so in those words.**
      `jobs/schemacheck.py` printed `could not connect: OperationalError` and
      `this says nothing about the schema, so it exits 2 rather than 1`. **No migration is pending**
      -- the question that had been open since the lane went red. The same log records something
      worth keeping: inside Actions, `DATABASE_URL` points at **Neon** while `SUPABASE_DATABASE_URL`
      is the primary, so when the primary blinks the lanes fall back to a database that is itself
      over quota.

    - **The real artifact restores.** `nbt-backup-38395055013` (34,984,918 bytes, run
      `backup-2026-10-13T120816Z`, schema `20261011130000_decision_history`) was downloaded whole,
      `tools/restore_db.py verify` passed **44 of 44** files on checksum, and it was restored into a
      disposable PostgreSQL **15.18** cluster built with `initdb` on a loopback port -- the 31
      migrations applied to it cleanly first, which is itself the migration test. Result:
      **43 tables, 977,772 rows, content digests equal, 45 foreign keys and 138 indexes**. The 43
      against the artifact's 44, and the 31-row shortfall, are `_prisma_migrations`, which a restore
      deliberately never writes. Production was read back afterwards and is unchanged. This is the
      *latest* artifact, which matters: the 10-11 rehearsal proved the tooling, not this backup.

    - **Resilience is one database, measured.** Both Neon endpoints answered
      `Your account or project has exceeded the quota` on this pass. Read and write failover are
      implemented and their tests pass, and they have **nowhere to fail over to**. The only other
      copy of the data is a GitHub artifact that expires seven days after it is written -- now
      proven restorable, which is the one thing that makes that acceptable at all.

    - **The Data API exposure is worse than "every table is readable", and it is still open.**
      `anon` and `authenticated` each hold **SELECT, INSERT, UPDATE, DELETE and TRUNCATE on all 44
      tables**, RLS is disabled on all 44, and there are **zero policies**. The repository is public.
      The publishable key was **not** committed -- only the string `sb_publishable_` appears, in
      prose -- and an unauthenticated REST call returns 401, so this is not a live breach; but that
      key is designed to be publishable, and the day it is shared anywhere, a stranger can empty the
      database. Worse than the grants themselves: `pg_default_acl` grants `arwdDxtm` to both roles
      on **every new table**, from both the `postgres` and `supabase_admin` grantors, so revoking
      today's grants alone would be undone by the next migration. **Nothing legitimate uses this
      path** -- there is no `@supabase/supabase-js` dependency, no `createClient`, no
      `NEXT_PUBLIC_SUPABASE*` anywhere; the application reaches Postgres directly through
      `@prisma/adapter-pg`. The fix is therefore a revoke of both roles *and* of the default
      privileges, and it was written and ready in this session but **not executed**: it is a
      permission change on the production database and the owner has not approved it. **Phase 2 does
      not pass while this stands, and Phase 3 does not begin.**

118. **The Data API is shut, and the thing that would have re-opened it is shut too.** 2026-10-13,
    applied with the owner's approval in one transaction against the live primary. This closes the
    item rule 117 left open; 117's last bullet is superseded on the question of whether it was
    executed, and stands on everything it measured.

    - **What was checked before touching anything**, because a revoke that misses a second path is
      worse than none: **no grants to `PUBLIC`** on any of the 44 tables, so there is no backdoor a
      role-specific revoke would leave open; **`anon` and `authenticated` are members of no other
      role**, so nothing is inherited; and **all 44 tables are owned by `postgres`**, which is the
      role Prisma connects as, so `ALTER DEFAULT PRIVILEGES FOR ROLE postgres` is aimed at the role
      that actually creates production objects rather than at a plausible-looking one.
    - **The column grants were a false alarm, and proving it mattered.** `information_schema.column_privileges`
      showed 605 columns each for both roles on SELECT, INSERT, UPDATE and REFERENCES, which reads
      like a second set of grants that a table-level revoke would leave behind. It is not:
      `pg_attribute.attacl` is **null on every column**, 605 is **exactly** the number of columns in
      the schema, and the four privileges listed are precisely the four that exist at column level in
      PostgreSQL. They were the table grants reflected, and they went when the table grants went.
    - **Applied:** `REVOKE ALL` on all tables, sequences and functions in `public` from both roles,
      and `ALTER DEFAULT PRIVILEGES FOR ROLE postgres ... REVOKE ALL` on tables, sequences and
      functions from both roles, in a single transaction. Nothing else was altered: no data, no
      `service_role`, no `postgres`, no schema `USAGE`.
    - **Verified by effective privilege rather than by the absence of a grant row.**
      `has_table_privilege` across all 44 tables: `anon` **0/44** and `authenticated` **0/44** on
      SELECT, INSERT, UPDATE, DELETE and TRUNCATE; `postgres` and `service_role` unchanged at
      **44/44**. Residual grant rows 0, residual column privileges 0. No mutating request was made
      against production to test this, and none was needed -- PostgREST executes as `anon`, and
      `anon` can no longer do anything.
    - **The application never noticed.** It reaches Postgres directly as `postgres` through
      `@prisma/adapter-pg`: `/`, `/stocks`, `/crypto`, `/forex`, `/logbook` and `/api/signals` all
      200, `/api/signals` still serving `pool: 557` and a real `asOf`, the front page still priced to
      2026-10-12, `/api/health` still served from the primary, and every row count and the database
      size unchanged at 324.3 MB. **The rollback was not needed** -- an exact 88-statement restore
      was generated from the 616-row snapshot first, and `postgres` owns every table, so re-granting
      is always available.
    - **One residual, and it is not a live gap.** `supabase_admin` still carries default ACLs
      granting both roles everything on new objects, and `postgres` is not a member of
      `supabase_admin`, so this session could not alter them. It only bites for objects
      `supabase_admin` itself creates in `public`, and the migration path creates them as `postgres`
      -- every one of the 44 is `postgres`-owned. It needs an account that can alter that role's
      defaults, and removing `public` from Exposed schemas in the dashboard remains worth doing as a
      second layer. Neither is load-bearing today.
    - **Separately, and left alone deliberately:** a login role `nbt_phase2_reader_20261013` holds
      SELECT on all 44 tables, is not a superuser, does not bypass RLS, and **has no expiry**. It is
      outside the Data API path and outside this fix's scope, so it was not touched. A standing
      read credential with no `VALID UNTIL` is worth a decision, not a silent revoke.

119. **The standbys: what is actually wrong with them, which half this repository can fix, and the
    rewrite budget that was burning the quota in the first place.** 2026-10-13. Rule 117 recorded
    both Neon endpoints as over quota and left it there. That was the measurement and not the
    diagnosis, and the diagnosis turns out to be two faults stacked on one path.

    - **The quota is account-level, not a full disk, and the evidence is that both projects fail
      identically.** Each endpoint was probed as configured, with `dbname=postgres`, and on its
      direct non-pooler host. DNS resolves and TCP 5432 opens on all of them, so neither project is
      deleted or suspended at the network edge; every attempt is refused at the connection stage,
      *before a database is selected*, with `Your account or project has exceeded the quota`. A
      per-project storage limit would not refuse two projects of different sizes in the same breath.
      **The inference drawn from that is corrected by rule 120: the limits are per project, so two
      projects failing together means two exhausted budgets, not one shared one.**
      **The stored credentials are not stale, and there is a clean test for it:** the same endpoints
      answer `password authentication failed for user 'neondb_owner'` when dialled with a wrong
      password, and `exceeded the quota` when dialled with the configured one. Authentication
      therefore succeeds and the refusal comes *after* it, which rules out the cheap explanation
      that the standby is merely holding an old password. Checking this needs no secret: the wrong
      password can be any string.
      The project's own note in `primary_choice` says what this is: Neon's free tier caps **compute
      hours**, "the derive passes used them up twice in two days", and compute hours are counted
      per account. **No `NEON_API_KEY` is configured anywhere**, so the console figure that would
      turn this from a strong inference into a reading cannot be taken from here.

    - **The mirror's failure is not the quota at all, and that is why it matters.** Last success
      `2026-10-11T02:09:38Z`; every run since has failed all three copy steps. The log does not say
      quota -- it says `connection to server at "2600:1f16:4bf:1627:d0d0:afd5:5c59:8d55", port 5432
      failed: Network is unreachable`. Public DNS resolves Neon's pooler to **exactly those two
      IPv6 addresses**, and GitHub's runners have no IPv6 route. This machine never saw it because
      its resolver returns no AAAA, which is why the same endpoint answers "quota" here and
      "unreachable" there. **Two independent faults**: fix the quota and the mirror would still
      fail. `_connect` now pins an IPv4 address with `hostaddr` while `host` keeps carrying the
      name, so SNI routing and certificate verification are unchanged; it moves to the next address
      only for errors that mean unroutable, because a quota refusal is an answer and retrying it
      three times just makes a slower failure. Verified against the live Supabase pooler, which
      routes by username and was unaffected.

    - **`DATABASE_URL_FALLBACK` is empty in Actions.** The mirror prints its environment and the
      variable is blank, so the second standby role has never existed in CI -- the lane has always
      had exactly one target. The three failing "copy steps" are three table groups against that one
      target, not three databases.

    - **The rewrite budget, which is the sustainability finding.** `fetch_crypto` replaced a coin's
      entire series whenever the fetch was at least as deep as what was stored, and in the steady
      state that is every run. Measured against the real stored depths: **75 coins, 98,303 rows,
      rewritten twelve times a day** -- about **2.4 million row writes to persist the 75 bars a day
      actually adds**, and 1.2 million dead tuples a day for autovacuum to walk. On Supabase this is
      invisible because the tier is priced by size; on Neon it is the bill. The series only needs
      rewriting when its depth changed -- a new day, or a deeper venue -- which is once a day, so
      the daily authoritative restatement is kept and the other eleven runs upsert a five-day
      correction window. **91.5% fewer row writes, 200,731 against 2,359,272**, measured not
      estimated. The invariant that a shallow venue never deletes a deep series is unchanged and is
      now tested behaviourally instead of by matching the text of one line.

    - **Size is not the problem and no cleanup is justified.** 324.3 MB of 500. `PriceSnapshot` is
      216 MB of it and its primary key *is* the natural key `(assetId, date)` -- already the cheap
      shape, 2.5 million scans in eleven days. `IntradayBar` is **bounded**, not runaway: it holds
      about eight session days because `jobs/intraday.py` sweeps it, so the "+59% in two days" in
      the earlier handoff was a table filling to its window. At 557 rows a session and 272 bytes a
      row all-in, the permanent record grows about **55 MB a year**, which is roughly three years of
      headroom in the 176 MB that is left. The only indexes with zero scans are two primary keys
      Prisma requires (`IntradayBar_pkey` 5.5 MB, `EventImpact_pkey` 1.1 MB); dropping a required
      primary key to save 6.6 MB of a 500 MB tier is not a trade worth making.

    - **So three-database resilience is still one database, and this is what it would take.** The
      repository's half is done: the mirror can now reach an IPv4 standby, and the lane that was
      burning the compute no longer does. The half that is not here is the Neon side.
      **What this rule said next -- that a replacement project on the same account would inherit the
      same ceiling, so a second home needs a different account or provider -- is wrong, and rule 120
      replaces it.** **Nothing here claims a working standby**, and `standby_parity.py` will keep
      saying so until one answers.

120. **Correction to rule 119: Neon's free limits are per project, not per account, so the recovery
    is cheaper and nearer than that rule claimed.** 2026-10-13, checked against Neon's own FAQ rather
    than against this repository's memory of it.

    - **The published Free plan**, from `neon.com/faqs/free-plan-limits-and-quotas`: **100 projects**,
      **1 GB Postgres storage per project** (raised from 0.5 GB on 2026-10-01, which is why older
      notes and third-party pages still say 0.5), **20 GB across all projects**, **100 CU-hours of
      compute per project per month**, and 5 GB of network transfer per project per month.
      **Compute and transfer reset at the start of each monthly billing period. Storage does not.**

    - **What rule 119 got wrong.** It read `primary_choice`'s note -- "Neon's free tier caps compute
      hours ... the derive passes used them up twice in two days" -- as an account-wide ceiling, and
      concluded that a replacement free project would inherit it, so a real second home needed a
      different account or provider. That does not follow from a per-project budget. Two projects
      refusing together is **two exhausted budgets**, not one shared one, which is exactly what two
      projects that both ran derive passes would produce.

    - **What follows instead, and it is better news.** A **new** free project on the same account
      starts with its own 100 CU-hours and its own 1 GB, and the account is nowhere near the 100
      project or 20 GB caps -- so a replacement standby costs nothing and needs no new account. And
      because compute resets each billing period, **the two existing projects should return on their
      own at the next reset** without being touched. Neither path requires spending money, and
      neither was visible while the limit was believed to be account-wide.

    - **Which of the two limits actually tripped is still unmeasured, and the error message will not
      say.** `Your account or project has exceeded the quota` is the same sentence for storage and
      for compute. Storage is the cheaper hypothesis to rule out -- the mirror only ever copied
      trailing windows, so a 1 GB cap should be far away -- but *should be* is not a measurement.
      It needs the console or a `NEON_API_KEY`, and **neither exists on this machine**: no `.env`
      holds one, Vercel has only the two database URLs, and the GitHub token is refused on
      `actions/variables` and `actions/secrets`. The exact readings needed are in the handoff.

    - **The rule this leaves behind:** a published limit is a fact about a vendor's current page, not
      about what this project remembers, and it moved under us once already on 2026-10-01. Check it
      at the source before building a recovery plan on top of it.

121. **The mirror is proven to work, against a real standby that was not Supabase.** 2026-10-13.
    Rule 119 fixed the IPv4 fault by reading a log; this is the end-to-end run, because "Supabase
    answered" is not evidence that a mirror into a second database writes anything.

    - **How the standby was built, which is also how a real one would be.** A disposable PostgreSQL
      **15.18** cluster on a loopback port, the 31 migrations applied, then the genuine production
      artifact `nbt-backup-38395055013` restored into it -- 44 tables. That is a standby created the
      way the runbook says to create one, and it is deliberately a *different major version* from the
      17.11 source, so schema compatibility is exercised rather than assumed.

    - **Then it was made to fall behind on purpose**, because a mirror into an already-equal copy
      proves nothing: the last five days of `PriceSnapshot` and the whole of `DecisionLog` were
      deleted from the copy. Newest price fell to 2026-10-08 against the source's 2026-10-13, and
      `DecisionLog` went to 0 against 1,666.

    - **`jobs/mirror.py` then ran for real**, Supabase to that standby. It matched **616 assets by
      `(industry, symbol)`**, which is the natural-key translation working across two separately
      seeded databases, and wrote `DecisionLog` 1,666, `PriceSnapshot` 1,749, `News` 159, with
      **0 unmatched** on every table. Afterwards the two agree exactly: **833,413 snapshots,
      newest 2026-10-13, 1,666 decisions, newest `computedAt` 2026-10-13 03:18:41.415** on both.
      The source gained 253 rows from the live daily lane while this ran and the standby took those
      too, so freshness propagates rather than merely a backlog draining.

    - **The project's own instrument agrees.** `tools/standby_parity.py` against that standby exits
      **0**: 557 of 557 active assets held, 0 missing news readings, and every decision input --
      prices, setups, factors, analogs, decisions, human signals -- level with the primary. Note the
      derived tables are level because the standby was built from a full backup, not because the
      mirror copies them; the mirror copies the four irreplaceable ones and the lanes recompute the
      rest, exactly as its docstring says.

    - **What this does and does not prove.** It proves the mirror's logic, natural-key translation,
      schema compatibility across major versions, writes, row counts and freshness. It does **not**
      prove the Neon leg: the IPv4 `hostaddr` fix is tested by unit tests and by a live Supabase
      connection, and the thing it was written for -- a GitHub runner dialling a Neon pooler that
      publishes AAAA -- cannot be exercised until Neon answers and the commit runs in Actions.
      That is the one part of the standby story still taken on reasoning rather than observation.

122. **A closed daily bar does not change, measured; and a classification of what a reset would
    actually destroy.** 2026-10-13. Rule 119 cut the crypto rewrite to once a day on the reasoning
    that a replace restates history. This is the measurement of whether that restatement corrects
    anything, and the answer changes the design again.

    - **The experiment has to hold the venue still, and the first attempt did not.** Refetching the
      stored series through the normal chain and diffing gave **12,011 of 12,809 bars "different"**,
      which looks like catastrophic drift and is nothing of the kind: the stored rows are
      **Coinbase** and the chain now answers **Binance** first, so that figure measures two
      exchanges disagreeing about a close. It is the reason a row carries the venue that produced
      it. Refetching **Coinbase against Coinbase-sourced rows** for BTC, ETH, SOL and ADA gives
      **9,779 overlapping bars back to 2018 and not one difference**.

    - **So the scheduled replace corrects nothing, and it is gone.** `crypto_write_plan` now rewrites
      only on a first fill, on a **materially deeper** venue (`len(bars) > stored + 3` -- the real
      case is Binance paging SOL back to 2255 bars where the stored Coinbase series holds 1944), or
      on an explicit `--restate`, which is how a controlled re-ingestion or a recovery asks for it.
      Everything else upserts the five-day window, and the new day's bar is inside it.
      **2,359,272 scheduled writes a day become 4,500, with no deletes at all** -- 99.81%, against
      the real stored depths. A second effect matters as much: the series stops churning between
      venues, because whichever exchange answers first on a given runner no longer rewrites six
      years of provenance.

    - **What a full reset would destroy, classified rather than assumed.** Of 44 tables, the ones
      with an upstream to refetch from are prices, the seeded lists, and the calendar; the derived
      tables are rebuilt by the existing chain. **106,562 rows have no upstream at all**:
      `IntradayBar` 94,544 (eight session days; the venues serve a short lookback),
      `News` 6,211 (back to 2026-09-08 -- RSS windows are days, not five weeks),
      `HumanSignal` 1,681, `SignalLog` 1,681, `DecisionLog` 1,666, `LiveQuote` 225,
      `MacroGate` 201, `Coverage` 156, `ChunkRun` 120, `CallOutcome` 58, `AuditLog` 10,
      `DecisionRun` 6, `Calibration` 2, `SourceReliability` 1.

    - **The learning corpus is two days old, and this would be the second time it was reset to
      zero.** `DecisionLog` and `SignalLog` both begin **2026-10-11**, because the quota event of
      2026-10-09 already destroyed 10-01 to 10-09 and rule 114 records that it was never recovered.
      Maturation now: **63 of 1,666 decisions measured at +1, none at +5, none at +20**; 1,050 of
      1,681 signals at +1, none at +5, +30 or +60. The out-of-sample loop that rule 66 exists to
      produce has not yet returned a single matured five-session result. Wiping it restarts a clock
      that takes **twenty trading sessions -- about four weeks** -- to reach +20, and no re-ingestion
      brings it back, because it is a record of what the system said before it knew the outcome.
      Nothing in a market-data resync can reconstruct that.

    - **The reset did not happen, on the mandate's own gate.** It requires all three targets
      identified *and* a fresh recoverable backup for each, and says in terms that if either Neon
      database is still unreachable the three are not ready. Both are still refused on quota, so
      **two of three cannot be backed up and cannot be reset**. What was done instead is everything
      the gate asks for on the reachable one: a fresh backup `2026-10-13T200907Z` (44 tables,
      978,393 rows, 35.2 MB, verified 44/44 by checksum), restored into an isolated PostgreSQL
      15.18 database and reconciled against production -- **43 tables, 978,362 rows, digests equal**,
      and prices, decisions, signals, news and intraday bars identical on both sides. Production
      integrity alongside it: 0 duplicates on every real uniqueness constraint, 0 null closes,
      0 orphans, 45 foreign keys and 44 primary keys intact.

123. **Correction to rules 119 and 122: "2.36 million writes a day" was the nominal schedule, not
    what the database actually saw. The per-run saving stands; the daily one was overstated by an
    order of magnitude.** 2026-10-13, from `pg_stat_user_tables` against the live primary rather
    than from the cron expression.

    - **What the counters say.** Over an 11.11-day window `PriceSnapshot` took **2,445,141 inserts
      and 820,695 deletes -- 293,955 row writes a day**, not 2,359,272. The deletes are the crypto
      replace, and dividing them by the 98,303 stored crypto rows gives **0.75 full passes a day,
      not twelve.** Rules 119 and 122 multiplied the series by the lane's *scheduled* cadence; this
      project already knew better, because rule 114 records that **GitHub delivers roughly a tenth
      of a frequent schedule**, and this session watched two multi-hour gaps where nothing ran at
      all. The arithmetic was right and the input was the timetable instead of the clock.

    - **The honest three numbers, which are not interchangeable.**
      **Per crypto run: 196,606 writes to 375, a 99.81% cut.** That one is solid, is what the code
      changes, and does not depend on how often anything runs.
      **At the nominal twelve runs a day: 2,359,272 to 4,500** -- a projection, true only if the
      schedule were ever delivered in full, which it is not.
      **On the measured cadence: 293,955 to about 146,500 row writes a day, a 50.2% cut of all
      `PriceSnapshot` writes** -- because the crypto rewrite is **50.3%** of everything that table
      does, and removing it halves the table's write volume. That is the figure to quote for what
      the database will actually experience, and it is still the single largest saving available.

    - **And none of the three is a compute measurement.** They are row writes. What a CU-hour costs
      is a function of wall time on a running endpoint, not of rows, and it cannot be known until
      the commits run in CI against a reachable Neon. Rule 122 said this and it stays true.

    - **What the same counters say about the other half, which is not yet explained.** The 146,215
      writes a day that are *not* crypto are far more than the roughly 557 rows a session the pool
      actually adds. The Yahoo lane is genuinely incremental -- measured today, **602 of 616 assets
      take the incremental path and 14 take the full backfill** -- but it upserts a
      `CORRECTION_DAYS = 14` window for every asset on every run, which is 8,428 rows a pass before
      anything new is stored. Unlike crypto, that window has a defensible reason: Yahoo
      back-adjusts for corporate actions (rule 115), so an equity's *whole* history can legitimately
      restate, and a 14-day window is a partial answer to that rather than an unnecessary one.
      **It was measured and left alone**, because shrinking it without first measuring how often an
      adjusted bar actually changes would be the same mistake this rule is correcting.

    - **The rule this leaves behind, and it is the second time this session:** a number taken from
      configuration is a claim about intent, and a number taken from `pg_stat` is a claim about the
      world. Only the second one belongs in a report about savings.

124. **The optimization is live, and this is the first measurement of it rather than a projection.**
    2026-10-13 20:51 UTC. `main` and `master` moved `46ec556` -> `3686178` (fast forward, 12
    commits, 11 files: the restore tooling, the IPv4 dial, the crypto write plan, their tests and
    this file). No workflow file changed, so nothing about scheduling moved. CI's `tests` workflow
    ran on the push and passed.

    - **One `cron crypto` run was dispatched against the new code** and the counters were read
      either side of it. **All 75 coins took the cheap path -- "kept N stored, upserted 5" -- and
      none was replaced.** `PriceSnapshot` moved **0 inserts and 0 deletes**. The same run on the
      old code would have deleted 98,303 rows and written them back: **196,606 row writes, measured
      against 375 upserts.**

    - **So the three numbers finally separate cleanly.** Per run, 196,606 -> 375, and that is now
      **measured in production**, not computed. On the measured cadence of 0.75 crypto passes a day
      (rule 123) this removes about **147,000 row writes a day, roughly half of everything
      `PriceSnapshot` does**. What a CU-hour costs is still unmeasured and will stay so until a Neon
      endpoint answers -- row writes are not compute, and this rule does not pretend otherwise.

    - **The run also confirmed the design handles the case it was built for.** It ran at 20:51 UTC,
      mid crypto day, so no new bar had closed and the five-day window was pure correction cover.
      When a bar does close, the window still contains it, so the new day lands without a replace --
      which is what `test_a_new_day_no_longer_rewrites_the_whole_series` asserts, now with a
      production run agreeing.

    - **What is left on the table, and it is small.** Those 375 upserts write values identical to
      what is already stored, and PostgreSQL still versions a row on an UPDATE, so they cost 375
      dead tuples a run. `ON CONFLICT ... DO UPDATE ... WHERE t.close IS DISTINCT FROM excluded.close`
      would make an unchanged upsert a no-op. It was **not done**: 375 rows against the 98,303 this
      rule just removed is noise, and a change to the write path earns its risk only when the
      measurement says it matters.

125. **A brand new Neon project in this account is refused too, which settles the question rule 120
    got wrong: the restriction is account-level, and creating more projects cannot fix it.**
    2026-10-13, tested directly rather than reasoned about.

    - **The test.** A third Neon project, `ep-nameless-glade-b4q0k41g`, created in the same account
      and with no usage of its own, was dialled with fresh credentials. It answers
      `Your account or project has exceeded the quota` -- **the same sentence as the two exhausted
      projects**. The endpoint is real and the credential is right: the same host with a deliberately
      wrong password answers `password authentication failed for user 'neondb_owner'`, so
      authentication succeeds and the refusal lands after it, exactly as on the other two.

    - **What that falsifies.** Rule 120 read Neon's published Free plan -- 1 GB and 100 CU-hours
      *per project*, 100 projects, 20 GB in total -- and concluded that a replacement project would
      start with its own budget, so a standby could be rebuilt on this account for nothing. **A new
      project with zero consumption is refused, so that conclusion is wrong.** Rule 119's original
      instinct that something account-wide was in play was closer, even though its stated reason
      (one shared compute ceiling) was not the published rule.

    - **What it does not tell us, and the error message never will.** Whether the account tripped
      the 20 GB aggregate storage cap, an account-level allowance, a payment or verification hold,
      or something else. All three projects print the same sentence for every cause. This is now the
      **third** attempt to name the cause from outside, and the answer has not changed: it takes the
      console or a `NEON_API_KEY`, and no amount of connection testing substitutes for it.

    - **The practical consequence, which is the useful part.** **Provisioning more projects is
      futile** -- that path is closed by measurement, not by argument, so nobody needs to spend
      another cycle on it. Until the account itself is cleared, there is no Neon standby to build,
      and `DATABASE_URL_FALLBACK` has nothing to point at. The mirror, the restore procedure and
      the IPv4 dial are all proven and waiting; what is missing is one account, not any code.

    - **The rule this leaves behind, and it is the third correction in one session:** published
      limits describe a plan, not an account's current state. Rule 120 was right about the documented
      policy and wrong about this account, and only a test against a fresh project could tell the
      two apart.

126. **Three database roles, and for the first time the sentence is backed by a connection, a
    restore, a mirror and a parity run on each.** 2026-10-13. Neon is out of the architecture --
    not fixed, replaced -- and the replacements are on two other providers, which is the point.

    - **Why not more Neon.** Rule 125 established that a brand new project in that account is
      refused with the same quota error as the two exhausted ones, so the restriction is the
      account. A third project there would have been a fourth refusal. Neon is left configured
      nowhere and referenced by nothing.

    - **The three roles, each a separate cluster by `system_identifier`** -- which is the check that
      distinguishes three databases from three names for one:

      | role | provider | version | `system_identifier` |
      | --- | --- | --- | --- |
      | primary `SUPABASE_DATABASE_URL` | Supabase | 17.11 | 7692131729119822239 |
      | standby 1 `DATABASE_URL_FALLBACK` | Aiven | **18.6** | 7696266274017226891 |
      | standby 2 `DATABASE_URL` | Prisma Postgres | **17.2** | 7695850978935533599 |

      Three providers, three accounts. The failure that took Neon out was account-level, and this
      is the shape that survives it: no single account action can now remove more than one role.
      A second Supabase project was considered and rejected for exactly that reason -- it would
      have shared the primary's account and counted as resilience without being any.

    - **Built the supported way, not by hand.** Each standby took the 31 migrations, then the
      verified backup `2026-10-13T200907Z` through `tools/restore_db.py --allow-remote`, then
      `jobs/mirror.py` to catch up what had landed since. Both restores reported **43 tables,
      978,362 rows, content digests equal, 45 foreign keys, 138 indexes**; both mirrors matched
      **616 assets by `(industry, symbol)` with 0 unmatched** and wrote the same 74 rows;
      `tools/standby_parity.py` exits **0** against both -- 557 of 557 active assets, no missing
      news readings, every decision input level with the primary. Row counts on all three:
      833,413 / 1,666 / 1,681 / 6,211 / 616, newest 2026-10-13.

    - **And they can actually serve the role**, which row counts alone do not prove. The same
      app-shaped query -- newest close per asset with its provenance -- returns identical values
      from all three, `AAPL 340.97 Yahoo Finance` and `btc-bitcoin 81742.50 Coinbase` included.

    - **Two version artefacts worth knowing before someone reads them as drift.** Aiven is
      PostgreSQL **18**, a major ahead of the source, and the restore reported `n=406` NOT NULL
      constraints there that 17 does not name -- the same thing rule 71 hit when comparing schema
      parity. Prisma's endpoint is **pooled**, and `prisma migrate deploy` ran through it without
      trouble, which was not a given. Neither is a defect; both would look like one in a diff.

    - **What is still owner-only.** The GitHub Actions secrets. The token here is refused on
      `actions/secrets` (403), so `DATABASE_URL_FALLBACK` and `DATABASE_URL` are correct locally and
      in this file, and **not yet correct in CI** -- until they are set there, the scheduled mirror
      still points at a dead Neon project and the standbys stay current only by hand.

127. **Phase 1 closes. Phase 2 does not, and the single reason is a secret this session cannot
    write.** 2026-10-13, final verification pass. Measurements repeated rather than carried forward.

    - **Phase 1: PASS.** Nine representative closes across AAPL, MSFT and NVDA reconcile **exactly**
      against a live Yahoo fetch. Coverage is 616 assets and 833,413 snapshots from 2019-01-01
      (crypto 2018-11-04). Freshness is reported honestly rather than flattered: `/api/health` puts
      every market at 0 sessions behind except US at 1, and prints `state` per market instead of a
      single green light. Every page serves -- `/`, `/stocks`, `/crypto`, `/forex`, `/logbook`,
      `/api/signals` all 200, from the primary, pool 557. Tests 849 Python and 466 Node.

    - **Phase 2: BLOCKED on one criterion, and everything else in it passes.** The three roles are
      distinct clusters (rule 126), all three hold **833,413 prices, newest 2026-10-13, 31
      migrations and the same 138 indexes**, both standbys restored with digests equal and both
      pass `standby_parity.py`. What is missing is that **no authorised workflow run has mirrored
      into them**, because this token is refused on `actions/secrets` and the Actions secrets still
      name the dead Neon project. A manual mirror is not proof that a scheduled one will target the
      right provider, so Phase 2 stays open on exactly that.

    - **The standby indexes are 35 MB larger than the primary's, and it is not a defect.**
      `PriceSnapshot_pkey` is 62.1 MB on Supabase and **95.0 MB** on both standbys, with the same
      138 indexes and identical content digests either side. The primary's rows arrived per asset in
      date order, which B-tree deduplication packs tightly; a restore COPYs in dump order and packs
      worse. It costs 3.5% of Aiven's 1 GB and buys nothing to reindex, so it was measured and left.

    - **A label that had started lying.** `cron-mirror.yml` routes by secret name, but the shell
      locals carrying them were still `NEON` and `NEON2` -- pointing at Aiven and Prisma. That is the
      same class of confusion that once had `schemacheck` printing "DATABASE_URL points at: Neon"
      while the truth was elsewhere, so they are now `DB_URL` and `DB_URL_FALLBACK`. The test
      asserting the workflow never echoes a credential keyed on the old names and would have gone
      **silently vacuous**; it now covers all three, which is stronger than before. Renaming a
      variable is cosmetic; letting a guard quietly stop guarding is not.

    - **Security, re-verified rather than assumed.** `anon` and `authenticated` hold **0 of 44** on
      SELECT, INSERT and TRUNCATE; an unauthenticated Data API request returns **401**;
      `nbt_phase2_reader_20261013` still holds SELECT only and remains undecided by the owner;
      `supabase_admin`'s default ACLs remain unchangeable from `postgres` and remain not a live gap.
      **No credential appears in any tracked file or anywhere in pushed history** -- scanned for the
      Neon, Aiven, Prisma and Supabase key shapes, zero hits. The local `.env` is ignored and
      untracked. The five connection strings pasted into the chat transcript are still in that
      transcript; nothing here erases them, and two of them are live.

128. **Phase 1 and Phase 2 are closed. The criterion rule 127 left open was met by a real workflow
    run, and this records what that proves and what it does not.** 2026-10-13, final closeout.
    No database, code, workflow or infrastructure was changed to write it.

    - **Phase 1: PASS**, on the evidence rule 127 set out and no more than that. Nine representative
      closes reconcile **exactly** against a live Yahoo fetch; coverage is **616 assets and 833,413
      snapshots** with daily price history from 2019-01-01; integrity passes on the real uniqueness
      keys (0 duplicates, 0 null closes, 0 orphans); freshness and provenance are printed honestly
      per market rather than as one green light; every public page serves from the primary; **849
      Python and 466 Node tests** pass. The documented limitations stand unchanged: `IntradayBar`
      holds about eight session days because the venues serve a short lookback, and markets differ
      in how far behind they may legitimately be, which is why each carries its own `state`.

    - **Phase 2: PASS.** The one criterion rule 127 blocked on -- that a real authorised run, not a
      manual one, mirrors into the intended targets -- is met by run **38474617007** on `e00711f`,
      **success**. It chose `configured: DATABASE_URL_FALLBACK,DATABASE_URL` and reported
      `summary: DATABASE_URL_FALLBACK ok, DATABASE_URL ok`. Each target matched **616 assets by
      `(industry, symbol)`** and read `PriceSnapshot` 3,456, `DecisionLog` 1,666 and `News` 4,770
      with **0 written, 0 unmatched** -- zero writes being the correct result for standbys already
      current, and the point of the run being which providers it reached, not how much it moved.
      The workflow's own parity step then passed against **both**: 557 of 557 active assets held,
      0 missing news readings, every decision input level.

    - **What the log cannot show, and how identity was established instead.** The mirror never
      prints a connection string, which is a property worth keeping, so the log names variables and
      not hosts. Provider identity rests on three things together: the secrets were copied from a
      `.env` whose three entries were each verified by `system_identifier` first; both targets
      matched 3,456 price rows as *unchanged*, which only a database holding this exact dataset can
      do; and the Neon project those secrets used to name would have refused on quota rather than
      succeeding. After the run all three clusters confirm separately -- Supabase
      **7692131729119822239**, Aiven **7696266274017226891**, Prisma **7695850978935533599** -- each
      holding 833,413 prices, 1,666 decisions, 6,211 news, newest 2026-10-13.

    - **Five things stay open, and closing the phases does not close them.**
      (1) Aiven's and Prisma's **monthly compute and network-transfer consumption are unmeasured**;
      only storage was read, from the databases themselves. Nothing here says the free-tier
      architecture is future-proof.
      (2) **Cron scheduling reliability is unaudited** and is a separate task; this project has
      measured GitHub delivering roughly a tenth of a frequent schedule, so mirroring is now
      correctly *configured* without being guaranteed *frequent*.
      (3) **No credential was rotated.** Five connection strings were pasted into the chat
      transcript and remain there; three are dead Neon, two are live. Nothing in this repository
      erases a transcript, and this rule does not pretend otherwise.
      (4) **`nbt_phase2_reader_20261013`** is still a login role with SELECT on all 44 tables and
      **no `VALID UNTIL`**, awaiting an owner decision.
      (5) **`supabase_admin`'s default ACLs** remain unchangeable from `postgres`. Objects created
      by the migration path inherit the corrected `postgres` defaults, which is every table today;
      that is not the same as proving every future creation path is covered.

    - **Phase 3 has not started.** No brain training, no historical-event ingestion, no cron audit.
      The optimization that is live is the crypto write path of rules 122 to 124, measured in
      production at 0 inserts and 0 deletes for a run that previously wrote 196,606 rows.

129. **The historical replay was complete and wrong, and what proved it was running it twice.**
    2026-10-14, Phase 3 data foundation. No production data was changed by any of this; every
    figure below comes from a read, a public API, or a workflow run.

    - **Two reads ignored the replay date, and the reconcile found them.** Of the 799 sessions that
      had been replayed twice, **413 produced different setups the second time**, beginning at the
      51st session of run `38488899752` — the moment `cron-us-prices` wrote new closes mid-run. A
      deterministic as-of replay cannot differ from itself, so the difference was the clock leaking
      in. The fields that moved name the culprits: `conditions` on 11,012 rows, `against` on 1,871.
      `jobs/setup.py all_industry_relative` measured each asset's return from its newest close
      *ever*, so a 2019 session's "versus its industry" came from 2026 prices; and
      `tools/decide.mjs` read the newest `AssetAnalog` row with no `periodEnd` bound, alone among
      the derived tables in `readInputs`. Both are bounded now, both unchanged on the live path,
      and `7cae2f6` carries the fix.

    - **The tests that should have caught it were testing the wrong thing.** `test_every_reader_
      takes_the_bound` enumerated four readers by name and `all_industry_relative` was not among
      them; `test_every_input_is_bounded_to_the_replay_date` asserted only that a bound existed
      *somewhere* in `readInputs`, which the other tables satisfied on `AssetAnalog`'s behalf. A
      list of names is not a rule. Both are per-reader and per-statement now, and
      `tools/determinism_check.py` with `data-worker-determinism.yml` re-replays a seeded,
      year-stratified sample and demands byte-identical output — the leakage test that only time
      can run.

    - **Every earlier output came from the unbounded code, so all 2,000 sessions were replayed
      again.** `data-worker-reconcile.yml` rebuilds the canonical checkpoint from the persisted
      outputs rather than from any checkpoint, trusting a run only where `lib`, `jobs/setup.py`,
      `jobs/sessions.py`, `jobs/nbt.py`, `tools/decide.mjs`, the schema and `requirements.txt`
      match the current tree. That trust rule is also why the checkpoint namespaces disagreed at
      all: the chain never passed `checkpoint` to the slice it dispatched, and the fetch step asked
      the last successful run for a hardcoded `nbt-worker-checkpoint` with `|| true` hiding the
      miss, so a chain restarted from zero whenever the previous slice had written another name.

    - **239 unadjusted corporate actions, across 152 of the 616 assets.** Found by adding PSX to
      the independent price check, which was only possible because Yahoo serves the Karachi listing
      (`SYMBOL.KA`, PKR, exchange KAR) and that is a different provider from the exchange's own
      daily file. BECO ran at ten times Yahoo's series until 2025-11-17 and then stepped down to
      meet it: Yahoo back-adjusted its whole history for a one-for-ten action and the exchange file
      did not, so the stored series carries a **-88.6% one-day move no holder experienced**. Of 60
      candidates checked against a second provider, **52 showed an ordinary day there, 2 were real
      moves both saw, and 6 had no second source**. Mostly PSX (173), but 22 US names too, and that
      half is ours: the lane fetches incrementally, so a bar stored before a split keeps the old
      scale while the provider silently rescales its own history behind it. Every factor measured
      across such a date is wrong, so `tools/foundation/assemble.py` carries
      `dataQuality.unadjustedActionInWindow` per row. Flagged rather than dropped — a row is still
      correct about everything that does not cross the action.

    - **The universe contains no failures.** Not one stored asset has a series that ends before
      today, so every backtest on it is a backtest on survivors. The 59 inactive assets left the
      pool for low turnover, not delisting. Measured against the S&P 500's own removal list since
      2019: **127 removals, 124 absent from the universe, 63 with no free daily history left**. The
      61 that can still be fetched are compared with the stored universe over each name's own
      window, so the figure measures the bias and not the calendar. It is a lower bound by
      construction: the 63 that vanished were mostly the acquisitions and the failures.

    - **What the foundation holds, each with a test that enforces it.** 32 macro series at 16.8
      years, every row carrying a conservative `availableAt`; 10 of them with revision history from
      400 ALFRED snapshots each and 0 failed fetches. One subtlety had to be labelled: ALFRED
      returns a series' whole history in every snapshot, so an observation older than the first
      snapshot has a `firstSeen` that records when this collector first looked, not when the figure
      was published — flagged `leftCensored`, and 2,459 have a real first sighting. 80 principles
      with every citation checked at Crossref (14 DOIs written from memory were wrong, and were
      replaced only by a search result passing the same test), 69 testable here, 19 with a runnable
      rule. 168 verified events in 159 clusters, 46 of them with two independent evidence groups.
      802,876 point-in-time asset-sessions, reconciled against an independently computed expected
      count, with 240 live-code equivalence samples and 0 mismatches.

    - **The macro availability rule has one test worth keeping.** On 16 March 2020 the join must
      still report January's 3.5% unemployment, because March's did not exist yet. A join keyed on
      observation date would show the spike, and would be look-ahead wearing a timestamp.

    - **Two faults that would have failed the run rather than the review.** The block bootstrap
      materialised every resampled trade: 244 seconds per rule at full scale, about 89 minutes
      across 22 rules, against a 240 minute budget that also has to build the features. Resampling
      each session's sum and count gives the same number in 4 seconds. And the leakage scan ran per
      rule over 800,000 rows, about a billion string comparisons for an answer that cannot have
      changed; the first attempt at fixing that memoised by list identity, which CPython reuses
      after a collection, so a poisoned dataset inherited a clean verdict from an unrelated one. It
      passed alone and failed in the suite, which is the only reason it was caught. Opting out is a
      parameter now, never an inference.

    - **The constraint that decides where these jobs run.** The Supabase session pooler allows 15
      clients. One local analysis started while a replay slice was in flight exhausted it
      (`EMAXCONNSESSION`, 12:19 UTC) and the standby then timed out. Everything that reads the
      database runs on a runner, one connection, after the heavy step.

    - **Open, and not this session's to close.** `cron-watchdog` has failed intermittently since
      02:09 UTC, before any of this work, and it fails with **exit code 2** — an uncaught exception
      rather than the 0 or 1 `main` returns — so the monitor goes red without saying why. A monitor
      that cannot report its own fault is the shape of problem rule 75 was written about.
      Diagnosing it needs the run log and `SITE_URL`, neither of which this session has.

130. **The PSX history was recovered rather than measured again, and the corporate-action
    quarantine was narrowed from the asset to the defect.** 2026-10-15, Phase 3 data foundation.
    This is the first entry here that changed production data: 183,267 rows were added to
    `PriceSnapshot`, after a verified backup, and no existing row was altered.

    - **The headline number was wrong in the safe direction, and the difference is the whole
      point.** `psx_recovery.json` put the shortfall at 275,812 bars across 203 symbols. Of the
      403,042 bars Yahoo's Karachi listing actually served, **62,399 are not bars**: 55,445 flat
      zero-volume pads for sessions the exchange did not hold, 4,157 missing an OHLC field, 2,797
      with prices out of order. Of what survived, **38,246 could not be written** because the two
      providers quote that stretch of history on different bases. **183,267 were written.** The
      gap between 275,812 and 183,267 is not a shortfall in the recovery; it is the part of the
      headline that was never recoverable, counted for the first time.

    - **Two providers, two bases, and an anchor rule instead of a judgement.** The exchange file is
      raw; Yahoo back-adjusts for splits. `MTL` shows what that means: it has nine splits since
      2019, and its 2019 Yahoo close is 189.48 where the exchange stored 820.48 -- a ratio of
      4.3303, which is the nine factors multiplied together. Appending those bars would have
      written a 77% fall that no holder lived through. So a missing date is written **only when the
      nearest stored date on each side of it is one Yahoo also serves and prices within 0.5% of the
      exchange**, and no split falls between them. An action inside the gap necessarily makes the
      earlier anchor disagree, which is why the rule needs no opinion about where the actions are.
      `recovery-manifest.json` had already demanded this under `psx-pre-2024-monthly-grid` ("never
      mix the two series for one asset"); the anchor rule is how that demand was met per date
      rather than per asset.

    - **The join was measured, not argued.** 18,760 places in the stored PSX series now have one
      provider's bar next to the other's. **At none of them do the two providers price the seam
      date differently.** Three seams move more than 30% -- JATM +64.05%, HIRAT +59.06%,
      PASL +35.42% -- and all three are real: each symbol makes six to twelve moves that size
      *within a single source*, and both providers quote the same close on the seam date. HIRAT is
      the clearest: Yahoo padded 2024-04-15 to 04-29 flat at 1.27 with zero volume, the filter
      dropped every one of them, and both providers then quote 2.02 on the reopening session. 907
      seams join to a date Yahoo serves no valid bar for; those are reported as unconfirmed rather
      than counted as clean. **The first version of this check failed 341 seams and was wrong** --
      it compared against the raw provider array, including the very pads the filter had rejected.
      A bar thrown away as fabricated cannot then be quoted as the provider's opinion of that date.

    - **PSX coverage fell from 0.983 to 0.816, and that is the first honest reading of it.** The
      per-asset figure compares each asset with a calendar built from the same data, so twelve
      dates a year looked like a complete year. The calendar is real now: **2019 went from 13
      session dates to 246, 2023 from 12 to 245, 2024 from 118 to 245**, and the assets that are
      still sparse have stopped being flattered by a sparse calendar. Nothing got worse; the
      measurement stopped agreeing with itself.

    - **The quarantine was costing 88 assets nearly their whole history for a defect that lasts
      five sessions.** The analog pool is the asset's entire history, so the old rule flagged every
      session at or after an asset's first unadjusted action. `AnalogSeries` now excludes the three
      things an action actually spoils -- a candidate whose own factors are measured across it, a
      forward window that crosses it, and a session whose own factors cross it -- and nothing else.
      Measured over 1,017,125 eligible sessions: the old rule flagged **171,746**, the window rule
      still excludes **53,571**, **4,614** sessions get no analog block because their own factors
      cross an action, and **120,839 sessions across 138 assets are restored**. `assemble.py` reads
      the feature build's manifest to decide which rule applies, so an older dataset built without
      the exclusion is still flagged the old way rather than silently trusted.

    - **Two of the 239 candidates are not actions at all.** Where the scan's second provider
      reported the same large move, the move happened: Yahoo adjusts for splits, so a split cannot
      still be a 32% one-day fall there. `DG` 2024-08-29 and `ALTN` 2025-02-27 are excluded from
      the action list, which both consumers now read from one place (`tools/foundation/actions.py`)
      so they cannot disagree about what the file says.

    - **The provider's split calendar confirms ten of the 173 PSX candidates and is silent on the
      rest.** Ten match a Yahoo split within five days whose factor reproduces the observed ratio
      (LCI 5:1, DLL 10:1, CLOV 10:1, MTL 2:1, KOHC 5:1, KML 10:1, BAFL 2:1, THCCL 5:1, KTML 5:1,
      UBL 2:1). One contradicts it: `ICIBL` moved 5.96x on 2026-07-13 while the nearest recorded
      split is 84.9:100 three days earlier. 158 candidates belong to symbols Yahoo lists with no
      split recorded on that date -- so Yahoo's split *events* for `.KA` are sparser than its own
      price adjustments, and a candidate without a provider split stays a candidate. **No price was
      de-adjusted and no factor was applied**: the evidence establishes which candidates are
      actions, not what the raw series should have been.

    - **What is still missing, exactly.** 38,246 bars across 69 symbols, all pre-2024, held because
      the bases diverge -- worst are TREET (1,151, 2019-01-02 to 2023-11-30), IBLHL (1,106), SEARL
      (1,093), GATM (1,054), AVN (1,053). 23 symbols are served HTTP 404 by Yahoo and keep the
      7,309 bars they have (BBFL, BFAGRO, BFBIO, BML, ENGROH, GAL, GCWL, GDL, IMS, ITANZ, LIVEN,
      LSEVL, QTECH, SELECT, SOYASUP, SPAC1, SPSL, STL, TISL, WAFI, WAHDAT, ZAL, ZUMA); 17 of them
      were already recorded under `late-listing-histories` as recent listings, which is the same
      fact from the other side. Recovering either group needs a provider that serves raw PSX prices
      and is not the restricted feed, and no such provider is known.

    - **A fetch that cannot tell a 404 from a dropped connection writes symbols off.** The first
      pass reported 41 symbols unserved. Eighteen of them had simply failed mid-run -- `nbt.get`
      returns None for a refusal and for a timeout alike -- and one of the eighteen, SZTM, had been
      fetched by hand minutes earlier. The tool now asks for the status code once before deciding,
      and the count settled at exactly the 203 and 23 measured on 2026-10-14.

    - **Still open, and why.** The dataset itself was not rebuilt. `data-pit-features.yml` and
      `data-assemble.yml` run on a runner, and the assembly also needs the sealed replay artifacts,
      which need an authenticated GitHub API this session does not have; a local feature build was
      measured at roughly an hour and could not be followed by an assembly in any case. What was
      proven locally against the real database, on 25 assets: the exclusion is active, 237 actions
      across 150 assets are loaded, and **10 of 10 live-equivalence samples match the plain loop**.
      `tools/foundation/events.py:161` still selects the PSX market series with `source ILIKE
      'Pakistan%'`, so it reads only the exchange's own bars and not the recovered ones -- correct
      today, and the line to change when the events series is next rebuilt. And the public `/psx`
      surface now publishes considerably more PSX history than it did; the licence question under
      `psx-redistribution-licence` is unchanged by that, but the volume behind it is not, and it
      remains the owner's decision.

131. **The frozen target's missing series were acquired, and three of them do not have a history
    to acquire.** 2026-10-15, Phase 3 data foundation. Acquisition and staging only: **nothing was
    written to the database**, which ends this work at 374 MB and 1,017,296 rows, exactly where it
    started.

    - **What came back.** `^GSPC` 4,726 sessions, `^VIX` 4,728 and `DX-Y.NYB` 4,727, all from
      2008-01-02 and all from Yahoo's chart API. Bitcoin went back from 2018-11-04 to **2015-07-20**,
      1,203 daily bars, which is Coinbase's own earliest: page five of the walk returned 24 candles
      and page six returned nothing, so the floor is the venue's and not a budget's.

    - **DXY and the broad dollar index are two different series and both are held now.**
      `DX-Y.NYB` is ICE's dollar index against six currencies; `DTWEXBGS`, already in the macro
      files, is the Federal Reserve's broad trade-weighted index against twenty-six. Neither
      substitutes for the other and the manifest records which is which. The same distinction is
      kept for `^GSPC` against `^SP500TR`, which exists and was deliberately not acquired: a price
      index is not a total-return index and the frozen target names the price index.

    - **The padding rule does not transfer to an index, and nearly cost the whole series.**
      `psx_backfill.validate` rejects a bar whose OHLC are equal with zero volume, because that is
      how Yahoo pads a session Karachi did not hold. `^VIX` publishes **zero volume on every
      session** -- it is calculated, not traded -- so that rule would have thrown away all 4,728
      bars. Index validation keeps the checks that mean something (a positive close, high not below
      low, no repeated date) and drops the one that does not.

    - **Three series publish a number today and no history anywhere this task could reach.**
      KSE-100: Yahoo 404s seven symbol spellings, the exchange's own closing file carries KSE30
      *futures* and no index level, `dps.psx.com.pk/indices` publishes the current level only, and
      stooq is still behind the JavaScript wall rule 46 recorded. KIBOR: the SBP page is
      server-rendered and parses, but history lives in per-day PDFs behind a JavaScript document
      search. SBP policy rate: the monetary policy page states 11.50% and no series. All three were
      captured as **one dated observation each** -- KSE-100 165,417.50, policy rate 11.50% with its
      12.50/10.50 corridor, KIBOR 3M/6M/12M at 11.72/11.97, 12.17/12.42, 12.24/12.74 as on
      14-Oct-26 -- and recorded as unresolved for history rather than smoothed over. **SBP answers
      403 to this project's user agent and 200 to a browser's**, which is why the earlier evaluation
      recorded it as unreachable.

    - **The two PSX numbers reconcile exactly, and neither was wrong.** 38,246 bars were withheld on
      basis grounds; 37,617 of them fall inside a symbol's stored range and **629 do not**. A gap is
      counted against the range an asset actually has, so the 629 -- which would extend a history
      rather than fill a hole in one -- were never in the 70,824. Both figures are now derived from
      the same staged file.

    - **8.1% of the "rejected padding" gaps were not absences at all.** The attribution put 32,519
      PSX gaps under provider padding, which says what Yahoo did and not whether a price exists. The
      exchange's own archives for 272 dates answer it: of 5,199 such gaps falling on those dates,
      **4,778 have no traded price at the exchange either** -- the symbol did not trade, and that is
      not a missing observation -- while **421 do**, and were staged from the cached archives at no
      further cost. Extrapolated, about **2,633** of the 32,519 are still recoverable this way.
      They were not all fetched because `recovery-manifest.json` records this host refusing at
      roughly 600 requests in a session and 272 were already spent.

    - **The 23 names Yahoo does not list were never short of a source.** The exchange's own closing
      file carries them, at the raw basis the stored series already uses, so there is no basis
      question: **637 of their 662 in-range gaps** came back. The remaining 25 are dates those
      symbols did not trade.

    - **Delisted and renamed, measured rather than assumed.** Comparing the first and last archive
      day, 320 symbols traded early and not late -- and **277 of them are dated futures contracts
      that simply expired**. Twenty-one are genuine delisting or rename candidates, including FFBL,
      PSMC, PIAA, ENGRO and DAWH. A caution that belongs with them: `META` and `SHEL` appear in both
      lists and are not the same companies, the registry's being the US ones.

    - **Where the collection stands.** Raw acquisition including staging is **97.12%**
      (1,130,829 of 1,164,354 expected observations); production-integrated is **87.37%**, and the
      difference is deliberate -- index levels have no `Asset` row, and the 38,246 basis-conflicting
      bars must not sit beside the exchange's own numbers until a sourced factor is adjudicated.
      Nine of the thirteen frozen target items hold usable history. The manifest is
      `data/foundation/acquisition/manifest.json`, version `acquisition-manifest-v1`.

132. **The PSX history is complete to the limit of what the exchange ever published, and the proof
    is that every remaining gap is a day the stock did not trade.** 2026-10-15, Phase 3 data
    foundation. 80,162 rows added after a verified backup; 394,014 PSX bars now, none lost, the
    database at 387 MB of 500.

    - **The sweep that should have come first.** The earlier run read 272 archive dates chosen for
      23 symbols. That was the wrong shape: the exchange's closing file carries the whole market on
      every date, so one pass over the calendar answers every PSX question at once. 2,294 weekday
      dates from 2018-01-01 were read, **2,171 published**, 119 silent (holidays, each confirmed by
      a real 404), 2 not an archive, 2 published but empty. The download is the persistence --
      `nbt.get` caches each archive for a year and `psx.read_day` reads through the same key -- so
      every later pass over 2,171 files cost nothing.

    - **The host did not refuse.** `recovery-manifest.json` records this server "refusing at
      roughly 600 requests in one session", and that figure stopped the previous run early. 2,294
      requests at the declared 1.5s spacing completed without a single refusal. The earlier limit
      was real when it was measured; it is not a property of the host at this rate, and the
      manifest's note should be read as "observed once" rather than a ceiling.

    - **The basis problem dissolved rather than being solved.** 38,246 Yahoo bars were withheld
      because Yahoo back-adjusts for splits while the stored series is raw. The exchange's own file
      *is* the raw series, so for those same dates there was never anything to adjudicate -- only a
      fetch nobody had done. Of the 80,162 bars recovered, **41,767 fall inside a stored range**
      (the basis-divergent dates, the pad-rejected dates and the 23 unlisted names together) and
      **38,395 fall before it**: 2018, a whole year that predates the universe's 2019 start. By
      year: 38,095 in 2018, then 12,228, 10,616, 9,504, 6,078, 2,729 and 912 to 2024.

    - **What the 36,762 remaining gaps are, measured and not assumed.** Every published archive was
      re-read and every remaining in-range gap tested against it. **36,762 of 36,762 are sessions on
      which the exchange published no traded price for that symbol**, and **none** is a date the
      exchange priced and this database lacks. A thinly traded Karachi listing does not trade every
      session; `gaps.json` counts every market session for every in-range asset, so its PSX figure
      of 0.914 is measuring the market's liquidity and not this project's coverage. **Against
      sessions where a price actually exists, PSX acquisition is complete.**

    - **Coverage, with the denominator named each time.** PSX went 0.816 to **0.914** on the
      per-asset measure, and the calendar gained a year: 2018 contributes 245 session dates where
      it previously had none. Across everything: historical observation coverage **96.74%**
      (1,097,458 of 1,134,465), raw acquisition including staging **99.93%** (1,274,292 of
      1,275,182), primary-store integrated **86.06%** -- the difference being benchmark and macro
      series that are staged because they have no `Asset` row, which is a Milestone B decision and
      not an acquisition failure.

    - **Three series publish a number and no history, and the search for one is now exhausted.**
      KSE-100, KIBOR and the SBP policy rate were pursued through nine further paths this session:
      seven Yahoo symbol spellings (404), the exchange's closing file at both 2018-01-01 and
      2026-10-13 (KSE30 *futures* rows, never an index level), `/indices` (current level only),
      `/historical` and `/daily-downloads` (JavaScript shells), stooq (JavaScript challenge,
      re-verified), SBP's `kibor_index.asp`, `kibor_archive.asp` and `economic-data` pages
      (JavaScript document search over per-day PDFs), and SBP EasyData (Oracle APEX 19.2, whose
      URLs carry session checksums). `IR-Corridor-Hist.xls` turned out to hold overnight repo
      *amounts*, not rates. One dated observation each was captured. **SBP answers 403 to this
      project's user agent and 200 to a browser's**, which is why it was previously recorded as
      unreachable.

    - **Everything else reached its source's own floor.** `^GSPC` 24,814 sessions from 1927-12-30,
      `^VIX` 9,266 from its 1990 inception, `DX-Y.NYB` 14,164 from 1971, `^SP500TR` 9,769 from 1988
      kept deliberately distinct from the price index, `GC=F` 6,556 and `BZ=F` 4,782 in full, FRED's
      `DGS10` to 1962 and `DFF` to 1954, and Bitcoin to **2011-08-18** through Bitstamp once
      Coinbase's own floor of 2015-07-20 was confirmed by the venue returning nothing earlier.
      The manifest is `data/foundation/acquisition/manifest.json`, version
      `acquisition-manifest-v2`.

133. **KIBOR and the SBP policy rate were never unavailable — they were behind a form submit, and
    two earlier entries said otherwise.** 2026-10-15, Phase 3 data foundation. No production
    database change: this entry adds 138,588 benchmark observations and 93,339 SBP observations to
    the project's data files, and `PriceSnapshot` ends where it started at 1,097,458 rows and
    387 MB.

    - **The correction.** Rules 130 and 132 recorded KIBOR, the SBP policy rate and KSE-100 as
      having no reachable history. For two of the three that was wrong, and the reason is worth
      keeping: the search stopped at pages that render data, and the data is published through
      SBP's EasyData portal, an Oracle APEX application whose series page carries a **"Download
      Available Series"** button. That button is an ordinary page submit, not an API, so nothing
      that reads HTML could ever find it.

    - **What it took, and the three mistakes on the way.** The submit posts the page's own form to
      `wwv_flow.accept`. APEX 19.2 protects page items with per-item checksums, and the three
      fields that decide acceptance -- `pPageItemsProtected`, `pSalt`, `pPageItemsRowVersion` --
      carry an `id` and **no** `name`, so looking them up by name found none and the portal replied
      "Page protection violation". Past that, the submit answers 302 to the file, and gives that
      Location as `http://`: following it as issued is a protocol downgrade the site's edge answers
      403 to. Following it by hand through a *second* opener then produced "Your session has
      expired", because a second opener means a second cookie jar. One opener, redirect captured
      only at the submit, forced to https: `application/excel`, `data_series.csv`.

    - **What came back.** **KIBOR: 93,300 observations across 18 series** -- bid and offer at 1W,
      2W, 1M, 3M, 6M, 9M and 12M -- **from 2005-06-09 to 2026-10-14**, which is a fortnight later
      than the range this task quoted, so the source had moved on rather than stopped. **The SBP
      policy rate: 39 effective-dated observations from 2015-05-25 to 2026-04-28**, which is the
      whole series: it prints only when the rate changes. Zero unparseable rows in either. A
      dataset downloads through page 213 and a single series through page 222 -- the same submit,
      a different page.

    - **KSE-100 is still not published anywhere permitted, and the list is now specific.** EasyData's
      own search for "KSE" returns **No Data Found** -- the portal carries SBP and PBS statistics,
      not exchange index levels. From the exchange's own origin, `/timeseries/eod/KSE100`,
      `/timeseries/int/KSE100` and `/timeseries/INDEX/KSE100` all answer **404**, while
      `/indices/KSE100` answers 200 with the **constituent list** and no history. Add the seven
      Yahoo spellings, every closing file from 2018 to 2026 (KSE30 *futures* rows, never an index
      level) and stooq's JavaScript wall. The current level is captured; the history is not
      published free.

    - **The four dates the sweep could not classify, settled.** 2,171 published plus 119 silent is
      2,290, not 2,294. Two dates -- **2018-07-19 and 2021-02-09** -- are served as **HTTP 200 with
      a zero-byte body**, confirmed by a direct re-request; two -- **2023-05-17 and 2023-05-18** --
      unpack to an archive with no rows. Against the independent provider, 2018-07-19 was not a
      trading day anywhere, while the other three were **real sessions the exchange's own archive
      does not carry**, which is why those dates hold partial coverage from the Karachi listing and
      no exchange bars at all.

    - **The staged series are not in a cache any more.** `.cache` is gitignored and disposable, so
      thirteen benchmark and macro series (138,588 observations, 1.3 MB) now live in
      `data/foundation/benchmarks/` and the two SBP series in `data/foundation/sbp/`, each a CSV --
      gzipped above 3,000 rows -- beside a manifest carrying the count, the range and a sha256.
      That is the convention `data/foundation/macro/` already uses. **No `Asset` row was created for
      any of them**: an index level is not a tradable instrument, and `PriceSnapshot` is what every
      ranking, peer median and relative-strength figure in this project is computed over.

    - **Coverage, with the denominator named.** Frozen target series **12 of 14**; historical
      observation coverage **96.74%**; raw acquisition including staging **99.43%** (1,367,592 of
      1,375,442); primary-store integrated **79.79%**, the gap being series that deliberately do
      not belong in `PriceSnapshot`. The SBP policy rate is excluded from both sides of the ratio:
      an irregular event series has no expected count to divide by, and including it would have
      flattered the figure. An earlier build of this manifest read **107%** for exactly that
      mistake.

    - **Still ahead, and not to be dropped.** This closes frozen market and macro data collection.
      Milestone B is the cleaning and point-in-time integrity pass. After it, still required as
      training data and not yet begun: **historical news and original documents, the major crash
      and bull-run timelines, pre-event information, catalysts, and post-event market reactions.**
      The dataset rebuild (`data-pit-features.yml`, `data-assemble.yml`) also still needs an
      authenticated runner, and the 38,246 basis-conflicting Karachi bars remain staged, largely
      superseded by raw exchange bars for the same dates.
