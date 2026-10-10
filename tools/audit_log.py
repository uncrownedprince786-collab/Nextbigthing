"""Append the day's evaluation audit to the owner's Google Doc: a weekly review on Mondays, a daily entry
every day. Runs at the end of the decision workflow.

    python tools/audit_log.py                print today's entry (and the weekly review on a Monday)
    python tools/audit_log.py --append       also append it to the Google Doc
    python tools/audit_log.py --date 2026-10-17 --append

Configuration (all optional; without it the entry is printed and goes to the run summary):
    AUDIT_DOC_ID                  the document id from its URL
    GOOGLE_SERVICE_ACCOUNT_JSON   a service account key that the document is shared with as Editor

What it reports, and how each figure is decided
-----------------------------------------------
Every verdict comes from `tools/scorecard.py`'s own functions, so this log and the scorecard can never
grade the same call differently:

  * a call's **cycle completes** when its five-session window closes (`move5Pct` is measured) -- the
    swing horizon of rule 77;
  * **stopped** if a daily close inside the window crossed the stop (checked first: a stopped trade did
    not get to find out where the price finished), else **right** or **wrong** on the five-session
    move, else **flat**;
  * a **star** is the entry-trigger confirmation (`trigger` in `legs`): the event behind a Rising or
    Falling Star that agreed with its call.

What it will not write
----------------------
No invented lesson and no claimed self-correction. A "retrospective lesson" here is the measured facts
of the outcome -- the move, the stop, the confirmations the call had -- because the engine does not form
opinions, and a sentence like "the veto should have weighted oil higher" would be a guess presented as a
finding. Nothing is adjusted automatically (brain.md rule 77), and the log says so. A rate is printed
with its count, and no rate is printed from nothing.

Idempotent: an entry already in the document for that day (or a review for that week) is not appended
twice, so a re-run or a retried workflow costs nothing. Never prints a credential.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "jobs"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from nbt import db  # noqa: E402
from scorecard import band_in, stop_was_hit, verdict_of  # noqa: E402

LEG_WORDS = {
    "timeframe": "longer view",
    "volume": "volume",
    "history": "similar past days",
    "peers": "peers",
    "trigger": "entry event",
}
GATE_WORDS = {
    "stop-crossed": "a daily close crossed the stop",
    "macro-veto": "the macro gate refused it on breaking news",
    "short-unbacked": "nothing independent confirmed the short any more",
    "incomplete": "the setup no longer read a direction",
    "reversal-unconfirmed": "the trend turned, unconfirmed",
}
DIVIDER = "=" * 68
RULE = "-" * 68


def day_label(d: date) -> str:
    return d.strftime("%b %d, %Y").replace(" 0", " ")


def pct(n: int, total: int) -> str:
    return f"{n} ({round(100 * n / total)}%)" if total else f"{n} (no completed cycle yet)"


def legs_of(row: dict) -> list[str]:
    return [x for x in (row.get("legs") or "").split(",") if x]


def outcome(row: dict, series: list) -> dict:
    """The scorecard's verdict for one completed call, plus the figures the log prints."""
    lo, hi = band_in(series, row["periodEnd"], row["measured5On"])
    stopped = stop_was_hit(row["action"], row.get("invalidation"), lo, hi)
    verdict = verdict_of(row["action"], row.get("move5Pct"), stopped)
    entry = row.get("baseClose")
    move = row.get("move5Pct")
    exit_price = entry * (1 + move / 100) if entry is not None and move is not None else None
    stop_day = None
    if stopped:
        crossing = sorted(
            d for d, c in series
            if c is not None and row["periodEnd"] < d <= row["measured5On"]
            and ((row["action"] == "LONG" and c <= row["invalidation"]) or (row["action"] == "SHORT" and c >= row["invalidation"]))
        )
        stop_day = crossing[0] if crossing else None
    return {"verdict": verdict, "entry": entry, "exit": exit_price, "move": move, "stop_day": stop_day}


def fact_line(row: dict, o: dict) -> str:
    """The retrospective, as measured facts and nothing else."""
    legs = legs_of(row)
    had = ", ".join(LEG_WORDS.get(x, x) for x in legs) if legs else "no independent confirmation"
    if o["verdict"] == "stopped":
        when = f" on {day_label(o['stop_day'])}" if o["stop_day"] else ""
        return f"A close crossed the stop {row['invalidation']:.2f}{when}. The call had: {had}."
    if o["move"] is None:
        return f"Move not measured. The call had: {had}."
    side = "with" if o["verdict"] == "right" else "against" if o["verdict"] == "wrong" else "flat to"
    return f"Moved {o['move']:+.2f}% {side} the call over five sessions. The call had: {had}."


def classify(prev: str | None, cur: str, gate: str | None) -> str | None:
    if not prev or prev == cur:
        return None
    if prev in ("LONG", "SHORT") and cur in ("LONG", "SHORT"):
        return "REVERSED"
    if prev in ("LONG", "SHORT"):
        return {"stop-crossed": "INVALIDATED", "macro-veto": "OVERRIDDEN"}.get(gate or "", "WITHDRAWN")
    return None  # a new call is not an exit or a shift


def weekly_review(week_start: date, rows: list[dict], completed: list[tuple[dict, dict]], shifts: int) -> list[tuple[str, str]]:
    end = week_start + timedelta(days=6)
    graded = [o for _, o in completed if o["verdict"] in ("right", "wrong", "stopped", "flat")]
    right = sum(1 for o in graded if o["verdict"] == "right")
    failed = sum(1 for o in graded if o["verdict"] in ("wrong", "stopped"))
    stars = [(r, o) for r, o in completed if "trigger" in legs_of(r) and o["verdict"] in ("right", "wrong", "stopped", "flat")]
    star_right = sum(1 for _, o in stars if o["verdict"] == "right")
    star_line = (
        f"{star_right} of {len(stars)} ({round(100 * star_right / len(stars))}%)" if stars else "no star has completed a cycle yet"
    )
    return [
        ("", ""),
        (DIVIDER, ""),
        (f"WEEKLY PERFORMANCE REVIEW: {day_label(week_start)} - {day_label(end)}", "title"),
        (DIVIDER, ""),
        (f"• Total predictions logged: {sum(1 for r in rows if r['action'] in ('LONG', 'SHORT'))}", ""),
        (f"• Completed cycles (five-session window closed): {len(graded)}", ""),
        (f"• Accurate: {pct(right, len(graded))}", ""),
        (f"• Invalidated or failed: {pct(failed, len(graded))}", ""),
        (f"• Mid-cycle state flips: {shifts}", ""),
        (f"• Early detection (stars) accurate: {star_line}", ""),
        (RULE, ""),
    ]


def daily_entry(day: date, completed: list[tuple[dict, dict]], shifts: list[dict], stars_today: list[dict]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = [("", ""), (f"{day_label(day)} - DAILY BRAIN EVALUATION AUDIT", "heading")]

    out.append(("1. EXPIRED / COMPLETED CALLS (five-session horizon)", "bold"))
    if not completed:
        out.append(("- None. No call's five-session window closed today.", ""))
    for row, o in completed:
        result = {
            "right": "ACCURATE (moved with the call across the window)",
            "wrong": "FAILED (moved against the call across the window)",
            "stopped": "FAILED (invalidated at the stop)",
            "flat": "FLAT (no move across the window)",
        }.get(o["verdict"] or "", "NOT SCORABLE (no measured move)")
        star = "Entry event fired with the call" if "trigger" in legs_of(row) else "No early signal"
        star_result = (
            f"{star} -- {'accurate' if o['verdict'] == 'right' else 'did not hold'}" if "trigger" in legs_of(row) else star
        )
        entry = f"{o['entry']:.2f}" if o["entry"] is not None else "n/a"
        exit_ = f"{o['exit']:.2f}" if o["exit"] is not None else "n/a"
        move = f"{o['move']:+.2f}%" if o["move"] is not None else "n/a"
        out += [
            (f"- Asset: {row['symbol']} ({row['name']}) | Type: {row['action']} | Called {day_label(row['periodEnd'])}", ""),
            (f"  - Result: {result}", ""),
            (f"  - Outcome: entry {entry} ➔ close {exit_} ({move})", ""),
            (f"  - Early signal: {star_result}", ""),
            (f"  - Facts: {fact_line(row, o)}", ""),
        ]

    out.append(("2. MID-CYCLE DIRECTIONAL SHIFTS & EXITS", "bold"))
    if not shifts:
        out.append(("- None. No call ended or flipped today.", ""))
    for s in shifts:
        out += [
            (f"- Asset: {s['symbol']} ({s['name']})", ""),
            (f"  - Shift: {s['kind']}: {s['prev']} ➔ {s['action']} (day {s['day']} of the call)", ""),
            (f"  - Reason: {GATE_WORDS.get(s['gate'] or '', 'the rule table reading changed')}", ""),
            ("  - Evaluation: pending; graded when the original call's five-session window closes", ""),
        ]

    out.append(("3. EARLY TREND DETECTION (Rising / Falling Stars)", "bold"))
    out.append((f"- Stars with the call today: {len(stars_today)}", ""))
    for r in stars_today:
        badge = "RISING STAR ⬆" if r["action"] == "LONG" else "FALLING STAR ⬇"
        out.append((f"  - {r['symbol']}: {badge} ➔ result pending (window closes in five sessions)", ""))

    out.append(("Self-correction: none applied automatically. Rules change only on reviewed scorecard evidence.", ""))
    out.append((RULE, ""))
    return out


# --- data --------------------------------------------------------------------------------------


def load(cur, day: date):
    cur.execute(
        """SELECT d."assetId", a.symbol, a.name, d.action, d.gate, d."periodEnd", d."baseClose", d.invalidation,
                  d."move5Pct", d."measured5On", d.legs
             FROM "DecisionLog" d JOIN "Asset" a ON a.id = d."assetId"
            WHERE d.action IN ('LONG', 'SHORT') AND d."measured5On" = %s
            ORDER BY a.symbol""",
        (day,),
    )
    matured = cur.fetchall()
    series: dict[str, list] = {}
    if matured:
        cur.execute(
            """SELECT "assetId", date, close FROM "PriceSnapshot"
                WHERE "assetId" = ANY(%s) AND date > %s AND date <= %s""",
            ([m["assetId"] for m in matured], min(m["periodEnd"] for m in matured), day),
        )
        for r in cur.fetchall():
            series.setdefault(r["assetId"], []).append((r["date"], r["close"]))
    completed = [(m, outcome(m, series.get(m["assetId"], []))) for m in matured]

    cur.execute(
        """WITH h AS (
             SELECT d."assetId", d."periodEnd", d.action, d.gate,
                    lag(d.action) OVER w AS prev,
                    min(d."periodEnd") FILTER (WHERE d.action IN ('LONG','SHORT')) OVER w AS first_dir
               FROM "DecisionLog" d
              WHERE d."periodEnd" >= %s::date - 40 AND d."periodEnd" <= %s
             WINDOW w AS (PARTITION BY d."assetId" ORDER BY d."periodEnd"))
           SELECT h.*, a.symbol, a.name FROM h JOIN "Asset" a ON a.id = h."assetId"
            WHERE h."periodEnd" = %s ORDER BY a.symbol""",
        (day, day, day),
    )
    changed = [{**r, "kind": classify(r["prev"], r["action"], r["gate"])} for r in cur.fetchall()]
    changed = [r for r in changed if r["kind"]]
    # The start of each ended call, for "day N of the call": one query for every shifted asset, not one
    # per asset (the in-loop ratchet in tests/test_brain.py).
    history: dict[str, list] = {}
    if changed:
        cur.execute(
            """SELECT "assetId", "periodEnd", action FROM "DecisionLog"
                WHERE "assetId" = ANY(%s) AND "periodEnd" < %s AND "periodEnd" >= %s::date - 40""",
            ([r["assetId"] for r in changed], day, day),
        )
        for h in cur.fetchall():
            history.setdefault(h["assetId"], []).append(h)
    shifts = []
    for r in changed:
        start = day
        for h in sorted(history.get(r["assetId"], []), key=lambda h: h["periodEnd"], reverse=True):
            if h["action"] != r["prev"]:
                break
            start = h["periodEnd"]
        shifts.append({**r, "day": (day - start).days + 1})

    cur.execute(
        """SELECT a.symbol, d.action FROM "DecisionLog" d JOIN "Asset" a ON a.id = d."assetId"
            WHERE d."periodEnd" = %s AND d.action IN ('LONG','SHORT') AND d.legs LIKE '%%trigger%%'
            ORDER BY a.symbol""",
        (day,),
    )
    stars = cur.fetchall()
    return completed, shifts, stars


def load_week(cur, start: date):
    end = start + timedelta(days=6)
    cur.execute(
        """SELECT action FROM "DecisionLog" WHERE "periodEnd" BETWEEN %s AND %s""", (start, end)
    )
    rows = cur.fetchall()
    completed: list = []
    flips = 0
    d = start
    while d <= end:
        c, s, _ = load(cur, d)
        completed += c
        flips += len(s)
        d += timedelta(days=1)
    return rows, completed, flips


# --- the document ------------------------------------------------------------------------------


def access_token(info: dict) -> str:
    from google.auth.transport.requests import Request
    from google.oauth2 import service_account

    creds = service_account.Credentials.from_service_account_info(
        info, scopes=["https://www.googleapis.com/auth/documents"]
    )
    creds.refresh(Request())
    return creds.token


def docs_call(method: str, url: str, token: str, body: dict | None = None) -> dict:
    req = urllib.request.Request(
        url, method=method, data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        raw = r.read()
        return json.loads(raw) if raw else {}


def doc_text(doc: dict) -> tuple[str, int]:
    text, end = [], 1
    for el in doc.get("body", {}).get("content", []):
        end = el.get("endIndex", end)
        for pe in (el.get("paragraph") or {}).get("elements", []):
            text.append((pe.get("textRun") or {}).get("content", ""))
    return "".join(text), end


def requests_for(lines: list[tuple[str, str]], at: int) -> list[dict]:
    """One insert of the whole block at `at`, then the styles, by offset into what was inserted."""
    text = "".join(line + "\n" for line, _ in lines)
    reqs: list[dict] = [{"insertText": {"location": {"index": at}, "text": text}}]
    offset = at
    for line, style in lines:
        n = len(line.encode("utf-16-le")) // 2  # Docs indexes count UTF-16 code units
        if style and n:
            rng = {"startIndex": offset, "endIndex": offset + n}
            if style in ("title", "heading"):
                reqs.append({"updateParagraphStyle": {
                    "range": rng,
                    "paragraphStyle": {"namedStyleType": "HEADING_1" if style == "title" else "HEADING_2"},
                    "fields": "namedStyleType"}})
            reqs.append({"updateTextStyle": {"range": rng, "textStyle": {"bold": True}, "fields": "bold"}})
        offset += n + 1
    return reqs


def append(doc_id: str, info: dict, blocks: list[tuple[str, list[tuple[str, str]]]]) -> list[str]:
    token = access_token(info)
    base = f"https://docs.googleapis.com/v1/documents/{doc_id}"
    done = []
    for marker, lines in blocks:
        text, end = doc_text(docs_call("GET", base, token))
        if marker in text:
            done.append(f"already present: {marker}")
            continue
        docs_call("POST", base + ":batchUpdate", token, {"requests": requests_for(lines, max(1, end - 1))})
        done.append(f"appended: {marker}")
    return done


def main(argv: list[str]) -> int:
    day = date.fromisoformat(argv[argv.index("--date") + 1]) if "--date" in argv else datetime.now(timezone.utc).date()
    with db() as conn, conn.cursor() as cur:
        completed, shifts, stars = load(cur, day)
        blocks = []
        if day.weekday() == 0:  # Monday: review the week that just ended
            start = day - timedelta(days=7)
            rows, wk_completed, flips = load_week(cur, start)
            review = weekly_review(start, rows, wk_completed, flips)
            blocks.append((review[2][0], review))
        entry = daily_entry(day, completed, shifts, stars)
        blocks.append((entry[1][0], entry))

    for _, lines in blocks:
        print("\n".join(line for line, _ in lines))

    if "--append" not in argv:
        return 0
    doc_id = (os.environ.get("AUDIT_DOC_ID") or "").strip()
    key = (os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON") or "").strip()
    if not doc_id or not key:
        print("audit log: not appended (AUDIT_DOC_ID and GOOGLE_SERVICE_ACCOUNT_JSON are not both set)")
        return 0
    try:
        for line in append(doc_id, json.loads(key), blocks):
            print("audit log:", line)
    except Exception as e:  # noqa: BLE001 - name only: an auth error can echo request detail
        print(f"audit log: could not append ({type(e).__name__}); the entry above is in the run summary")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
