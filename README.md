# NextBigThing

> **Picking this up after a break? Read [RESUME.md](RESUME.md) first.** It states where work
> stopped, what is verified, the one item still open, and what you have to supply before any
> job will run. `HANDOFF.md` is the detail behind it.

A read only site that ranks what is gaining ground, using only free public data, and
names the source and the as of date of every number it shows.

Four things are measured separately:

- **Markets.** 160 assets across 17 industries, ranked by size at the end of 2021 against
  size now, by price return, and by 24 month return measured against their own industry.
  Nine industries are US listings and crypto; eight are Pakistan Stock Exchange sectors,
  quoted in rupees and labelled as such.
- **Products.** 30 consumer products, read from Google Trends, Wikipedia pageviews,
  Hacker News, Reddit and Google News on short, stated windows.
- **Event windows.** A hand written list of dated public events, and the largest measured
  price moves in the 14 and 30 days after each. The moves are measured. Why anything moved
  is not, and the site never says an event caused a price change.
- **Marketplace rankings.** The first page of Amazon's public Best Sellers charts for nine
  categories, stored as published, with each listing's movement against the previous
  stored run. Deliberately kept out of the product demand scores.

Nothing is forecast and nothing is estimated. Where a free source does not publish a
number, the site says so instead of filling the gap.

## How it is put together

The site reads a database and nothing else. All fetching happens in Python scripts that
write rows with an explicit `source` and `periodEnd`. There is no API route, no fetch on
render, and no browser side chart library.

```
jobs/       Python data jobs, run on a schedule
prisma/     schema and migrations
app/        Next.js App Router pages, server components only
lib/        Prisma client, queries, formatting
components/ small server rendered UI pieces
```

Pages read precomputed rows. If a job fails, the previous rows stay and the freshness
table on the front page shows the date of the last successful run.

## Running it locally

1. Install Node and Python 3.12.
2. `npm install`
3. `pip install -r requirements.txt`
4. Copy `.env.example` to `.env` and paste the Neon connection string. The same
   `DATABASE_URL` is used by the jobs and by the site.
5. Apply the schema and generate the client:

   ```
   npx prisma migrate deploy
   npx prisma generate
   ```

6. Fill the database once: `python jobs/run.py seed`
7. Refresh everything: `python jobs/run.py daily`
8. `npm run dev`

## The data jobs

| Command | What it does |
| --- | --- |
| `python jobs/run.py seed` | Industries, assets, products, links. Idempotent. |
| `python jobs/run.py daily` | Prices and news for both exchanges, then rankings, confidence, event windows and the written lines. |
| `python jobs/run.py weekly` | The daily run plus the full PSX backfill, all five product signal sources and the marketplace charts. |
| `python jobs/psx.py recent` | PSX closes: the snapshot dates and the last 120 days. |
| `python jobs/psx.py full` | The above plus a monthly grid back to 2019, for the charts. |
| `python jobs/events.py` | Seeds the event list and measures the window after each one. |
| `python jobs/marketplace.py` | Amazon Best Sellers, first page of nine categories. |
| `python jobs/stats.py` | Row counts and newest stored date per table. |
| `python jobs/confidence.py all` | Grades every ranking row and product. Runs on its own too. |
| `python jobs/analysis.py` | Rewrites the `Analysis` table from stored numbers. |
| `python jobs/thesis.py` | Compares each held directional read against the day it first appeared. |
| `python jobs/attribution.py` | Splits each recent move into market, industry and asset specific parts. |
| `python jobs/graph.py` | Walks today's flagged catalysts two hops over stored relationships. |
| `python jobs/intraday.py` | Five minute bars for the active set, then the derived intervals. |
| `python jobs/intraday.py derive` | Rebuilds 15/30/60 minute bars from stored five minute ones. |
| `python jobs/horizons.py` | The intraday and longer term reads, then target ranges for every horizon. |
| `python jobs/investigate.py` | Looks into every move that is unusual for the asset that made it. |
| `python jobs/schemacheck.py` | Exits non-zero if the database is behind this checkout's migrations. |

Individual scripts take a source name, for example
`python jobs/prices.py crypto` or `python jobs/signals.py reddit`.

`psx.py` caches hard: a published closing file for a past day never changes, so only the
last fortnight is refetched and a second `full` run costs almost nothing. The first one is
around 300 requests and takes a few minutes.

`confidence.py` runs after `rank.py` and before `analysis.py`, so the written lines are
generated from the same grades the page shows. `analysis.py` grades products again after
recomputing demand scores, which keeps the badge and the score beside it in step.

`thesis.py`, `attribution.py` and `graph.py` read stored rows and make no request, so they
sit in the release lane rather than the refresh lane. The order between them is a real
dependency: `thesis.py` needs the `AssetSetup` row `setup.py` has just written, and
`graph.py` walks out from the catalysts `human.py` flagged earlier in the same run.

## Intraday, and what it costs

Five minutes is the canonical interval and 15, 30 and 60 are derived from it. The aggregation is
exact — first open, last close, max high, min low, summed volume — and a group missing any
component bar is skipped rather than assembled, because an hour built from nine of its twelve
bars is a quieter hour than the one that happened.

Nothing polls every asset every minute. An **active set** is chosen from stored rows before any
request is made, and a hard per-run request ceiling bounds the job whatever the selection says.

Two numbers worth knowing, both measured rather than estimated:

- One run fetching a **month** of five minute bars stored 201,726 rows and took `IntradayBar` to
  **85 MB** — larger than the entire seven year daily history for all 160 assets (71 MB), for
  data nothing queried beyond the newest two sessions. The fetch window is now five days.
- One minute bars are **not fetched**. Every reader in this repository queries `interval = 5`,
  so 1m was storage spent on nothing. The capability is kept in the code path — fetch,
  normalisation, session accounting and aggregation all handle it — behind `FINE_SLICE = 0`.

Intraday bars are swept after ten days. The daily series is never swept: it is the permanent
record, and retention here is by value rather than by age alone.

`jobs/intraday.py` is also the one job in this repository that writes thousands of rows at a
time, so it batches with `executemany`. One statement per bar against a pooled remote database
turned a twenty asset run into minutes of pure latency.

## Migration has one path

`schema.yml` applies migrations and nothing else does. The data lanes run `jobs/schemacheck.py`,
which compares the migration directories against `_prisma_migrations` and exits non-zero with
the pending names if the database is behind. It holds no writer privilege and issues no DDL, so
it cannot race anything.

This replaced a real failure: `refresh.yml` used to migrate too, and on a push that touched it
both workflows ran `prisma migrate deploy` against one database in the same second from two
different concurrency groups. A test asserts that exactly one workflow contains a
`prisma migrate deploy` run line.

`thesis.py` never recomputes the opening day's conditions. It reads the row that was written
on that day, because recomputing them would answer "what would we have said then, knowing
what we know now" — which is the one question a frozen reason exists to prevent. A broken
thesis is terminal: once a close has passed the level the opening day named, the row is left
alone so a later recovery cannot quietly erase it.

HTTP responses are cached under `.cache/` with a per source time to live, so a rerun does
not hammer a source. Jobs send a real User-Agent, back off on `429` and `403`, and treat a
failed source as a missing value rather than a zero.

## Confidence

Every ranking row, product and analysis line carries a grade of high, medium, low or none,
with the reason stored beside it. The grade describes how well evidenced the figure is, not
which direction it points.

- **Rankings** are graded down when the industry mean sits far from its own median, because
  a skewed mean is not a fair description of a typical peer, and when the volume check fails
  or there are too few peers to compare against. The published rank is never changed to suit
  the grade; the caveat is disclosed instead.
- **Products** are graded on how many of the five sources answered and whether they point
  the same way as the average. Sources that split up and down, or where the mean and median
  land on opposite sides of zero, cap the grade at medium.
- **Small denominators are separated from bad arithmetic.** A Reddit percentage on a base of
  fewer than 5 posts is never published, because 1 post against 0 is a rounding artifact. A
  percentage on a base of 5 to 9 posts is published, because the arithmetic is right, but it
  caps the grade at medium, because at that scale a single post is 10 to 20% of the reading.
  The number and the confidence claim are judged separately.

Full rules and the measured data behind them are in `brain.md`.

## Pakistan Stock Exchange

Prices come from the exchange's own end of day file,
`dps.psx.com.pk/download/mkt_summary/<date>.Z`, a ZIP holding one pipe delimited line per
listed symbol. No key, no cookie, nothing solved, and files exist back past 2019-12-31, so
every snapshot date the site ranks on is covered. It is the exchange's own record rather
than a scrape of a rendered page, so a layout change cannot quietly alter a number.

Two limits are worth knowing before reading those pages:

- **Size exists for the latest close only.** The share count on the exchange's company
  page is a current figure with no history behind it. Multiplying it by a 2021 price would
  produce a market capitalisation that was never true, so none is written for any earlier
  date and the pre-AI size table shows these sectors as blank. This is the same handling
  crypto already gets.
- **Returns are in rupees and are not converted.** A 40% gain over a period when the
  currency weakened is not a 40% gain in purchasing power. Rankings only ever compare
  assets inside one industry, so a Karachi listing is measured against Karachi peers and
  the currency never enters the comparison, but a figure read on its own still carries it.

## Event windows

`jobs/events.py` holds a short list of dated events, each with a factual summary and a
source URL for the date, and measures every asset's price change over the 14 and 30 days
after. There is no detector and there will not be one: detecting events from the price
series would select whichever dates sit next to large moves, and every row would then
appear to confirm a relationship the selection had created.

Adding an event is an edit to `EVENTS` in `jobs/events.py`. The section never claims
causation, and `jobs/analysis.py` builds its sentences so they stay true if an event
turned out to have no bearing on the market at all.

## Marketplace rankings

`jobs/marketplace.py` reads the first page of Amazon's Best Sellers chart for nine
categories and stores it as published, with each listing's movement against the previous
stored run. eBay is not stored: its sold and completed search returns 403 to an ordinary
request, and there is no free public endpoint behind it.

These rows never enter a product's demand score. A search trend says people are looking; a
bestseller rank says one listing is outselling others in its category. Averaging them
would produce a number whose meaning changed week to week depending on which source
answered.

Only the first page of each chart is read, because the rank counter restarts on page two
and using it would mean guessing an offset. An unrecognised category slug does not return
404, it quietly serves a different category's chart, so every slug in `CATEGORIES` was
fetched and parsed before being added.

## Refresh schedule

`.github/workflows/refresh.yml` runs `daily` at 07:17 UTC and `weekly` on Monday at 07:43
UTC, and can be triggered by hand with a `seed`, `daily` or `weekly` choice. It needs two
repository secrets:

- `DATABASE_URL`, the Neon connection string. The jobs write, so this one needs an owner
  or writer role.
- `CONTACT_EMAIL`, optional, used only if identified requests are ever filed.

The workflow applies `npx prisma migrate deploy` before it runs any job. This is the only
automated place the schema is migrated, because it is the only automated place that holds a
writer credential, and a job cannot write to a table that does not exist yet.

### `main` is the branch

One branch, and it is `main`. It is what Vercel deploys to production and what
`.github/workflows/schema.yml` triggers on. `master` still exists and is not maintained.

This matters more than a naming preference, because GitHub runs `schedule` and
`workflow_dispatch` **only from the repository's default branch**, and it takes both the
workflow file and the checked-out code from there. So while the default is still `master`,
the nightly refresh runs whatever `master` last held — which is fine today, because the two
point at the same commit, and wrong the moment `main` moves ahead.

**The repository default has to be set to `main`** for the schedule to keep running current
code: Settings → Branches → Default branch. Until that is done, a change to a job in `main`
will not reach the nightly run.

Product signals run weekly rather than daily because Reddit and Wikipedia rate limit, and
asking them every day mostly returns `429` and no new data.

## Deployment

Vercel builds the site. Set `DATABASE_URL` in the project environment, and the front page,
industry, product, asset and methodology routes are revalidated hourly.

Nothing in the Vercel build touches the schema, and it must stay that way: the role Vercel
holds is read-only and cannot run DDL. So a release that adds a table has an order to it.
The migration goes first, from the writer role — the refresh workflow does this, or
`npx prisma migrate deploy` from a local `.env` — and the deploy follows. A build that runs
first fails while Next.js collects page data, because the pages query their tables at build
time. That failure costs nothing: Vercel keeps serving the previous deployment until a build
succeeds.

The site only ever reads, so the `DATABASE_URL` Vercel uses is a dedicated read-only role
(`nbt_readonly`), not the connection string the jobs write with. A leaked read-only
credential cannot change a row. The role is granted `connect`, schema `usage` and `select`
on every table in `public`, plus `alter default privileges ... grant select on tables`, so a
table added by a later migration stays readable to the site without a second manual step.

To recreate it after a credential rotation, connect once with the owner role and run:

```sql
CREATE ROLE nbt_readonly LOGIN PASSWORD '<new password>'
  NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
GRANT CONNECT ON DATABASE neondb TO nbt_readonly;
GRANT USAGE ON SCHEMA public TO nbt_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO nbt_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO nbt_readonly;
```

Then set Vercel's `DATABASE_URL` to the same host and database with that role's credential.
Keep the local `.env` and the GitHub secret on the writer role.

## Data sources

Yahoo Finance through `yfinance`, Binance public klines, CoinPaprika, the Pakistan Stock
Exchange data portal, Google Trends, Wikipedia pageviews, the Hacker News Algolia API,
Reddit public search RSS, Google News RSS and Amazon Best Sellers.

X is not covered, because no free public endpoint can supply it. eBay is not covered,
because its completed listings search returns 403. Daraz, OLX and Facebook Marketplace
publish no free ranking endpoint, so where a local Pakistani angle matters the product
pages list the checks a reader has to make by hand rather than showing a number that does
not exist.

`brain.md` holds the verified source table, the ranking formulas and the rules for
changing any of them.
