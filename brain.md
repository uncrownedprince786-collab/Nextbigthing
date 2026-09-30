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

## Rules for changes
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
