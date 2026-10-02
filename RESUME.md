# Resume here

Last worked: **2026-10-02**, on `main`. See section 3 — the silent-failure half of the open item is fixed; the confirmation still needs one GitHub sign-in.

This file is the sixty-second orientation. `HANDOFF.md` is the detail; read this first, then
that.

---

## 1. Before anything else

```bash
cd "C:\Users\NEW TECH\Nextbigthing"
```

A second, **stale** copy of this project exists elsewhere on the owner's machine — a
snapshot from 2026-09-30, under their `Documents` folder. Do not work in it; confirm you
are in the directory above before editing anything.

**`DATABASE_URL` is required and is not in this repo.** `.env` is gitignored and absent, so no
job and no script in `tools/` will run until it is set. Ask the owner for the Neon connection
string and put it in `.env` (copy `.env.example` for the shape). Everything works once it is
there.

## 2. What is green

Verified against the live production database on 2026-10-01, not merely built:

| | |
| --- | --- |
| Tests | **228**, all passing, no database or network needed |
| Types, lint, build | clean |
| `schema.yml` (release lane) | **green** — run `36917629683`, 9m 3s, all 20 brain jobs |
| Every job in the daily group | passes individually against production — see the table in `HANDOFF.md` |
| Intraday chain, end to end | **29 checks, 0 failures** (`python tools/intraday_chain.py`) |
| Acceptance criteria | **23 pass, 4 partial, 0 fail** (`python tools/acceptance.py`) |
| Database | 123 MB of a 500 MB free tier |

The four partials are time-gated, not unfinished: calibration, source learning, posterior odds
and event resolution all wait on outcome rows maturing (earliest ~**2026-10-30**) or on a
scheduled date passing. The machinery is live and measuring; it has nothing to measure yet.
`HANDOFF.md` explains each one.

## 3. What is red — the one open item

**`refresh.yml` fails at "Run data jobs".** Latest: run `36918247571`, failure, 17m 11s. The
schema guard passed; the failure is inside `python jobs/run.py daily`.

Two causes were found and fixed on 2026-10-01 (`a7cdfa4`, `3cc83ee`), and **every job in that
group now passes when run on its own against production**. So what remains is almost certainly
environmental rather than a code defect.

**The hypothesis, and the next thing to do:** `yfinance` is likely throttled or blocked from
GitHub runner IPs. The evidence is that the same `prices` step stored **0** rows on the runner
while storing **37,537** locally minutes later, and `fetch_yahoo` cannot distinguish an empty
frame from a blocked one — `yf.download` returns an empty DataFrame and nothing raises.

To confirm it you need **one GitHub sign-in**. `jobs/run.py` already writes a per-step table to
`$GITHUB_STEP_SUMMARY` and `schema.yml`'s migrate step copies its own output there, but GitHub
does not render job summaries to anonymous visitors. Sign in once, open the failing run, and the
table names the step in a line.

**Done on 2026-10-02:** the silence itself is fixed. `require_answer` in `jobs/prices.py` now
fails the step when a whole download batch stores **0** rows — a blocked or throttled host,
rather than a market with no new bars — on the same line `jobs/marketplace.py` draws when every
Amazon category is blocked. One asset answering nothing is still data and is still only printed.
Two tests guard it, and brain.md rule **31** records why. `jobs/audit.py` already made this
distinction and is what caught the original run: it reports `Yahoo Finance daily closes —
partial — the newest day holds 2 records against a recent median of 60`.

**And then the actual defect turned up, in `fetch_crypto`.** It is a code bug after all, not
only an environment:

1. `insert_snapshots` gained `open`, `high` and `low` on 2026-10-01 in `aa64785`. The Yahoo
   caller was updated; the Binance one was not. Six fields reached a nine-name COPY unpack, so
   **every crypto insert has raised `ValueError` since that commit** — the same day
   `refresh.yml` started failing. The rows go through `crypto_rows` now, and a test unpacks it
   with the nine names COPY uses.
2. In the same function the market cap was dated off `closes[-1]` **before** the empty-series
   guard. CoinPaprika is not geo-blocked and Binance is, so the one host where `closes` is
   empty is exactly the host where a cap is present: `IndexError` on a runner, clean locally.
   The guard now comes first.

Both are invisible to the 221-test suite and to running each job locally, which is why "every
job passes individually" held while the group failed. **This is the better explanation of run
`36918247571` than the Yahoo block**, and it is fixed.

**Every batch lane now reports a silent source**, since the same hole was in all of them:
Yahoo and Binance count rows stored, the news lane counts *feeds that parsed* (new rows are
legitimately 0 on a rerun inside the cache hour, and the guard sits before the 120-day
retention sweep so a fetchless run cannot delete four months of articles), and `jobs/psx.py`
counts published trading days over a 120-day window where zero cannot be a holiday. brain.md
rule 31 explains why the counter differs per lane.

What is still open: the Yahoo-block hypothesis is now only a hypothesis, unconfirmed and no
longer needed to explain the failure. Confirming anything still wants one GitHub sign-in to
read the step summary — but the useful next move is simply to **re-run `refresh.yml`** and see
whether it passes. If it fails again, the new guards name the source in the step's own output.
Run conclusions, unlike step summaries, *are* public: `tests #22` passed on `b826d2e`.

## 4. Known data gaps, each with its reason

- **`ProductRegion` is empty.** `geo.py` works (verified: 175 countries, 51 US states, 5 PK
  provinces) but keeps being cancelled by queue churn in `backfill.yml`.
- **`MarketplaceItem` is empty** and `Coverage` reports Amazon Best Sellers as `silent`. It is a
  weekly job and has not run.
- **Binance crypto closes stop at 2026-09-29.**
- **`EventState` is 0.** All 131 scheduled dates are still in the future, so nothing has
  resolved. The first frozen pre-event state appears when one passes.

## 5. Not verified, and not claimed

**Visual production acceptance has not been performed.** The Vercel deployment sits behind
Vercel Authentication: it answers `HTTP 200` with a 341 KB body, and that body is the sign-in
challenge rather than the site. Reading the status code alone was misleading, which is worth
remembering.

What was done instead: the current commit was built and served locally against the production
database, and `/`, `/asset/INTC`, `/asset/AAPL`, `/methodology`, `/events` and `/products` were
all fetched and read. That verifies the code and the data. It does not verify the deployment.
The remedy is one setting — disable Vercel Authentication for production, or grant access.

## 6. Where to read next

| file | what it holds |
| --- | --- |
| `HANDOFF.md` | the live state in full: the acceptance matrix with measured figures, the nine defects the acceptance pass found, the free-tier numbers, and what still needs a human |
| `brain.md` | **32 rules for changes.** Read these before editing a job; the last ten were earned by real bugs |
| `ARCHITECTURE.md` | the layer map, with every layer marked built / partial / absent honestly |
| `tools/README.md` | the four read-only verification harnesses and the two results that are easy to misread |
| `README.md` | how the system is put together and how to run it |

## 7. Freeze status

Feature development was declared complete on 2026-10-01. Only these are in scope now:

1. a real production bug
2. a security issue
3. provider or source breakage
4. a free-tier or storage violation
5. required maintenance
6. the already-defined calibration, source-learning and event-resolution mechanisms, when their
   evidence naturally matures

The open item in section 3 falls under (1) and (3). Everything else should be left alone.
