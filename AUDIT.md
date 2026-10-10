# Production audit — 2026-10-10 (final)

**Status: PRODUCTION LOCKED** on `f6edc7e` (Next.js 16.3.8) — on the owner's criteria, every one
measured on 2026-10-10 between 18:07 and 20:17 UTC: the suites pass, the live display checker passes,
`/api/health` reads `ok: true`, the latest run of every workflow is green, and the logic audit reads
PASSED MATHEMATICALLY.

**Locked does not mean defect-free.** Section 4 lists what is known and not fixed; nothing in it is
rated High. The High finding of the first pass (the patient-flip whipsaw) was resolved in `78bdc7c`.

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
| Python suite | **verified** | 688 tests, OK |
| Web suite | **verified** | 422 tests, 0 failures |
| Type check, lint, compile | **verified** | `tsc --noEmit` 0, `eslint` 0, `compileall jobs tools` 0, `next typegen` 0 |
| CI on the release | **verified** | `tests` and `schema` green on `f6edc7e` |
| Production deploy | **verified** | `f6edc7e` Ready on Next.js 16.3.8; ISR pages 1h, industry pages prerendered |
| A build cannot fail on an unreachable database | **verified** | `next build` with all three tiers on dead local ports, on 16.3.7 and again on 16.3.8: exit 0, every database page deferred to request time. Before the fix the same build failed on P1001; two production builds failed that way on 2026-10-10 |

### Live site

| requirement | status | evidence |
| --- | --- | --- |
| Pages answer | **verified** | every page 200, unknown routes 404 |
| Heartbeat | **verified** | `/api/health` `ok: true` at 20:17 UTC: closes within limits for all five markets, decisions dated today, newest headline 1.8 h, newest quote 10 min, pool 532 |
| Display rules | **verified** | `tools/ui_audit.py` on `f6edc7e`: 707 rows on 6 pages, every price cell, 532 of 532 assets listed, every check passed |
| Action cell is one line | **verified, test-covered** | live at 1280, 1024, 375 px: row, no wrap, 6px gap, 176px track, 0 of 25 stars wrapped, 0 cells overflowing; row height set by the Horizon column, not the star. Before: 25 of 25 wrapped at 1280 |
| No horizontal scroll on a phone | **verified** | 8 pages at 375 px |
| Sub-cent prices | **verified, test-covered** | PEPE `$0.000004043` on its page, `$0.0₅4036` form in cells; `compactPrice(0.0000099999)` is `$0.0₄1` (was a tenth of that) |
| FX prices | **verified, test-covered** | pairs print in pips (4 decimals, 3 from 20); EURUSD's entry and stop had printed as the same "1.12" |
| One reading per name, the same on its page | **test-covered** | the asset page's call reads swing and longer only, as the lists and the nightly log do |
| No whipsaw | **verified, test-covered** | a held flip keeps the call the reader holds, and no call returns unconfirmed to the side it left within 3 days (`forced-whipsaw-hold`). Through `decideCall` on the audit's case: SHORT, LONG, SHORT became SHORT, LONG, LONG |

### Logic audit (`tools/logic_audit.py`, 20:17 UTC, on `f6edc7e`) — PASSED MATHEMATICALLY

| check | database: DecisionLog 2026-10-10 | live pages |
| --- | --- | --- |
| checked | 570 LONG/SHORT calls (20 WAIT rows carry no levels) | 532 names, 707 rows |
| stop or target on the wrong side, stop inside the zone | 0 | 0 (298 targets) |
| entry equal to stop | 0 | 0 (2 before the FX fix, display only) |
| invalid reward:risk | 0 of 294 stored | 0 |
| reward:risk outside what the printed levels allow | — | 0 of 298 |
| resolved-call stops | 276 of 276 explained: 254 at exactly 2.00 × atr14 from the close, 22 the setup's own level, none at the price | — |
| under $1 | no collapse | 0 of 37 |
| stored targets, 14 days | 2,216: none non-positive, none reversed, no invalid reward:risk | — |

The stop equals the zone's far edge on 294 logged calls (254 page rows). That is the construction —
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
| decision, calendar | **verified** | green on `f6edc7e`, dispatched to exercise the new code: the copy-back check ran first ("the primary is current against SUPABASE_DATABASE_URL"), no write fell over, no `PRIMARY` warning, the decision lane wrote 590 rows with the whipsaw guard in place |
| live quotes, crypto, watchdog, retry | **verified** | latest runs green |
| audit, PSX, US prices | **verified** | latest runs green (scheduled, on earlier commits) |

### Database and configuration

| item | status | evidence |
| --- | --- | --- |
| Lanes write the Neon primary | **verified** | every lane prints `DATABASE_URL points at: Neon`, and connects |
| `PRIMARY` variable removed | **verified** | lanes after the owner's change carry no warning annotation |
| Site reads the Neon primary | **verified** | no failover warning in three hours of production logs, and the site shows the quotes and headlines the Neon lanes wrote minutes earlier |
| Unmaintained Vercel fallback tier removed | **verified** | `DATABASE_URL_FALLBACK` gone from Vercel; deployments since `f548e85` run without it |
| Supabase standby | **verified** | mirrored and migrated, above |
| Reads survive a Neon pause | **test-covered, read** | the site's pool fails over to Supabase on a quota error (lib/failover.ts), and a build with no reachable tier defers instead of failing |
| Writes survive a Neon pause | **test-covered** | `jobs/nbt.py db()` and `tools/writer.mjs` write the standby when the primary cannot be reached (never on a bad password); `jobs/reconcile.py` copies the standby's newer rows back the first time a lane reaches the primary, and cron-mirror runs it before its own copy. Both databases' maxima were checked identical before deploying. **Not yet exercised by a real outage**: the next quota pause is the first live test, and its runs will carry a "Writing to the standby" warning |
| Free-tier storage | **verified** | 238 MB on the primary |
| Neon compute-hours quota | **mitigated** | a pause no longer stops the site or the lanes; rule 88's case for Supabase as primary still stands if pauses become routine |

### Security

| item | status | evidence |
| --- | --- | --- |
| Secrets in history | **verified** | none of the six live secrets in the local env files (five database passwords, one GitHub token) appears in any tracked file or any commit; every connection-string match in history is a test placeholder; no Neon password, API key, GitHub token, JWT, AWS key or private key pattern anywhere. Only `.env.example` is tracked; `.env` and its backup are git-ignored. All code reads credentials from the environment |
| Write surface | **read** | two route handlers, both `GET`; no forms, no accounts |
| Dependencies | **verified** | `next` 16.3.8: its six advisories closed (`7c2cc31`). Remaining: Prisma's transitive `mysql2` and `deepmerge-ts`, not on the request path, whose only offered fix is a major downgrade |
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
| `7c2cc31` | `next` 16.3.7 advisories | bumped to 16.3.8 |
| `78bdc7c` | the patient-flip whipsaw (SHORT, LONG, SHORT) | a held flip keeps the reader's call; `whipsawHold` blocks an unconfirmed return within 3 days |
| `cffe7ac` | a Neon quota pause stopped every lane | writes fail over to the standby and are copied back after |
| `f6edc7e` | an old Neon endpoint id in RESUME.md | removed (an identifier, not a credential) |

## 4. Known and not fixed

1. **Resolved — the patient-flip whipsaw** (`78bdc7c`): kept for the record; see section 3.
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
   throttling of the runner) is unconfirmed; the lane now fails visibly instead of silently. The write
   failover has passed its tests but not yet a real outage. During one, rows derived on the standby
   (setups, factors) are rebuilt on the primary by the next decision run rather than copied back.

## 5. Owner actions

Done, and verified: `PRIMARY` deleted; GitHub `DATABASE_URL` on the working Neon project; Vercel
`DATABASE_URL_FALLBACK` deleted and redeployed. Done by the technical lead at the owner's instruction:
`next` 16.3.8; the whipsaw decision (a guard, not a documented quirk); write failover; credential sweep.

Still open:
1. **Rotate the Neon password** that was pasted into a chat earlier (it is in no file and no commit, but
   a chat transcript is outside this repository's control), then update `DATABASE_URL` in GitHub and
   Vercel. The session cannot confirm whether this was done.
2. **Optional**: make Supabase the primary (rule 88) if Neon's pauses become routine; failover now
   carries the site and the lanes through them either way.

## 6. Decision

**PRODUCTION LOCKED** as of 2026-10-10 20:17 UTC, on `f6edc7e`, under the owner's criteria. The lock is
a statement about what was measured, not a promise: re-run `tools/ui_audit.py`,
`tools/logic_audit.py` and the suites before treating any later commit as covered by it.
