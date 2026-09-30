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

- [ ] Home page: group industry cards by market so the PSX sectors read as their own
      list, and say which currency each group is in.
- [ ] Industry page: `CurrencyNote`, currency passed to `money()`, `HowToRead`.
- [ ] Asset page: currency on prices and size.
- [ ] Product page: "Marketplace and local notes" block, `HowToRead`.
- [ ] Nav: Events and Marketplace links in `app/layout.tsx`.
- [ ] Methodology page: PSX, events, marketplace, and the research walkthrough.
- [ ] `brain.md`: source table rows for PSX, Amazon and eBay; the Reddit window rule;
      the flat-source rule.
- [ ] `README.md`: new jobs, new sections, PSX limitations.
- [ ] `.github/workflows/refresh.yml`: nothing needed, `run.py` owns the job list —
      confirm the 90 minute timeout still fits the PSX backfill.
- [ ] `npm run build` and `npx tsc --noEmit` clean.
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
