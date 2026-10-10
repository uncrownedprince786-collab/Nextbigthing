"""Read the site's heartbeat every hour and restart the lane that stopped.

    python tools/watchdog.py              read /api/health, dispatch what it names, report
    python tools/watchdog.py --dry-run    read and plan, dispatch nothing

What "self-healing" can mean on this platform
---------------------------------------------
The site is serverless and the jobs are scheduled workflows, so there is no process that could hold an
"infinite heartbeat loop". What there can be is a scheduled look: this runs hourly, reads `/api/health`
(which judges every stored reading against the rule table's own freshness limits), and for each stale
reading starts the workflow that refreshes it. A lane that silently stopped -- a schedule GitHub
skipped, a run that "succeeded" while writing nothing -- is started again without anyone noticing
first. `retry.yml` already re-runs a run that *failed*; this catches the ones that never ran.

When it does not restart, and turns red instead
-----------------------------------------------
  * the lane is already queued or running: it waits, so two copies never race on the same rows;
  * the watchdog dispatched it within the last 50 minutes: once an hour, never a storm;
  * the lane has failed twice in the last three hours: restarting a lane that cannot succeed (a wrong
    secret, a provider that blocks the runner) only adds red runs. That is the case a person has to
    fix, and the run goes red so GitHub's own failure email reaches them;
  * the site or its database cannot be read at all, for the same reason.
A red run here is the alert. A green one means everything stale was restarted or nothing was stale.

What it will never do
---------------------
  * Dispatch a workflow that is not on `LANES`. The health document comes over the network and is
    treated as untrusted input: a lane name in it is a request, and only six files can be requested.
  * Print the token, or anything from a response body beyond the fields it names.
  * Change a threshold, a rule or a row. It starts lanes; the lanes do what they always do.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

# The only workflows the watchdog may start, by file name. Exactly the lanes `lib/health.ts` names.
LANES = frozenset({
    "cron-crypto.yml", "cron-us-prices.yml", "cron-psx.yml", "cron-decision.yml", "cron-news.yml", "cron-live.yml",
})
ACTIVE = frozenset({"queued", "in_progress", "waiting", "pending", "requested"})
# A run that ended without doing its work. "cancelled" is how GitHub reports a job that hit its own
# timeout, which is how the news and products lanes actually died; counting only "failure" meant a lane
# that timed out every run was restarted for ever and never reached a person.
FAILED = frozenset({"failure", "cancelled", "timed_out"})
DISPATCH_COOLDOWN = timedelta(minutes=50)
FAILURE_WINDOW = timedelta(hours=3)
FAILURES_TO_ESCALATE = 2
DEFAULT_SITE = "https://nextbigthing-nu.vercel.app"


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value.replace("Z", "+0000"), "%Y-%m-%dT%H:%M:%S%z")
    except ValueError:
        return None


def plan(health: dict | None, runs: dict[str, list[dict]], now: datetime) -> list[dict]:
    """What to do about each problem: dispatch, wait, or escalate. Pure: the runs and clock are inputs.

    `runs` maps a lane to its recent runs, newest first, as the GitHub API returns them
    (`status`, `conclusion`, `event`, `created_at`).
    """
    if health is None:
        return [{"lane": None, "action": "escalate", "why": "the health endpoint could not be read"}]
    actions: list[dict] = []
    seen: set[str] = set()
    for problem in health.get("problems") or []:
        lane = problem.get("lane")
        detail = str(problem.get("detail") or problem.get("check") or "")[:200]
        if lane is None:
            actions.append({"lane": None, "action": "escalate", "why": detail})
            continue
        if lane not in LANES:
            actions.append({"lane": None, "action": "escalate", "why": f"health named a lane that is not allowed: {str(lane)[:60]}"})
            continue
        if lane in seen:
            continue
        seen.add(lane)
        recent = runs.get(lane) or []
        if any(r.get("status") in ACTIVE for r in recent):
            actions.append({"lane": lane, "action": "wait", "why": f"{detail}; a run is already queued or running"})
            continue
        failures = [
            r for r in recent
            if r.get("conclusion") in FAILED and (t := parse_time(r.get("created_at"))) and now - t <= FAILURE_WINDOW
        ]
        if len(failures) >= FAILURES_TO_ESCALATE:
            actions.append({
                "lane": lane, "action": "escalate",
                "why": f"{detail}; the lane failed {len(failures)} times in the last 3 hours, so restarting it will not help",
            })
            continue
        # The cooldown is for a dispatch that ran and did its job; one that already died is no reason to
        # wait (2026-10-10: a manual news run cancelled at its timeout held the restart back for 50
        # minutes). A dead run counts toward escalation above instead.
        mine = [
            r for r in recent
            if r.get("event") == "workflow_dispatch"
            and r.get("conclusion") not in FAILED
            and (t := parse_time(r.get("created_at"))) and now - t < DISPATCH_COOLDOWN
        ]
        if mine:
            actions.append({"lane": lane, "action": "wait", "why": f"{detail}; dispatched within the last 50 minutes"})
            continue
        actions.append({"lane": lane, "action": "dispatch", "why": detail})
    return actions


# --- I/O --------------------------------------------------------------------------------------


def read_health(url: str) -> dict | None:
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "nbt-watchdog"}), timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        # 503 carries a body naming the database as the problem; anything else is "could not read".
        if e.code == 503:
            try:
                return json.load(e)
            except Exception:  # noqa: BLE001
                return None
        return None
    except Exception:  # noqa: BLE001 - any failure to read is the one thing a heartbeat must report
        return None


def github(method: str, path: str, token: str, body: dict | None = None):
    req = urllib.request.Request(
        f"https://api.github.com{path}",
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "nbt-watchdog",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read()
        return json.loads(raw) if raw else None


def main(argv: list[str]) -> int:
    dry = "--dry-run" in argv
    site = (os.environ.get("SITE_URL") or DEFAULT_SITE).rstrip("/")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    token = os.environ.get("GITHUB_TOKEN", "")
    now = datetime.now(timezone.utc)

    health = read_health(f"{site}/api/health")
    lanes = sorted({p.get("lane") for p in (health or {}).get("problems") or [] if p.get("lane") in LANES})
    runs: dict[str, list[dict]] = {}
    for lane in lanes:
        try:
            got = github("GET", f"/repos/{repo}/actions/workflows/{lane}/runs?per_page=10", token) if repo and token else None
            runs[lane] = (got or {}).get("workflow_runs") or []
        except Exception as e:  # noqa: BLE001
            print(f"watchdog: could not list runs for {lane} ({type(e).__name__})")
            runs[lane] = []

    actions = plan(health, runs, now)
    if health is not None and not actions:
        print(f"watchdog: healthy at {now:%Y-%m-%d %H:%M} UTC; nothing to restart")
    escalated = False
    for a in actions:
        if a["action"] == "dispatch":
            if dry or not (repo and token):
                print(f"watchdog: would dispatch {a['lane']} ({a['why']})")
                continue
            try:
                github("POST", f"/repos/{repo}/actions/workflows/{a['lane']}/dispatches", token, {"ref": "main"})
                print(f"watchdog: dispatched {a['lane']} ({a['why']})")
            except Exception as e:  # noqa: BLE001
                escalated = True
                print(f"watchdog: could not dispatch {a['lane']} ({type(e).__name__}); needs a person")
        elif a["action"] == "wait":
            print(f"watchdog: waiting on {a['lane']} ({a['why']})")
        else:
            escalated = True
            print(f"watchdog: NEEDS A PERSON: {a['why']}")
    return 1 if escalated else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
