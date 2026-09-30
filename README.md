# NextBigThing

A read only site that ranks what is gaining ground, using only free public data, and
names the source and the as of date of every number it shows.

Two things are measured separately:

- **Markets.** 70 assets across 7 industries, ranked by size at the end of 2021 against
  size now, by price return, and by 24 month return measured against their own industry.
- **Products.** 30 consumer products, read from Google Trends, Wikipedia pageviews,
  Hacker News, Reddit and Google News on short, stated windows.

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
| `python jobs/run.py daily` | Prices and news, then rankings, then confidence, then the written lines. |
| `python jobs/run.py weekly` | The daily run plus all five product signal sources. |
| `python jobs/stats.py` | Row counts and newest stored date per table. |
| `python jobs/confidence.py all` | Grades every ranking row and product. Runs on its own too. |
| `python jobs/analysis.py` | Rewrites the `Analysis` table from stored numbers. |

Individual scripts take a source name, for example
`python jobs/prices.py crypto` or `python jobs/signals.py reddit`.

`confidence.py` runs after `rank.py` and before `analysis.py`, so the written lines are
generated from the same grades the page shows. `analysis.py` grades products again after
recomputing demand scores, which keeps the badge and the score beside it in step.

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

## Refresh schedule

`.github/workflows/refresh.yml` runs `daily` at 07:17 UTC and `weekly` on Monday at 07:43
UTC, and can be triggered by hand with a `seed`, `daily` or `weekly` choice. It needs two
repository secrets:

- `DATABASE_URL`, the Neon connection string. The jobs write, so this one needs an owner
  or writer role.
- `CONTACT_EMAIL`, optional, used only if identified requests are ever filed.

Product signals run weekly rather than daily because Reddit and Wikipedia rate limit, and
asking them every day mostly returns `429` and no new data.

## Deployment

Vercel builds the site. Set `DATABASE_URL` in the project environment, and the front page,
industry, product, asset and methodology routes are revalidated hourly.

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

Yahoo Finance through `yfinance`, Binance public klines, CoinPaprika, Google Trends,
Wikipedia pageviews, the Hacker News Algolia API, Reddit public search RSS and Google News
RSS. X is not covered, because no free public endpoint can supply it.

`brain.md` holds the verified source table, the ranking formulas and the rules for
changing any of them.
