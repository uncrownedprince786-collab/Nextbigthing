# UI Cutover & Rollback Runbook — 2026-10-18

**Status:** prepared and verified against the live deployment. **No cutover was performed and no
functionality was deleted.** This is the procedure to be executed later, under owner authorisation,
when the replacement interface is signed off.

Authority: `WORKSTREAMS-2026-10-17.md` §C (the route-group contract: *"rollback is deleting the
group"*), `README.md` §Deployment (Vercel builds `main`; the build never touches the schema;
Vercel keeps serving the previous deployment until a build succeeds), and `brain.md` (deployment
notes). Existing convention is dated markdown at the repository root; there was no existing
runbook, so this is the one new file, named to that convention.

---

## 1. The two interfaces, precisely

| | Published product | Replacement interface |
|---|---|---|
| URL space | `/`, `/stocks`, `/psx`, `/crypto`, `/forex`, `/commodities`, `/products`, `/product/[slug]`, `/asset/[symbol]`, `/industry/[slug]`, `/events`, `/event/[slug]`, `/marketplace`, `/logbook`, `/methodology`, `/privacy` | `/preview`, `/preview/markets`, `/preview/markets/[slug]`, `/preview/asset/[symbol]`, `/preview/asset/[symbol]/research`, `/preview/news`, `/preview/predictions`, `/preview/watchlist`, `/preview/status` |
| Source | existing `app/**` pages | `app/preview/**` only |
| Delivery | same Vercel project, same `main` | same Vercel project, same `main` |

Both are served by **one deployment**. `/preview` is a route **prefix**, not a separate project,
and it adds no files to the existing routes (`app/preview/layout.tsx` carries the contract in its
header comment). Isolation, verified live on 2026-10-18:

- `GET /` → HTTP 200, 970,978 bytes; contains the published-product marker *"readings, not tips"*;
  does **not** contain the preview nav.
- `GET /preview` → HTTP 200; contains the amber preview banner *"…replacement interface, in
  development…"* and `robots: { index: false, follow: false }` (`noindex` present in the HTML).
- No `middleware.ts`, `robots.ts` or `sitemap.ts` exists anywhere in the tree.
- Unknown symbols 404 on both trees (`/asset/ZZZZZZNOPE` → 404, `/preview/asset/ZZZZZZNOPE` → 404,
  `/preview/markets/zzzz-nope` → 404).

---

## 2. Which commit and deployment serve production today (verified 2026-10-18)

The public alias is **<https://nextbigthing-nu.vercel.app/>**; it serves whatever is on `main`.
The long `nextbigthing-<hash>-…vercel.app` addresses are **per-deployment aliases of the same
project** — a way to pin and test one exact build, not a different site.

**Verified from the public GitHub Deployments API** (`gh` is not installed here; the API needs no
auth for a public repository):

| production deployment | sha | environment | state | immutable deployment URL |
|---|---|---|---|---|
| id `7147395406` | `7e923e3` | Production | success | `https://nextbigthing-qgroi06lw-uncrownedprince786-6663s-projects.vercel.app` |
| id `7147317724` | `3c5952d` | Production | success | `https://nextbigthing-nuhhfd8l7-uncrownedprince786-6663s-projects.vercel.app` |

- `7e923e3` is the current production commit (this session's docs-only checkpoint). **The
  application files it ships are identical to `3c5952d`** — the last commit that touched `app/**`.
- The published site is **public**: `GET /` returns 200 with the real page, not Vercel's sign-in
  challenge. (The long-standing "behind Vercel Authentication" note in `HANDOFF.md` — which
  describes the 2026-10-01 state and is itself superseded — no longer applies.)
- **Vercel deploys on every push to `main`, including documentation-only commits.** A new
  production deployment appears within ~1 minute of a push. Because every deployment is immutable
  and addressable, the previous one remains retrievable, which is the basis of Level-1 rollback.

Re-derive at any time:

```powershell
$h = @{ 'User-Agent'='opencode'; 'Accept'='application/vnd.github+json' }
$repo = 'uncrownedprince786-collab/Nextbigthing'
$d = Invoke-RestMethod "https://api.github.com/repos/$repo/deployments?per_page=1" -Headers $h
$id = $d[0].id
$s = Invoke-RestMethod "https://api.github.com/repos/$repo/deployments/$id/statuses" -Headers $h
"sha=$($d[0].sha.Substring(0,7)) state=$($s[0].state) url=$($s[0].environment_url)"
```

> Note: `unittest` and lint run in GitHub Actions (`tests.yml`), never in the Vercel build. The
> `tests` lane is green on `3c5952d` (run **#291**, both jobs). See `RESUME.md` §0.

---

## 3. How the replacement is tested **separately** from the existing production routes

Three tiers, cheapest first. Tier 3 is the only true pre-production gate and is the one that must
precede cutover.

1. **Route-prefix test on the live alias (available now, zero risk).** `https://nextbigthing-nu.vercel.app/preview/…`
   renders the replacement; `https://…/` renders the published product. Neither reads the other's
   files, so exercising `/preview` cannot alter the published product. This is how the 8 screens
   and the live journey were verified.
2. **Commit-pinned test on the immutable deployment URL (available now).** Fetch the
   `environment_url` for a specific deployment (table above) to test **exactly that build**, immune
   to anything pushed afterwards. Use this for the smoke matrix in §5.
3. **True pre-production (Vercel Preview environment) — RECOMMENDED, currently BLOCKED.** Deploy
   the cutover branch/PR so Vercel produces a **Preview** deployment (a distinct `*.vercel.app`
   URL, not the production alias), test the full matrix there, and only then merge to `main`.
   - **Blocker:** `vercel whoami` times out from this machine (CLI installed, not authenticated
     here), and `gh` is absent, so the Preview URL cannot be created or queried from here. Creating
     it needs the owner's Vercel access, or enabling Vercel's Git integration Preview builds.
   - Until Tier 3 exists, cutover risk is borne by the fact that the cutover is a **single
     revertible commit** (§6) and Level-1 rollback is instant (§7).

---

## 4. Preconditions and authorisations (before starting)

- [ ] Owner has reviewed this runbook and **authorised the cutover**.
- [ ] Working tree clean; `HEAD == origin/main`; no job or download in flight.
- [ ] `tests` lane green on the cutover commit (see §5, last row).
- [ ] The cutover commit contains **no schema migration** (the UI adds none; migrations are a
      separate, writer-role step per `README.md` §Deployment). If a migration were bundled,
      Level-1 rollback would be unsafe.
- [ ] Current production commit recorded (§2). It is the rollback target.
- [ ] No pooler-sensitive operation is started in the same window (see B1/B4 in `RESUME.md`).

---

## 5. Pre-cutover smoke checks and acceptance criteria

Run against the **cutover commit's immutable deployment URL** (Tier 2/3), on desktop viewport.

**Smoke matrix**

| # | Check | Expected |
|---|---|---|
| S1 | `GET /` … all 16 published routes | 200, and each still contains its published marker |
| S2 | `GET /preview` + all 8 screens | 200 |
| S3 | `/preview/markets/[slug]`, `/preview/asset/[symbol]`, `/preview/asset/[symbol]/research` | 200 for a real slug/symbol |
| S4 | Unknown slug/symbol on both trees | 404 (never a 500, never a default-filled page) |
| S5 | `POST /preview/api/watchlist` with > 50 symbols | capped at 50; `GET` on it is method-not-allowed |
| S6 | Symbol lookup case-insensitivity (e.g. `aapl` vs `AAPL`) | same asset |
| S7 | `robots` on `/preview` | `noindex, nofollow` present |
| S8 | Server logs for the deployment | no unhandled errors during S1–S7 |

**Acceptance criteria** — cutover may proceed only if **all** hold:

1. Every replacement screen renders on the cutover commit with **real data**, and every published
   route still returns 200 (**no regression**).
2. Missing data renders as **absence**, never a substituted default (`null` = not known; `0` =
   measured zero — the project-wide rule).
3. **Screen 4 (Research) shows no model direction.** The rule engine's `gate`, `published` and
   `gateReasons` qualifiers are preserved; the "readings, not tips" discipline is not dropped to
   look cleaner. There is no validated model (`productionApproved: false` in all four artifacts).
4. Watchlist and Preferences document that state is **device-local** (`localStorage`); no screen
   implies a server-side account.
5. The `tests` lane is green on the cutover commit (`types and lint` **and** `brain logic`).
6. Level-1 rollback has been **rehearsed** on a throwaway alias or verified by promoting the prior
   deployment and back (§7), so the revert path is known-good before it is needed.
7. Owner sign-off recorded in `RESUME.md`.

---

## 6. Cutover procedure

The cutover is **one commit** whose revert is the rollback. It promotes the replacement to the
public URLs while **keeping the old page files in the tree** (they are removed only later, §8).

1. **Branch and freeze.** From `main` at the recorded commit, create the cutover commit. Do not add
   a migration.
2. **Map the URLs.** The replacement's URL shapes differ from today's (`/preview/markets` vs
   `/stocks`; `/preview/asset/[symbol]` vs `/asset/[symbol]`). The cutover therefore includes an
   explicit old→new mapping and `308` redirects from every old route to its replacement, so no
   existing link breaks.
3. **Promote the group.** Serve the replacement subtree at the public root (route-group move, or a
   new root that renders it), per the `WORKSTREAMS` §C route-group model. Update the nav.
4. **Keep `/preview` working** as a redirect to the promoted routes, so any shared `/preview` link
   still resolves.
5. **Keep the old files present but unreachable** (behind the redirects). This is what makes the
   rollback a revert rather than a reconstruction.
6. **Verify on the Preview deployment (Tier 3).** Run §5. Resolve any failure before merging.
7. **Merge to `main`.** Vercel builds; on success the production alias serves the cutover commit.
8. **Post-cutover smoke.** Re-run S1–S8 against the live alias. Record the new production
   deployment id/sha in `RESUME.md`.

---

## 7. Rollback procedure

Two levels. **Level 1 is instant and needs no code change — use it first.**

**Level 1 — repoint the alias to the last known-good deployment (seconds, no build):**

- Preferred: Vercel dashboard → Project → Deployments → select the deployment from §2 (the recorded
  pre-cutover sha) → **Promote to Production**. Clears the production alias back in one action and
  leaves the cutover deployment intact.
- CLI equivalent (requires Vercel auth, currently unavailable here):
  `vercel alias set <pre-cutover-deployment-url> nextbigthing-nu.vercel.app`.
- This does **not** delete anything; both deployments remain addressable.

**Level 2 — revert the cutover commit (if the alias must follow `main` again):**

```
git revert <cutover-sha>
git push origin main
```

Because the old page files were kept (cutover step 5), the revert restores prior behaviour on the
next successful build. If the build fails, Vercel keeps serving the previous deployment
(`README.md` §Deployment) — the failure is safe.

**Rollback of data:** none is required. The cutover is presentation-only; it performs **no database
write and no migration**. If a future cutover ever bundled a migration, this runbook's Level-1/2
rollback would be unsafe and the migration would need its own reverse.

**Signals that trigger rollback:** any published route non-200; any replacement screen erroring;
any screen presenting an unvalidated direction as a recommendation; broken redirect loop.

---

## 8. Evidence required **before** removing old product code

Removing the old pages (`app/**` outside `app/preview/**`) is a **separate, later commit** and must
not be part of the cutover. It requires all of the following, recorded in `RESUME.md`:

1. **Cutover merged and green** — the cutover commit passed `tests` and served production.
2. **A stabilisation window** — an agreed period (proposal: **7 days**) of production serving the
   replacement with **no P1 regression** and no rollback triggered.
3. **A rehearsed rollback** during that window (§5 criterion 6), so removal is not the first time
   the revert path is exercised.
4. **Owner authorisation** — explicit, because this is the step that is not a one-line revert.
5. **Route/redirect audit** — every old URL either maps to a live replacement route or returns a
   deliberate 404; no dangling redirect.
6. **No orphaned readers** — confirm no old page was the only consumer of a `lib/queries.ts`
   reader before deleting it (`WORKSTREAMS` §2 lists the 50 readers).

Until all six hold, the old code stays and `/preview` stays promotable.

---

## 9. What this runbook does NOT do

- It does **not** perform the cutover, promote an alias, delete any route, or change any file under
  `app/**`. Preparing it changed only this document, `RESUME.md`, and `WORKSTREAMS-2026-10-17.md`.
- It does **not** create a Vercel Preview deployment (Tier 3) — that needs owner Vercel access
  (§3).
- It does **not** assert a validated model. The replacement may ship without one; it may not ship a
  direction.
