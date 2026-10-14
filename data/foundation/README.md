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
| Replay reconciliation (sealed) | artifact `nbt-canonical-checkpoint` | `reconcile_replay.py`, `data-worker-reconcile.yml` | push `ops/reconcile.json` |
| Determinism re-check | check-run annotation | `determinism_check.py`, `data-worker-determinism.yml` | push `ops/determinism.json` |

Walk-forward evaluation infrastructure is `tools/foundation/walkforward.py`. It trains nothing.

## Macro

32 FRED series, each with at least 15 years of history (2010-01 to the latest release). Every row
has `availableAt`, the earliest date the value could have been known, as a stated and conservative
publication lag after the period ends. Real releases are usually earlier, never later, so using
`availableAt` cannot leak. `USREC` (the NBER recession flag) has no `availableAt` and is an ex-post
label, never a feature. Revision history comes from ALFRED snapshots taken on the 14th and 28th of
each month, so a first-seen date is an upper bound on the real release (at most about 14 days late).

Shorter than 15 years, reported and not counted: the two ICE credit-spread series (FRED carries a
rolling three years under ICE's licence). The LBMA gold series is no longer served.

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
