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
| Google News | `news.google.com/rss/search` | Works. |
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
