"""Grade each published call as a trade, from its own recorded levels, apart from its direction (rule 95).

    python tools/trade_sim.py              grade, print the summary, write nothing
    python tools/trade_sim.py --write      also store each call's outcome and the day's summary

Directional accuracy is not a profitable edge. A call can point the right way and never be fillable at
its entry, or fill and reach its stop before its target. So every published call recorded by a decision
run ("DecisionCall", tools/decide.mjs) is graded twice, into separate fields of "CallOutcome":

  * **direction** -- the scorecard's verdict, unchanged (tools/scorecard.py): the stop first, over the
    sessions' lows and highs, then the sign of the five-session move from the call's close;
  * **trade** -- a simulation of the call's own plan, on the daily bars after the session it was read from.

The plan and its assumptions, every one stated because nothing here can be observed intraday:

  * Entry is a limit order at the zone edge the reward:risk is measured from -- the top of the zone for a
    LONG, the bottom for a SHORT (lib/target.ts). It fills on the first session whose range reaches it, at
    that price, or at the open when the session opens beyond it on the better side. Nothing fills on the
    session the call was read from: the call is made after that close.
  * A session that opens beyond the stop before the order has filled invalidates the plan
    (INVALIDATED_BEFORE_FILL): the level that says the reading is wrong was crossed before entry.
  * After the fill, the stop and the measured exit are resting orders. A session that opens beyond either
    exits at the open (a gap through the stop is recorded, and its loss is larger than one R). A session
    whose range reaches both is AMBIGUOUS -- daily bars cannot say which came first -- and is never
    counted as the favourable one: the conservative expectancy books it at the stop. On the session the
    order filled inside the range, a touch of the exit is not counted (it may have come before the fill),
    while a touch of the stop is (it may have come after).
  * The window is the call's own validity (lib/validity.ts: seven days for a swing setup, 28 for a
    position). A filled trade still open when it ends exits at that session's close (EXPIRED); an order
    still unfilled is NOT_FILLED. Both count in the denominator.
  * A call a later run withdrew -- a different verdict at the end of an earlier day than the fill -- is
    WITHDRAWN if it had not filled. A bar whose prices contradict each other (a close outside its own
    range), or a closed window with no bars at all, is UNAVAILABLE. Neither is dropped.
  * R is gross: the result over the risk from the fill to the stop. No spread, commission, borrow or
    slippage is modelled, because none of it is stored; net R is not reported.

One trade per position: a call re-issued by later runs, or by the next day's run while it stays open, is
the same position, and only the first published call of it -- per asset, side and validity start -- is
graded. Two or three runs on one day therefore cannot count one trade two or three times. No rate is
claimed as an edge until it has `MIN_SAMPLE` closed trades behind it, and every rate prints its count.
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "jobs"))

import costs as cost_model  # noqa: E402  (after the sys.path line above)
sys.path.insert(0, str(ROOT / "tools"))
from scorecard import MIN_SAMPLE, band_in, stop_was_hit, verdict_of  # noqa: E402

TRADE_STATES = (
    "NOT_FILLED", "INVALIDATED_BEFORE_FILL", "WITHDRAWN", "STOP_FIRST", "TARGET_FIRST",
    "EXPIRED", "AMBIGUOUS", "UNAVAILABLE", "PENDING",
)
CLOSED = ("STOP_FIRST", "TARGET_FIRST", "EXPIRED", "AMBIGUOUS")
SWING_DAYS = 7
DIRECTION_SESSIONS = 5
# A close may sit on its own high or low; a hair outside it is rounding, more is a bar that contradicts itself.
_EPS = 1e-9


def _num(x) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if v == v else None


def _consistent(o, h, lo, c) -> bool:
    if None in (o, h, lo, c) or lo > h:
        return False
    tol = max(abs(h), abs(lo), 1.0) * 1e-6 + _EPS
    return lo - tol <= c <= h + tol and lo - tol <= o <= h + tol


def simulate(call: dict, bars: list[tuple], today: date, verdicts: list[tuple[date, str]] = ()) -> dict:
    """The trade outcome of one call. Pure: the bars, the clock and later verdicts are inputs.

    `call`: action, entryLow, entryHigh, stop, target, baseSession, validUntil.
    `bars`: (day, open, high, low, close) for the asset's sessions, any order; only those after
    `baseSession` and through the window are read.
    `verdicts`: (periodEnd, action) of the asset's calls in later valid runs, the newest run of each day.
    """
    action = call.get("action")
    long = action == "LONG"
    out = {"trade": "PENDING", "fillOn": None, "fillPrice": None, "exitOn": None, "exitPrice": None,
           "grossR": None, "gapThrough": False, "sessions": 0, "final": False, "note": None,
           # Carried for the cost model only. Nothing writes it: the INSERT names its columns.
           "risk": None}
    if action not in ("LONG", "SHORT"):
        return {**out, "trade": "UNAVAILABLE", "final": True, "note": "not a directional call"}
    lo_z, hi_z = _num(call.get("entryLow")), _num(call.get("entryHigh"))
    stop, target = _num(call.get("stop")), _num(call.get("target"))
    base = call.get("baseSession")
    if None in (lo_z, hi_z, stop, target) or base is None:
        return {**out, "trade": "UNAVAILABLE", "final": True, "note": "the call recorded no full plan (entry, stop and exit)"}
    until = call.get("validUntil") or (base + timedelta(days=SWING_DAYS))
    matured = today > until
    entry = hi_z if long else lo_z
    window = sorted((b for b in bars if base < b[0] <= until), key=lambda b: b[0])
    if not window:
        if matured:
            return {**out, "trade": "UNAVAILABLE", "final": True, "note": f"no session bar stored between {base} and {until}"}
        return out

    # The verdict standing at the end of each day, from later runs.
    standing = sorted(verdicts, key=lambda v: v[0])

    def withdrawn_by(day: date) -> bool:
        latest = None
        for when, act in standing:
            if when < day:
                latest = act
        return latest is not None and latest != action

    fill = None
    filled_inside = False
    for i, (day, o, h, lo, c) in enumerate(window):
        o, h, lo, c = _num(o), _num(h), _num(lo), _num(c)
        out["sessions"] = i + 1
        if not _consistent(o, h, lo, c):
            return {**out, "trade": "UNAVAILABLE", "final": True,
                    "note": f"the bar of {day} contradicts itself (open {o}, high {h}, low {lo}, close {c})"}
        if fill is None:
            if withdrawn_by(day):
                return {**out, "trade": "WITHDRAWN", "final": True, "note": "a later run withdrew the call before it filled"}
            if (long and o <= stop) or (not long and o >= stop):
                return {**out, "trade": "INVALIDATED_BEFORE_FILL", "final": True,
                        "note": f"{day} opened beyond the stop before the order filled"}
            reached = lo <= entry if long else h >= entry
            if not reached:
                continue
            at_open = (o <= entry) if long else (o >= entry)
            fill = o if at_open else entry
            filled_inside = not at_open
            out["fillOn"], out["fillPrice"] = day, fill
            risk = (fill - stop) if long else (stop - fill)
            out["risk"] = round(risk, 6) if risk > 0 else None
            if risk <= 0:
                return {**out, "trade": "UNAVAILABLE", "final": True, "note": "the fill sat at or beyond the stop"}
            # The fill session itself: the stop counts, the exit only when the order filled at the open.
            hit_stop = lo <= stop if long else h >= stop
            hit_target = (h >= target if long else lo <= target) and not filled_inside
            if hit_stop and hit_target:
                return {**out, "trade": "AMBIGUOUS", "final": True, "exitOn": day,
                        "note": f"{day} reached both the stop and the exit; daily bars cannot order them"}
            if hit_stop:
                return {**out, "trade": "STOP_FIRST", "final": True, "exitOn": day, "exitPrice": stop, "grossR": -1.0}
            if hit_target:
                return {**out, "trade": "TARGET_FIRST", "final": True, "exitOn": day, "exitPrice": target,
                        "grossR": round(((target - fill) if long else (fill - target)) / risk, 4)}
            continue
        risk = (fill - stop) if long else (stop - fill)
        out["risk"] = round(risk, 6) if risk > 0 else None
        gap_stop = o <= stop if long else o >= stop
        gap_target = o >= target if long else o <= target
        if gap_stop:
            return {**out, "trade": "STOP_FIRST", "final": True, "exitOn": day, "exitPrice": o, "gapThrough": True,
                    "grossR": round(((o - fill) if long else (fill - o)) / risk, 4), "note": f"{day} opened through the stop"}
        if gap_target:
            return {**out, "trade": "TARGET_FIRST", "final": True, "exitOn": day, "exitPrice": o,
                    "grossR": round(((o - fill) if long else (fill - o)) / risk, 4), "note": f"{day} opened through the exit"}
        hit_stop = lo <= stop if long else h >= stop
        hit_target = h >= target if long else lo <= target
        if hit_stop and hit_target:
            return {**out, "trade": "AMBIGUOUS", "final": True, "exitOn": day,
                    "note": f"{day} reached both the stop and the exit; daily bars cannot order them"}
        if hit_stop:
            return {**out, "trade": "STOP_FIRST", "final": True, "exitOn": day, "exitPrice": stop, "grossR": -1.0}
        if hit_target:
            return {**out, "trade": "TARGET_FIRST", "final": True, "exitOn": day, "exitPrice": target,
                    "grossR": round(((target - fill) if long else (fill - target)) / risk, 4)}

    if not matured:
        return out
    if fill is None:
        return {**out, "trade": "NOT_FILLED", "final": True, "note": f"the entry was not reached by {until}"}
    day, _, _, _, c = window[-1]
    c = _num(c)
    risk = (fill - stop) if long else (stop - fill)
    return {**out, "trade": "EXPIRED", "final": True, "exitOn": day, "exitPrice": c,
            "grossR": round(((c - fill) if long else (fill - c)) / risk, 4), "note": f"still open when the window ended on {until}"}


def directional(call: dict, bars: list[tuple]) -> tuple[str, float | None]:
    """The scorecard's verdict for the call (stop first, then the five-session move), and the move in %."""
    action, base = call.get("action"), call.get("baseSession")
    close = _num(call.get("baseClose"))
    after = sorted((b for b in bars if base is not None and b[0] > base), key=lambda b: b[0])
    if action not in ("LONG", "SHORT") or close is None or base is None:
        return "unavailable", None
    if len(after) < DIRECTION_SESSIONS:
        return "pending", None
    fifth = after[DIRECTION_SESSIONS - 1]
    series = [(d, _num(c), _num(lo), _num(h)) for d, _o, h, lo, c in after[:DIRECTION_SESSIONS]]
    lo, hi = band_in(series, base, fifth[0])
    move = (_num(fifth[4]) / close - 1.0) * 100.0 if _num(fifth[4]) is not None and close else None
    v = verdict_of(action, move, stop_was_hit(action, _num(call.get("stop")), lo, hi))
    return (v or "pending"), (round(move, 4) if move is not None else None)


def units(calls: list[dict]) -> list[dict]:
    """The calls graded: the first published call of each position (asset, side, validity start), taken from
    the earliest valid run that made it. `calls` carry `startedAt` of their run."""
    first: dict[tuple, dict] = {}
    for c in sorted(calls, key=lambda c: (c["startedAt"], c["id"])):
        if not c.get("published") or c.get("action") not in ("LONG", "SHORT"):
            continue
        key = (c["assetId"], c["action"], c.get("validFrom") or c.get("baseSession"))
        first.setdefault(key, c)
    return list(first.values())


def standing_verdicts(calls: list[dict]) -> dict[str, list[tuple[date, str]]]:
    """Per asset, the verdict of the newest valid run of each day: what a reader saw at that day's end."""
    newest: dict[tuple[str, date], tuple] = {}
    for c in calls:
        k = (c["assetId"], c["periodEnd"])
        if k not in newest or (c["startedAt"], c["id"]) > newest[k][0]:
            newest[k] = ((c["startedAt"], c["id"]), c["action"])
    out: dict[str, list[tuple[date, str]]] = defaultdict(list)
    for (asset, day), (_, act) in newest.items():
        out[asset].append((day, act))
    return out


def grade(calls: list[dict], bars_by_asset: dict[str, list[tuple]], today: date) -> list[dict]:
    """Every graded call with both outcomes. Deterministic: the same inputs grade the same way every time."""
    verdicts = standing_verdicts(calls)
    graded = []
    for c in units(calls):
        bars = bars_by_asset.get(c["assetId"], [])
        later = [(d, a) for d, a in verdicts.get(c["assetId"], []) if d > c["periodEnd"]]
        t = simulate(c, bars, today, later)
        d, move = directional(c, bars)
        graded.append({**c, **t, "direction": d, "move5Pct": move,
                       "final": bool(t["final"]) and d not in ("pending",)})
    return graded


def _rate(k: int, n: int) -> dict:
    return {"k": k, "n": n, "rate": (round(k / n, 4) if n else None)}


# `Asset.assetType` is not on the call row, but the market is, and the cost bands differ by venue
# rather than by instrument class. PSX and US are both cash equity; everything else maps straight.
MARKET_COST_TYPE = {"US": "stock", "PSX": "stock", "Crypto": "crypto", "FX": "forex", "Commodity": "commodity"}


def net_band(rows: list[dict]) -> dict:
    """Mean net R under each cost scenario, over the trades that actually closed.

    Separate from the gross mean beside it and never a replacement for it: every number here
    rests on `tools/costs.py`, which is a stated band of assumptions and not a measurement. A
    trade the model will not price -- a short where retail cannot short -- is left out rather
    than counted at its gross result, and `n` says how many survived for that reason.
    """
    out: dict[str, object] = {"assumed": True, "basis": "tools/costs.py bands, not measured"}
    for scenario in cost_model.SCENARIOS:
        vals = []
        for r in rows:
            if r["trade"] not in ("STOP_FIRST", "TARGET_FIRST", "EXPIRED"):
                continue
            kind = MARKET_COST_TYPE.get(r.get("market") or "")
            if kind is None or r.get("risk") in (None, 0) or r.get("fillPrice") in (None, 0):
                continue
            v = cost_model.net_r(
                r["grossR"], fill=r["fillPrice"], risk=r["risk"], asset_type=kind,
                short=(r.get("side") or "").upper() == "SHORT",
                sessions=int(r.get("sessions") or 0), scenario=scenario, market=r.get("market"),
            )
            if v is not None:
                vals.append(v)
        out[scenario] = {"n": len(vals),
                         "meanR": (round(sum(vals) / len(vals), 4) if vals else None)}
    return out


def bucket(rows: list[dict]) -> dict:
    """Counts and rates for one group of graded calls. Every rate carries its count; none is an edge yet."""
    trades = Counter(r["trade"] for r in rows)
    evaluable = sum(v for k, v in trades.items() if k not in ("PENDING",))
    filled = sum(trades[k] for k in CLOSED)
    closed_r = [r["grossR"] for r in rows if r["trade"] in ("STOP_FIRST", "TARGET_FIRST", "EXPIRED") and r["grossR"] is not None]
    # Conservative: an ambiguous bar is booked at the stop.
    conservative = closed_r + [-1.0] * trades["AMBIGUOUS"]
    net = net_band(rows)
    directions = Counter(r["direction"] for r in rows)
    judged = directions["right"] + directions["wrong"] + directions["stopped"] + directions["flat"]
    return {
        "calls": len(rows),
        "net": net,
        "evaluable": evaluable,
        "pending": trades["PENDING"],
        "trades": {k: trades[k] for k in TRADE_STATES},
        "fillRate": _rate(filled, evaluable - trades["UNAVAILABLE"]),
        "targetFirst": _rate(trades["TARGET_FIRST"], filled),
        "stopFirst": _rate(trades["STOP_FIRST"], filled),
        "expired": _rate(trades["EXPIRED"], filled),
        "ambiguous": _rate(trades["AMBIGUOUS"], filled),
        "gapThrough": sum(1 for r in rows if r["gapThrough"]),
        "grossRExpectancy": {
            "n": len(conservative),
            "mean": (round(sum(conservative) / len(conservative), 4) if conservative else None),
            "measured": len(conservative) >= MIN_SAMPLE,
        },
        "direction": {
            "judged": judged,
            "right": directions["right"], "wrong": directions["wrong"],
            "stopped": directions["stopped"], "flat": directions["flat"], "pending": directions["pending"],
            "accurate": _rate(directions["right"], judged),
        },
    }


def summarise(graded: list[dict], today: date) -> dict:
    """The whole set and its splits by market, side, horizon and confidence."""
    def split(key):
        groups: dict[str, list[dict]] = defaultdict(list)
        for r in graded:
            groups[str(r.get(key) or "unknown")].append(r)
        return {k: bucket(v) for k, v in sorted(groups.items())}

    first = min((r["periodEnd"] for r in graded), default=None)
    return {
        "asOf": today.isoformat(),
        "since": first.isoformat() if first else None,
        "minSample": MIN_SAMPLE,
        "all": bucket(graded),
        "byMarket": split("market"),
        "bySide": split("action"),
        "byHorizon": split("horizon"),
        "byConfidence": split("confidence"),
        "assumptions": [
            "entry: a limit at the zone edge the reward:risk is measured from, filled from the session after the call",
            "exits: the stop and the measured exit as resting orders; a gap fills at the open",
            "a session reaching both is AMBIGUOUS and booked at the stop in the expectancy",
            "window: the call's validity (7 days swing, 28 position); an open trade exits at its last close",
            "R is gross: no spread, commission, borrow or slippage is stored, so no net R is reported",
        ],
    }


# --- the database -------------------------------------------------------------------------------

CALLS_SQL = """
    SELECT c.id, c."runId", c."assetId", c.symbol, c.market, c."periodEnd", c."baseSession", c."baseClose",
           c.action, c.confidence, c."entryLow", c."entryHigh", c.stop, c.target, c.published, c.horizon,
           c."validFrom", c."validUntil", r."startedAt"
      FROM "DecisionCall" c JOIN "DecisionRun" r ON r.id = c."runId"
     WHERE r.status IN ('complete', 'partial')
"""

UPSERT_OUTCOME = """
    INSERT INTO "CallOutcome" ("callId", "evaluatedAt", final, direction, "move5Pct", trade, "fillOn", "fillPrice",
                               "exitOn", "exitPrice", "grossR", "gapThrough", sessions, note)
    VALUES (%s, now(), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT ("callId") DO UPDATE SET
        "evaluatedAt" = now(), final = EXCLUDED.final, direction = EXCLUDED.direction, "move5Pct" = EXCLUDED."move5Pct",
        trade = EXCLUDED.trade, "fillOn" = EXCLUDED."fillOn", "fillPrice" = EXCLUDED."fillPrice",
        "exitOn" = EXCLUDED."exitOn", "exitPrice" = EXCLUDED."exitPrice", "grossR" = EXCLUDED."grossR",
        "gapThrough" = EXCLUDED."gapThrough", sessions = EXCLUDED.sessions, note = EXCLUDED.note
    WHERE NOT "CallOutcome".final
"""


def load(cur) -> tuple[list[dict], dict[str, list[tuple]]]:
    from sessions import session_bar

    cur.execute(CALLS_SQL)
    calls = [dict(r) for r in cur.fetchall()]
    graded_assets = sorted({c["assetId"] for c in units(calls)})
    bars: dict[str, list[tuple]] = defaultdict(list)
    if graded_assets:
        oldest = min(c["baseSession"] or c["periodEnd"] for c in calls if c["assetId"] in set(graded_assets))
        cur.execute(
            """SELECT "assetId", date, open, high, low, close FROM "PriceSnapshot"
                WHERE "assetId" = ANY(%s) AND date > %s AND """ + session_bar() + """
                ORDER BY "assetId", date""",
            (graded_assets, oldest),
        )
        for r in cur.fetchall():
            bars[r["assetId"]].append((r["date"], r["open"], r["high"], r["low"], r["close"]))
    return calls, bars


def main(argv: list[str]) -> int:
    from nbt import db

    today = datetime.now(timezone.utc).date()
    with db() as conn, conn.cursor() as cur:
        cur.execute("SELECT to_regclass('public.\"DecisionCall\"') AS t")
        if cur.fetchone()["t"] is None:
            print('trade sim: no "DecisionCall" table yet (migration 20261011130000_decision_history); nothing to grade')
            return 0
        calls, bars = load(cur)
        graded = grade(calls, bars, today)
        summary = summarise(graded, today)
        a = summary["all"]
        print(f"trade sim: {a['calls']} published positions from {len(calls)} recorded calls since {summary['since']}")
        print(f"  trades: {json.dumps(a['trades'])}")
        print(f"  fill rate {a['fillRate']}, gross R expectancy {a['grossRExpectancy']}")
        net = a.get("net") or {}
        band = ", ".join(
            f"{k} {(net.get(k) or {}).get('meanR')} (n={(net.get(k) or {}).get('n')})"
            for k in cost_model.SCENARIOS
        )
        # Printed apart from the gross line and labelled, because these rest on assumed costs.
        print(f"  net R by assumed cost scenario: {band}")
        print("    costs are assumptions from tools/costs.py, not measured; gross above is unchanged")
        print(f"  direction {a['direction']}")
        if "--write" in argv:
            cur.executemany(UPSERT_OUTCOME, [
                (g["id"], g["final"], g["direction"], g["move5Pct"], g["trade"], g["fillOn"], g["fillPrice"],
                 g["exitOn"], g["exitPrice"], g["grossR"], g["gapThrough"], g["sessions"], g["note"])
                for g in graded
            ])
            cur.execute(
                """INSERT INTO "AuditLog" (day, kind, title, lines) VALUES (%s, 'trades', %s, %s::jsonb)
                   ON CONFLICT (day, kind) DO UPDATE SET title = EXCLUDED.title, lines = EXCLUDED.lines""",
                (today, f"Simulated trades as of {today.isoformat()}", json.dumps(summary)),
            )
            conn.commit()
            print(f"trade sim: stored {len(graded)} outcomes and the summary for {today.isoformat()}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
