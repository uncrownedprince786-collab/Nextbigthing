# Crypto forecast lane — state at 2026-10-21, and what is left

Written to be picked up cold. Everything below is in the repository and deployed unless it says
otherwise.

Live: <https://nextbigthing-nu.vercel.app> · first commit of this work `7441a06`.

---

## 1. What now works

**The journey.** Home → Crypto → the coin list → a coin → *how long are you asking about* → that
coin's chart and a direction, all on the asset page.

- `/crypto` leads with a directory of **all 76 registry coins** (`components/assetDirectory.tsx`).
  Before this, 66 were listed and the 10 outside the active pool appeared nowhere on the site.
  The analysis lists below it are unchanged — the pool is still what carries a call.
- `/asset/<slug>` for a crypto name renders `components/cryptoBrain.tsx`: a note saying **how long
  you are asking about is not which way it goes**, seven duration buttons, and nothing answered
  until one is chosen. Verified on all 76 coin pages (200, picker present).
- The chosen window renders the question and the answer side by side, then a chart drawn from the
  **exact bars the model read** with the horizon shaded (`components/forecastChart.tsx`).
- `?h=` drives it, so every state is a shareable URL. The older `?style=` picker still serves the
  four non-crypto markets.

**The models.** Binary UP/DOWN — the sign of the forward return, no FLAT class, no row converted
into a direction. Fourteen lanes fitted, **five earn a direction**:

| family | window | test acc | majority | day-blocked 95% CI | WF | badge |
|---|---|---|---|---|---|---|
| btc | 5 min | 0.5153 | 0.5014 | [+0.0088, +0.0198] | 5/5 | LOW |
| btc | 15 min | 0.5270 | 0.5030 | [+0.0169, +0.0316] | 5/5 | MEDIUM |
| btc | 1 hour | 0.5267 | 0.5027 | [+0.0117, +0.0360] | 5/5 | MEDIUM |
| crypto | 5 min | 0.5314 | 0.5020 | [+0.0243, +0.0345] | 5/5 | MEDIUM |
| crypto | 15 min | 0.5246 | 0.5008 | [+0.0149, +0.0328] | 5/5 | MEDIUM |

The other nine (btc h4/d1/d5/d20, crypto h1/h4/d1/d5/d20) are **refused** and each says which
pre-registered gate it failed. Every session-and-longer horizon failed: the bootstrap interval
spans zero on all of them, pooled across 65 coins as well as on Bitcoin alone.

### The 90% target has NOT been met

The best lane is **53.1%** on its holdout. That is a real, significant edge — the intervals
exclude zero, the walk-forward is 5/5, both directions are predicted — and it is nowhere near the
90% the project set. The card on the page says this in those words. Nothing anywhere is presented
as though the target were met. Do not let a later change quietly imply otherwise.

**Data.** `tools/foundation/crypto_intraday.py` collected and validated 420,463 Bitcoin 5-minute
bars (99.996% complete, one 16-bar gap), 4-hour history for 65 coins back to 2017, and 5-minute
history for 31. Every rejection is counted by reason; the corpus manifests hold the completeness
record and a cross-venue check against Coinbase (median |diff| 0.13%).

**The loop.** `BrainForecast` / `BrainForecastOutcome` (migrations `20261021000000`,
`20261021010000`). The shown forecast is written keyed on the bar it was read from, so a reload
inside one bar writes nothing and the row that is graded is the row that was seen.
`jobs/forecast_score.py` grades only once `maturesAt` has passed, reads the venue bar at that
instant rather than the newest, records lateness, and is scheduled hourly by
`.github/workflows/cron-forecast-score.yml`. Proven end to end: 16 forecasts graded.

**Guards.** `tests/intradayParity.test.ts` compares the TypeScript serving features against the
Python definition on real bars and fails above 1e-9. `tools/ui_audit.py` walks the journey on the
live site and reads the panel's own `data-forecast` state, so a page that renders the picker and
then says nothing is a failure rather than a 200.

---

## 2. Open, and what I would do next

### a. Binance is blocked from Vercel — every production forecast is `degraded`

Measured on the deployed site: **every** forecast fell through to **Kraken**. Binance's klines are
the only free feed carrying taker-buy volume and a trade count, so falling past it imputes
`tbi1`, `tbi12`, `tbi48` to neutral — three of forty-one features the models were *trained* with.
The page says so and marks the forecast degraded, which is correct, but the served model is not
reading the inputs it was fitted on.

Already written and committed but **not yet verified in production**: a second venue entry for
`data-api.binance.vision`, Binance's public market-data host, placed directly after
`api.binance.com` in `lib/cryptoBars.ts`. Gap-patching now skips a venue of the same `family`, so
a mirror is never asked to fill a hole its own series has.

**Next step:** hit `/api/forecast?symbol=btc-bitcoin&h=m5` on the deployed site and read
`data.venue` and `data.quality`. If it says `Binance (public data mirror)` and `ok`, the problem
is solved. If it is still Kraken, the mirror is blocked too and the options are: retrain the
served models without the three taker features (so the serving inputs match the training inputs),
or add a venue that publishes order flow and is reachable from Vercel.

### b. Latency

The asset page answers in **7–10 s** on the deployed site, and **almost none of that is the
forecast** — it is the page's own seventeen reads against a free-tier pooler capped at two
connections. `/asset/btc-bitcoin` with no window is as slow as with one.

`app/api/forecast/route.ts` was added so the direction path can be measured and consumed on its
own; it runs the same `forecastFor` → `recordForecast` pair the page does. **It has not been
timed in production yet** — do that first, then decide whether the page needs the forecast moved
behind that route.

### c. Smaller things

- 15 of the graded outcomes carry `latenessMs = -1`. A bar's `close_ms` is its last millisecond,
  so the instant it ends is `close_ms + 1`; that is fixed, and those rows predate the fix. They
  are genuine forecasts genuinely graded and were left rather than edited.
- The prospective record holds 26 forecasts from my own development traffic. No rate is shown
  under 30 graded, so nothing misleading is displayed, but the first real numbers will include
  them.
- `GRASS` and other thin coins refuse with "121 missing bars inside the 289-bar window" — Coinbase
  omits candles with no trades. Correct behaviour; a 5-minute model fitted on continuously-traded
  pairs should not be applied there anyway.
- There is no search box anywhere on the site. The directory plus the browser's find-in-page
  covers lookup; a filter input would need `use client`, which the repository's guard forbids
  outside a short reviewed allow list.
- `.claude/launch.json` carries an unrelated, pre-existing uncommitted change (a session-mode dev
  entry). Left alone deliberately.

---

## 3. Where everything is

```
lib/intradayFeatures.ts      the 41 features, serving side (mirrors the Python definition)
lib/cryptoHorizons.ts        the seven durations; mirrors tools/research/crypto_horizons.py
lib/cryptoBars.ts            fetch, validate, gap-fill or refuse; the venue chain
lib/cryptoModel.ts           read an artifact, score one row
lib/cryptoLanes.ts           what the site is allowed to say, from crypto_lanes.json
lib/cryptoVenues.ts          which venue instrument each coin is
lib/cryptoForecast.ts        the whole forecast, every refusal a named kind
lib/forecastStore.ts         write the shown forecast; read the prospective record
components/cryptoBrain.tsx   the panel
components/forecastChart.tsx the bars the model read, with the horizon shaded
components/forecastRecord.tsx the prospective record on /predictions
app/api/forecast/route.ts    the forecast alone, same code path

tools/foundation/crypto_intraday.py    collect and validate bars
tools/foundation/crypto_venue_map.py   which venue each coin is, checked against the venues
tools/research/intraday_features.py    THE definition of the feature set
tools/research/intraday_matrix.py      the fast twin, checked against the definition
tools/research/gbm.py                  histogram gradient boosting, numpy only
tools/research/train_crypto_short.py   train and evaluate one lane
tools/research/crypto_lanes.py         the permission table and the served weights
jobs/forecast_score.py                 grade matured forecasts
tools/migrate.mjs                      apply migrations to the primary from a laptop
```

Rebuild the corpus and the lanes:

```bash
python tools/foundation/crypto_intraday.py BTCUSDT --interval 5m --days 1460 --verify
python tools/research/train_crypto_short.py --symbols BTCUSDT --tag btc --rounds 300 --depth 3
python tools/research/crypto_lanes.py
python tools/research/write_parity_fixture.py
```
