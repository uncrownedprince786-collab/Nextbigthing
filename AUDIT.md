# Production audit — 2026-10-10 (final)

**Status: PRODUCTION LOCKED** — on the owner's criteria, every one measured on 2026-10-10 between 18:07
and 19:30 UTC: the suites pass, the live display checker passes, `/api/health` reads `ok: true`, the
latest run of every workflow is green, and the logic audit reads PASSED MATHEMATICALLY.

**Locked does not mean defect-free.** Section 4 lists what is known and not fixed. The first item is a
High: the patient flip can bring back a call a reader was already told to drop. It changes which call
readers see, so it is left for the owner under rule 86.

One authoritative matrix, replacing the 2026-10-02 audit. Every row says how it was established.

---

## 1. How each row was established

| word | means |
| --- | --- |
| **verified** | run or read in this session, with the result quoted |
| **test-covered** | asserted by the suite, which uses no database and no network |
| **read** | established by reading the code, not by running it |
| **unverified** | believed from inference, and not checked here |
| **owner** | a setting only the account holder can change; section 6 |

Method. Database facts come from the lanes' own logs, `/api/health`, the live pages, and two short
read-only sessions by `tools/logic_audit.py` that the owner asked for (rule 88 otherwise keeps
development off the production database). Three read-only reviewers covered the decision path, the
database failover and the data lanes; every finding they reported was checked against code or a log
before it was acted on or listed here.

---

## 2. Requirement matrix

### Code and build

| requirement | status | evidence |
| --- | --- | --- |
| Python suite | **verified** | 683 tests, OK |
| Web suite | **verified** | 416 tests, 0 failures |
| Type check, lint, compile | **verified** | `tsc --noEmit` 0, `eslint` 0, `compileall jobs tools` 0, `next typegen` 0 |
| CI on the release | **verified** | `tests` and `schema` green on `c36d2a0` |
| Production deploy | **verified** | `c36d2a0` Ready; ISR pages 1h, 36 industry pages prerendered |
| A build cannot fail on an unreachable database | **verified** | `next build` with all three tiers on dead local ports: exit 0, every database page deferred to request time. Before the fix the same build failed on P1001; two production builds failed that way on 2026-10-10 |

### Live site

| requirement | status | evidence |
| --- | --- | --- |
| Pages answer | **verified** | every page 200, unknown routes 404 |
| Heartbeat | **verified** | `/api/health` `ok: true` at 19:21 UTC: closes within limits for all five markets, decisions dated today, newest headline 0.9 h, newest quote 29 min, pool 529 |
| Display rules | **verified** | `tools/ui_audit.py` on `c36d2a0`: 706 rows on 6 pages, every price cell, 529 of 529 assets listed, every check passed |
| Action cell is one line | **verified, test-covered** | live at 1280, 1024, 375 px: row, no wrap, 6px gap, 176px track, 0 of 25 stars wrapped, 0 cells overflowing; row height set by the Horizon column, not the star. Before: 25 of 25 wrapped at 1280 |
| No horizontal scroll on a phone | **verified** | 8 pages at 375 px |
| Sub-cent prices | **verified, test-covered** | PEPE `$0.000004043` on its page, `$0.0₅4036` form in cells; `compactPrice(0.0000099999)` is `$0.0₄1` (was a tenth of that) |
| FX prices | **verified, test-covered** | pairs print in pips (4 decimals, 3 from 20); EURUSD's entry and stop had printed as the same "1.12" |
| One reading per name, the same on its page | **test-covered** | the asset page's call reads swing and longer only, as the lists and the nightly log do |

### Logic audit (`tools/logic_audit.py`, 19:14 UTC) — PASSED MATHEMATICALLY

| check | database: DecisionLog 2026-10-10 | live pages |
| --- | --- | --- |
| checked | 565 LONG/SHORT calls (20 WAIT rows carry no levels) | 529 names, 706 rows |
| stop or target on the wrong side, stop inside the zone | 0 | 0 (294 targets) |
| entry equal to stop | 0 | 0 (2 before the FX fix, display only) |
| invalid reward:risk | 0 of 267 stored | 0 |
| reward:risk outside what the printed levels allow | — | 0 of 294 |
| resolved-call stops | 298 of 298 explained: 277 at exactly 2.00 × atr14 from the close, 21 the setup's own level, none at the price | — |
| under $1 | 0 collapses of 38; smallest risk 0.26% of the close | 0 of 37 |
| stored targets, 14 days | 2,193: none non-positive, none reversed, no invalid reward:risk | — |

The stop equals the zone's far edge on 267 logged calls (250 page rows). That is the construction —
the zone is the range from the entry level to the stop, both ends inclusive — not an inversion, and
risk measured from the entry level is never zero. A strict "stop beyond the zone" rule would need the
zone presented differently; that is a presentation choice, listed in section 4.

### Data lanes

| lane | status | evidence |
| --- | --- | --- |
| tests, schema | **verified** | green on `f77e2d7`, `f548e85`, `c36d2a0`; Supabase migrated alongside ("No pending migrations") |
| news | **verified** | green on `f77e2d7`, dispatched (12.2 min, 1,340 headlines — slice 2, which had never completed on this database) and scheduled; output now streams |
| backfill | **verified** | green on `f77e2d7` |
| mirror | **verified** | green on `f77e2d7`: Supabase took 349 prices, 1,141 decisions, 143 theses, no timeout |
| products | **verified** | green on `f548e85` — the lane's first completed run since it was created on 2026-10-03 (8 of 8 cancelled before): signals 14 min, geo 20 min. On `f77e2d7` its signals job failed on a stalled Reddit feed, the cause `f548e85` fixed; geo passed there too. `retry.yml` re-ran that failed job by itself, its first working retry |
| live quotes, calendar, crypto, watchdog, retry | **verified** | latest runs green |
| decision, audit, PSX, US prices | **verified** | latest runs green (scheduled, on earlier commits) |

### Database and configuration

| item | status | evidence |
| --- | --- | --- |
| Lanes write the Neon primary | **verified** | every lane prints `DATABASE_URL points at: Neon`, and connects |
| `PRIMARY` variable removed | **verified** | lanes after the owner's change carry no warning annotation |
| Site reads the Neon primary | **verified** | no failover warning in three hours of production logs, and the site shows the quotes and headlines the Neon lanes wrote minutes earlier |
| Unmaintained Vercel fallback tier removed | **verified** | `DATABASE_URL_FALLBACK` gone from Vercel; deployments since `f548e85` run without it |
| Supabase standby | **verified** | mirrored and migrated, above |
| Free-tier storage | **verified** | 238 MB on the primary |
| Neon compute-hours quota | **owner** | rule 88's reason for preferring Supabase still stands: hourly jobs keep Neon awake |

### Security

| item | status | evidence |
| --- | --- | --- |
| Secrets in history | **verified** | every connection-string match in all commits is a test placeholder |
| Write surface | **read** | two route handlers, both `GET`; no forms, no accounts |
| Dependencies | **verified** | `next` 16.3.7 has six advisories fixed in 16.3.8; image-optimizer SSRF, self-hosted ISR poisoning and Draft Mode do not apply here. Patch bump still due |
| Headers | **verified** | HSTS present; no CSP, `X-Frame-Options` or `nosniff` — low risk for a read-only site |
| The connection string pasted into a chat earlier | **owner** | rotate that Neon password |

---

## 3. What this pass fixed

| commit | fault | fix |
| --- | --- | --- |
| `f77e2d7` | builds failed whenever the primary was unreachable | `lib/buildSafe.ts` defers the page to request time; Prisma's P1001/P1002/P1017 recognised; the logbook no longer caches an empty page on an outage |
| `f77e2d7` | news hung 25 silent minutes, then cancelled | output streamed through `tee`; a stuck step stopped at 20 min as a counted failure |
| `f77e2d7` | products: 8 of 8 runs cancelled, nothing stored | split by source; geo budgeted inside its job; signals committed per source |
| `f548e85` | products: a Reddit feed stalled the lane | 90 s wall-clock cap per feed, 8 min budget, a stall ends Reddit for the run |
| `f77e2d7` | mirror: full copy hit a statement timeout; decisions skipped with it | per-transaction statement ceiling; decisions step independent; MacroGate copied |
| `f77e2d7` | a failed standby migration ended the step silently | each standby tried and reported, failure annotated |
| `f77e2d7` | watchdog never escalated a timing-out lane; a dead dispatch blocked a retry | cancelled and timed-out count as failures; cooldown ignores dead runs |
| `f77e2d7` | skipped quote runs went unnoticed | a quote lane that is on and an hour stale is a health problem the watchdog restarts |
| `f77e2d7` | `retry.yml` had never re-run anything | repository named — and it has since |
| `f77e2d7` | star wrapped under its call | one-line action cell, track floors measured in a browser |
| `f77e2d7` | `compactPrice` a tenth off just under a power of ten | rounds before counting zeros |
| `f77e2d7` | asset page and list could print opposite calls | the page reads swing and longer only |
| `c36d2a0` | FX entry and stop printed as one number | pairs print in pips; `tools/logic_audit.py` added |

## 4. Known and not fixed

1. **High — the patient flip can hold against a call the reader no longer has** (demonstrated in a
   scratch script). The reversal gate reads only calls the rule table made, so after a forced flip it
   keeps an older call: table SHORT, then a forced LONG on a stop-cross, then an unconfirmed up-turn
   prints SHORT again, with "the last call holds". Likely fix: hold against the last logged call of any
   kind. Owner's decision (rule 86).
2. **Medium** — the "timeframe" confirmation ignores direction (`decision.ts:718`); the asset page's
   gap sentence can contradict a forced call (`reconcile.ts:96`); the scorecard still reads WAIT rows
   for refusals and mixes forced with table calls; health cannot see which tier serves or how far a
   standby lags, and setups, factors, news and quotes are not mirrored.
3. **Low** — withheld-trend shorts never keep their own stop (`resolve.ts:95`); out-of-pool names get a
   page call that is never logged; a forced call with no stop says "which is why the action is WAIT";
   forced flips get a generic reason; the logbook prints sub-cent prices with 2 decimals; the
   `same_database` check ignores the Supabase project in the user name; the home page is 1.95 MB of
   HTML (79 KB over the wire).
4. **Presentation** — the stop sits on the entry zone's far edge by construction (section 2).
5. **Operational** — GitHub drops most scheduled runs; the watchdog now restarts the five data lanes
   and quotes, but it is itself chained to lane completions. The news hang's root cause (most likely
   throttling of the runner) is unconfirmed; the lane now fails visibly instead of silently.

## 5. Owner actions

Done, and verified: `PRIMARY` deleted; GitHub `DATABASE_URL` on the working Neon project; Vercel
`DATABASE_URL_FALLBACK` deleted and redeployed.

Still open:
1. **Rotate the Neon password** pasted into a chat earlier, then update `DATABASE_URL` in GitHub and
   Vercel with the new string.
2. **Bump `next` to 16.3.8** (exact pin), a routine patch.
3. **Decide section 4.1**, the patient-flip whipsaw.
4. **Decide the primary for the long run**: Neon meters compute hours and has gone over quota twice;
   rule 88 sets out the Supabase path.

## 6. Decision

**PRODUCTION LOCKED** as of 2026-10-10 19:30 UTC, on `c36d2a0`, under the owner's criteria. The lock is
a statement about what was measured, not a promise: re-run `tools/ui_audit.py`,
`tools/logic_audit.py` and the suites before treating any later commit as covered by it.
