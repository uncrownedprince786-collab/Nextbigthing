# Expansion in progress

Working notes for the branch `expand-psx-events-marketplace`. **Delete this file when the
list below is finished** — it is a scratch pad, not documentation.

Nothing on this branch has been run against a database. Every HTTP source was verified
live before code was written against it; none of the SQL has executed.

## Done

- [x] **Fix: Reddit window bias.** `jobs/signals.py` compared a 30 day count with a
      90 day count taken from 180 to 90 days ago. Steady discussion read as -67% every
      run and the 60 days in between were measured by nobody. Windows are now adjacent
      and the longer one is converted to a rate first.
- [x] **Fix: a flat source counted as a vote down.** `summarise()` in
      `jobs/confidence.py` derived `down = answered - up`, so a source reading exactly
      0.0 was tallied as pointing down and `flat` was always 0. The product page already
      handled zero correctly, so the badge and the page disagreed.
- [x] **Fix: industry news could not be shared between industries.** The partial index
      from the previous migration keyed the industry partition on `url` alone. Migration
      `20260930181000_news_industry_dedupe` keys it on `("industryId", url)`, and the
      `ON CONFLICT` target in `jobs/prices.py` follows it.
- [x] **Fix: `skew` shadowing** in `jobs/confidence.py` — declared as `dict[str, float]`,
      used as a dict of lists, then rebound to a float inside the loop.
- [x] Schema: `Industry.market`, `Industry.currency`, `Asset.currency`, `Event`,
      `EventImpact`, `MarketplaceItem`, `AnalysisKind.eventImpact`, `Analysis.eventId`.
      Migration `20260930182000_markets_events_marketplace`. `prisma validate` passes.
- [x] Seed: Automobile and Software & Cloud (10 each), 8 PSX sectors (70 assets).
      17 industries, 160 assets, no symbol in two industries.
- [x] `jobs/psx.py` — PSX daily closes from the exchange's own closing files.
- [x] `jobs/events.py` — 8 seeded events, impact windows at 14 and 30 days.
- [x] `jobs/marketplace.py` — Amazon Best Sellers, 9 verified categories.
- [x] `jobs/run.py`, `jobs/stats.py` wiring.
- [x] `lib/format.ts` currency-aware `money()` and `price()`.
- [x] `components/ui.tsx` — `HowToRead`, `CurrencyNote`.
- [x] `lib/queries.ts` — event and marketplace queries.
- [x] `app/events`, `app/event/[slug]`, `app/marketplace` pages.

## Left to do

- [x] Home page grouped by market, with a currency note per group.
- [x] Industry page: `CurrencyNote`, currency through `money()`, `HowToRead`.
- [x] Asset page: currency on prices and size.
- [x] Product page: "Marketplace and local notes" block, `HowToRead`.
- [x] Nav: Pakistan, Marketplace and Events links.
- [x] Methodology: a section per new source plus the seven step research walkthrough.
- [x] `brain.md` and `README.md`.
- [x] `next build` reaches "Compiled successfully" and "Finished TypeScript". It then
      fails at "Collecting page data" because there is no database reachable from here,
      which is expected and is the only failure.

### Still open

- [ ] **Nothing has been run against a database.** No migration has executed, no job has
      written a row. Do this first, on a scratch database rather than the live one:
      `npx prisma migrate deploy`, then `python jobs/run.py seed`, then
      `python jobs/psx.py recent`, `python jobs/events.py`,
      `python jobs/marketplace.py`, then `python jobs/run.py daily`, then
      `python jobs/stats.py` to see the per-market coverage line.
- [ ] Watch for these three on that first run, they are where a mistake would surface:
      - `ALTER TYPE "AnalysisKind" ADD VALUE 'eventImpact'` — allowed inside a transaction
        on Postgres 12+, but the new value cannot be *used* in the same transaction. The
        migration only adds it, so this should pass; if Prisma complains, split it out.
      - `close_near()` in `jobs/events.py` orders by `abs(date - %s::date)`. Verify the
        cast behaves on Neon as it does on stock Postgres.
      - `jobs/psx.py` `full` is around 300 requests on a cold cache, roughly 8 minutes.
        The workflow's 90 minute timeout has room, but confirm it on the first real run.
- [ ] `HowToRead` on `app/products/page.tsx` — the only page in the teaching layer that
      did not get one. The detail page at `app/product/[slug]` has it.
- [ ] Open a pull request from this branch, or merge it.
- [ ] Delete this file.

## Known limitations to state in the final write-up

- PSX market capitalisation exists for the latest close only. The exchange publishes a
  current share count with no history, so no pre-AI size is written for these sectors.
- PSX returns are in rupees. A rupee return over a period of depreciation is not the same
  quantity as a dollar return, and no conversion is applied.
- Amazon gives the first 30 positions of a category. The rank counter restarts on page
  two, so an offset would have to be guessed.
- eBay returns 403 to an ordinary request. Not used.
- Event impacts are price moves inside a window. No causation is measured or claimed.
