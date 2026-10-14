# Data foundation

Public, sourced datasets and the tools that build and check them. Nothing here is a model, and
nothing here is loaded into a production database. Anything derived from a licensed price feed is
built inside GitHub Actions, sealed with `WORKER_ARTIFACT_KEY`, and never committed.

Every claim below is enforced by `tests/test_foundation.py`, which fails if a threshold is not met.
A dataset whose file is absent is skipped by the test, never passed.

| Dataset | Where | Built by | Re-run |
| --- | --- | --- | --- |
| Macro series, availability timestamps | `macro/*.csv`, `macro/manifest.json` | `tools/foundation/macro.py history` | `python tools/foundation/macro.py history` |
| Macro vintages (revisions) | `macro/vintages/*.jsonl` | `macro.py vintages` (resumable) | `python tools/foundation/macro.py vintages` |
| Trading principles | `principles/principles.json` | `principles_src.py` + `principles.py` | `python tools/foundation/principles.py` |
| Event corpus | `events/events.json` | `events_src.py` + `events.py` | `python tools/foundation/events.py` |
| Survivorship profile | `survivorship/report.json` | `survivorship.py` | `python tools/foundation/survivorship.py` |
| Independent price verification | `price_verification/report.json` | `verify_prices.py` | `python tools/foundation/verify_prices.py` |
| Point-in-time features (sealed) | artifact `nbt-pit-features-*` | `pit_features.py`, `data-pit-features.yml` | push `ops/pit.json` |
| Joined dataset (sealed) | artifact `nbt-dataset-*` | `assemble.py`, `data-assemble.yml` | push `ops/assemble.json` |
| Coverage gaps | check-run annotation, sealed `coverage/` | `coverage_gaps.py` (in `data-assemble.yml`) | push `ops/assemble.json` |
| Principle evaluation | check-run annotation, sealed `evaluation/` | `evaluate_principles.py` (in `data-assemble.yml`) | push `ops/assemble.json` |
| Replay reconciliation (sealed) | artifact `nbt-canonical-checkpoint` | `reconcile_replay.py`, `data-worker-reconcile.yml` | push `ops/reconcile.json` |
| Determinism re-check | check-run annotation | `determinism_check.py`, `data-worker-determinism.yml` | push `ops/determinism.json` |

Walk-forward evaluation infrastructure is `tools/foundation/walkforward.py`. It trains nothing.

## Run order

The sealed pipeline has one order, because each step verifies the one before it. Each is started
by committing a change to its request file on `main` (bump the `nonce`); `workflow_dispatch` is
equivalent but needs the web UI.

1. **Replay** — `data-worker.yml`, dispatched with `checkpoint=nbt-canonical-checkpoint`. It
   chains its own slices until no sessions remain. Each slice's counts appear as a check-run
   annotation.
2. **Reconcile** — push `ops/reconcile.json`. Rebuilds the canonical checkpoint from the persisted
   outputs, trusting only runs whose replay code matches the current tree, and re-dispatches the
   worker for whatever is still missing. Repeat until it reports `missingOrInvalid: 0`.
3. **Determinism** — push `ops/determinism.json`. Re-replays a seeded, year-stratified sample and
   requires byte-identical output. This is the leakage test that time can run and a unit test
   cannot.
4. **Features** — push `ops/pit.json`. Rebuilds the point-in-time factors and analogs.
5. **Assemble** — push `ops/assemble.json`. Joins outcomes, features and replayed setups, then
   runs the coverage-gap, survivorship and principle-evaluation reports in the same job.

Steps 1 to 3 must be green before step 5 is meaningful: assembling against an unreconciled replay
would join setups whose provenance is unknown.

## Where these jobs run, and why

Anything that reads the database runs inside GitHub Actions, not from a laptop. The measured
reason: the Supabase session pooler allows 15 clients, and one local analysis started while a
replay slice was in flight exhausted it (`EMAXCONNSESSION`, 2026-10-14 12:19 UTC), after which the
standby connection timed out too. A single runner holding a single connection, scheduled after the
heavy step, is the shape that fits the free tier. The replay worker's own lane is serialised by its
concurrency group for the same reason.

## Macro

32 FRED series, each with at least 15 years of history (2010-01 to the latest release). Every row
has `availableAt`, the earliest date the value could have been known, as a stated and conservative
publication lag after the period ends. Real releases are usually earlier, never later, so using
`availableAt` cannot leak. `USREC` (the NBER recession flag) has no `availableAt` and is an ex-post
label, never a feature. Revision history comes from ALFRED snapshots taken on the 14th and 28th of
each month, so a first-seen date is an upper bound on the real release (at most about 14 days late).

Shorter than 15 years, reported and not counted: the two ICE credit-spread series (FRED carries a
rolling three years under ICE's licence). The LBMA gold series is no longer served.

## Coverage, and the gap the per-asset figure hid

`coverage/gaps.json` counts sessions where an asset's own market traded and the asset has no bar.
By that measure the universe is 98.3% to 100% covered everywhere. That measure is not enough on its
own: it compares each asset with a calendar built from the same data, so a market that was fetched
monthly looks fully covered.

`calendarCompleteness` is the check that catches it, and PSX is what it catches. Measured against
the weekdays in each year, the stored PSX history holds **4.6% to 5.0% of them for 2019 through
2023**, 45% in 2024, and reaches 95.8% only in 2025. US is above 96% throughout. So for 226 of the
616 assets — 37% of the universe — the pre-2024 history is monthly, and a 20-session average over
monthly-spaced bars is a 20-month average under a daily name. Nothing in a row revealed that, so
`pit_features.py` now emits `spanDays` (the calendar days a window really covers) and the dataset
carries `dataQuality.windowIsNotDaily`.

`coverage/psx_recovery.json` measures the repair. Yahoo serves the Karachi listing (`SYMBOL.KA`)
with full daily history from 2019 — about 261 bars a year where the exchange file holds 13 — so the
gap is recoverable from a free source. Filling it writes to `PriceSnapshot` and belongs to the
ingest lane that owns it; this is the measurement, not the repair.

## Principles

Each principle names a published finding, the exact signal that would test it on data this
repository stores, the horizon, the expected sign and the pre-registered comparison. Every
citation is checked against Crossref (title fragment, first author, year within one). Where the
DOI first recorded was wrong, it was replaced only by a Crossref search result that passes the
same test, and the original is kept. This verifies the citation, not the finding: the one-sentence
`finding` is a paraphrase and no principle is anything but `untested` until a walk-forward result
exists. `testable_now` is True only when every input is stored; fundamentals, term structures and
foreign short rates are not.

## Events

Each candidate event is checked for: the claimed date written out in a Wikipedia article found by
search; the same date on the article's Wikidata item; an official document where one exists (a
Federal Reserve statement or speech, a BLS release) that contains the date; and the largest
absolute return z-score of the event's own instrument in the window one day before to three days
after, computed from this repository's prices. The market test shows the date is a date something
moved, not that the event caused the move. Tiers and evidence groups are stored with every event;
an event with no matching article is never counted, however well known.

## Survivorship

No stored asset has a series that ends before today, so the universe contains no company that was
delisted, acquired or failed. The 59 inactive assets were dropped from the pool for low turnover,
not delisting. Quantified against the S&P 500's own removal list since 2019 in `survivorship/`.

## Prices

Stored stock and ETF closes are Yahoo's dividend-adjusted close, not the price that traded
(measured against Yahoo's own `close` and `adjclose` fields). They are rewritten as dividends are
paid. Every feature built here is scale-free over its window, so the adjustment does not change a
feature; absolute levels are not traded prices. See `price_verification/report.json` for the
second-source comparison and for what could not be verified independently.

Each class is checked against a provider that did not supply the stored value: US stocks and ETFs
against Nasdaq, crypto against Binance (falling back to Bitstamp), FX against the ECB's euro
reference rates crossed through EUR, and PSX shares against Yahoo's Karachi listing (`SYMBOL.KA`,
quoted in PKR), which is a different provider from the exchange's own daily file. Classes whose
adjustment bases differ are compared as daily returns rather than levels. Commodity futures remain
unverified: the stored `=F` contracts have no free keyless counterpart, and a spot series is a
different instrument.

## Unadjusted corporate actions

`price_verification/unadjusted_actions.json`. A stored series that was never rescaled for a split
carries a one-day move no holder experienced, and every factor measured across that date — the
return, the robust z, the analog match — is wrong for that asset in any window containing it.

239 candidates across 152 of the 616 assets. Of 60 checked against a second provider, 52 showed an
ordinary day there while the stored series showed a collapse, 2 were real moves both providers saw,
and 6 had no second source. Mostly PSX (173), where the exchange's daily file is not back-adjusted,
but 22 US names too: the lane fetches incrementally, so a bar stored before a split keeps the old
scale while the provider silently rescales its own history behind it.

The dataset flags these rather than dropping them — `dataQuality.unadjustedActionInWindow` per row,
counted in the manifest — because a row is still correct about everything that does not cross the
action. Repair means re-fetching an asset's full history at the current scale, which
`tools/recover_asset.py SYMBOL --since ... --write` does for the Yahoo-sourced names; it is a
production write and is left for the owner.

## Principle evaluation

`evaluate_principles.py` runs pre-registered rules — each mapped from a principle's stated signal
to the stored point-in-time features, written before any result was seen — through the purged
walk-forward evaluator, against buy-and-hold and a reproducible coin flip, net of the low, base
and high cost assumptions. A rule is PASS only when it beats both controls, makes money at the
base cost, has an interval above zero, and clears a 0.95 deflated Sharpe probability against the
running trial count. Most will fail; a corpus of honest failures is the deliverable. Nothing here
is model training and no result promotes a rule into the live engine.
