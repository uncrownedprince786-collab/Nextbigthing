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
