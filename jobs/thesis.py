"""Remember why a state was entered, and notice when that reason stops being true.

The gap this closes: `AssetSetup` records the conditions behind today's state, and it does
that one day at a time. Nothing compared today against the day the state first appeared, so
a `buy` read that had been sitting there for two weeks on conditions that had quietly
reversed looked exactly like one written this morning on conditions that all pass. The row
was honest about today and silent about the only question that matters once a state is a few
days old: is the reason it exists still there?

A thesis here is a run — a maximal stretch of consecutive stored reads on which an asset
held the same directional state. The run's first day is the day the reason was recorded, and
every later day is measured against *that* day rather than against yesterday.

States
------
    active      the reason is intact: the state still names this direction and every
                condition that carried a verdict on the opening day still carries the same
                one
    weakening   not contradicted, but changed: a condition has flipped its verdict, become
                unavailable, or the state has dropped out of the direction without the
                invalidation being reached
    broken      the invalidation level computed on the opening day has been passed by a
                stored close, or the current read names the opposite direction

Two things this job will not do
-------------------------------
  * It does not re-derive the opening day's conditions from today's data. It reads the row
    `setup.py` wrote on that day. Recomputing them would answer "what would we have said
    then, knowing what we know now", which is the one question the row exists to prevent.
  * It does not rewrite a check. Each day's assessment is its own `ThesisCheck` row, so the
    record of what the system believed on a Tuesday survives Wednesday disagreeing with it.
    A broken thesis is terminal and is never reassessed.

`broken` is the only status resting on a number rather than on a comparison of verdicts, and
that is deliberate: the invalidation level is the one part of a setup written down in
advance, so it is the one part that can be failed rather than merely argued about.

Run: python jobs/thesis.py
Reads: AssetSetup, PriceSnapshot
Writes: AssetThesis, ThesisCheck
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from nbt import db, one, pct, rows, step  # noqa: E402

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except Exception:  # noqa: BLE001
    pass

THESIS = "Compared against the stored condition read from the day the state first appeared"

# The states that make a claim about direction. `wait` and `none` are readings, not theses:
# there is no reason being held that could later stop being true, so there is nothing to
# remember. A run of them simply ends whichever thesis preceded it.
DIRECTIONS = ("buy", "short")

# Verdict tokens `setup.py` writes, as one set. A condition is only compared when both days
# carried one of these: "position: 45% of the way up its range" states a value and passes no
# judgement, so a change in it is a change in the evidence and not a change in a verdict,
# and this job does not pretend otherwise.
VERDICTS = frozenset({"pass", "fail", "up", "down", "mixed"})

# How the opposite direction is named, for the flip test.
OPPOSITE = {"buy": "short", "short": "buy"}


def verdicts(conditions: str) -> dict[str, str]:
    """Parse a stored `conditions` string into {condition name: verdict}.

    `setup.py` writes each condition as "name: text (verdict)", pipe separated, and some of
    them carry no verdict at all. Conditions without one are left out rather than defaulted,
    because a default here would manufacture agreement or disagreement out of a sentence
    that stated neither.

    The verdict is the last comma-separated token inside the final bracket, which is what
    makes "(60%, pass)" and "(up)" both parse without a rule per condition.
    """
    found: dict[str, str] = {}
    for part in conditions.split(" | "):
        part = part.strip()
        if not part or ":" not in part:
            continue
        name, _, rest = part.partition(":")
        rest = rest.rstrip()
        if not rest.endswith(")"):
            continue
        open_at = rest.rfind("(")
        if open_at < 0:
            continue
        token = rest[open_at + 1 : -1].split(",")[-1].strip().lower()
        if token in VERDICTS:
            found[name.strip()] = token
    return found


def compare(opened: dict[str, str], now: dict[str, str]) -> tuple[list[str], list[str]]:
    """(changed, held) condition names, measured against the opening day.

    A condition that had a verdict on the opening day and has none now counts as changed,
    not as held: an input that stopped being available has stopped supporting anything, and
    carrying it forward as a pass is exactly the substitution `setup.py` refuses to make.
    """
    changed, held = [], []
    for name, was in sorted(opened.items()):
        (held if now.get(name) == was else changed).append(name)
    return changed, held


def breached(direction: str, level: float | None, low: float | None, high: float | None) -> bool:
    """Whether a stored close has passed the level the opening day named as invalidation.

    Strictly past, not equal to: the level is the lowest close of the twenty sessions before
    the thesis opened, so a later close at exactly that value has matched the range rather
    than left it.
    """
    if level is None:
        return False
    if direction == "buy":
        return low is not None and low < level
    if direction == "short":
        return high is not None and high > level
    return False


def assess(
    direction: str,
    opened: dict[str, str],
    now: dict[str, str],
    now_state: str | None,
    level: float | None,
    low: float | None,
    high: float | None,
) -> tuple[str, list[str], list[str], str]:
    """(status, changed, held, reason).

    Pure, so the state machine can be tested without a database. The order of the checks is
    the meaning: a passed level outranks a changed verdict, because one was committed to in
    advance and the other is a reading that moves every day.
    """
    changed, held = compare(opened, now)

    if breached(direction, level, low, high):
        edge = low if direction == "buy" else high
        return (
            "broken",
            changed,
            held,
            f"a close of {edge:.2f} passed the {level:.2f} the opening day named as the level "
            "at which the trend this was read from is no longer there",
        )
    if now_state == OPPOSITE[direction]:
        return (
            "broken",
            changed,
            held,
            f"the current read names the opposite direction, {OPPOSITE[direction]}",
        )
    if now_state != direction:
        return (
            "weakening",
            changed,
            held,
            f"the current read is {now_state or 'not stored'} rather than {direction}, and the "
            "invalidation level has not been reached",
        )
    if changed:
        return (
            "weakening",
            changed,
            held,
            f"the state still reads {direction}, but {len(changed)} of the conditions it was "
            f"opened on no longer read the same way: {', '.join(changed)}",
        )
    return (
        "active",
        changed,
        held,
        f"the state still reads {direction} and all {len(held)} conditions that carried a "
        "verdict on the opening day still carry the same one",
    )


def runs(reads: list[dict]) -> list[list[dict]]:
    """Split condition reads, oldest first, into maximal runs of one directional state.

    Only runs of a directional state are returned. A gap in the dates does not split a run:
    a skipped nightly job is a missing observation, and treating it as the end of a thesis
    would restart the clock on a reason that never changed.
    """
    out: list[list[dict]] = []
    current: list[dict] = []
    for read in reads:
        state = read["state"]
        if state in DIRECTIONS and (not current or current[-1]["state"] == state):
            current.append(read)
            continue
        if current:
            out.append(current)
            current = []
        if state in DIRECTIONS:
            current = [read]
    if current:
        out.append(current)
    return out


def grade_for(status: str, changed: list[str], held: list[str]) -> tuple[str, str]:
    """A grade describing how much of the opening reason is still measurable.

    Never how the price has gone. A thesis whose conditions have all held is well evidenced
    whether or not it has worked yet, and grading it on the return would turn a statement
    about evidence into a scorecard.
    """
    compared = len(changed) + len(held)
    if status == "broken":
        return (
            "high",
            "the level named in advance was passed, which is a measurement rather than a reading",
        )
    if not compared:
        return (
            "none",
            "the opening read carried no condition with a verdict, so there is nothing to compare",
        )
    if status == "active":
        return (
            "high" if len(held) >= 3 else "medium",
            f"{len(held)} conditions compared, all unchanged",
        )
    return (
        "medium" if len(held) >= len(changed) else "low",
        f"{len(changed)} of {compared} compared conditions have changed",
    )


THESIS_SQL = """
    INSERT INTO "AssetThesis" ("assetId", horizon, direction, "openedOn",
        "openHeadline", "openConditions", "openClose", "invalidateLevel",
        "entryLevel", status, reason, changed, held, "asOf", "lastClose",
        "changePctSinceOpen", "sessionsSince", confidence, "confidenceNote",
        source, "computedAt")
    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
            %s::"Confidence",%s,%s,now())
    ON CONFLICT ("assetId", horizon, "openedOn") DO UPDATE SET
        status = EXCLUDED.status, reason = EXCLUDED.reason,
        changed = EXCLUDED.changed, held = EXCLUDED.held,
        "asOf" = EXCLUDED."asOf", "lastClose" = EXCLUDED."lastClose",
        "changePctSinceOpen" = EXCLUDED."changePctSinceOpen",
        "sessionsSince" = EXCLUDED."sessionsSince",
        confidence = EXCLUDED.confidence,
        "confidenceNote" = EXCLUDED."confidenceNote",
        "computedAt" = now()
"""

# The check row names its thesis by the thesis's own natural key and looks the id up in the
# statement, so the two batches do not need a round trip between them to exchange ids.
# DO NOTHING rather than an update, so running the job twice in a day cannot overwrite the
# morning's reading with the evening's.
CHECK_SQL = """
    INSERT INTO "ThesisCheck" ("thesisId", "asOf", status, reason, changed,
        held, close, "changePctSinceOpen", source, "computedAt")
    SELECT t.id, %s, %s, %s, %s, %s, %s, %s, %s, now()
      FROM "AssetThesis" t
     WHERE t."assetId" = %s AND t.horizon = %s AND t."openedOn" = %s
    ON CONFLICT ("thesisId", "asOf") DO NOTHING
"""


def main() -> None:
    today = date.today()
    conn = db()
    cur = conn.cursor()
    try:
        step(f"compare each held state against the day it first appeared, as of {today}")
        assets = rows(cur, 'SELECT id, symbol FROM "Asset" ORDER BY symbol')
        opened_count = checked = frozen = 0
        tally = {"active": 0, "weakening": 0, "broken": 0}

        # Four statements for the whole universe, taken before the loop. This job asked for an
        # asset's setup history, then for three price facts and an existing-thesis lookup for
        # every run inside it: eight round trips per asset, and on a host outside the database's
        # region eight minutes of a run.
        reads_by_asset: dict[str, list[dict]] = {}
        for r in rows(
            cur,
            """
            SELECT "assetId", "periodEnd", horizon, state, conditions, "invalidateLevel",
                   "entryLevel", headline
            FROM "AssetSetup" ORDER BY "assetId", horizon, "periodEnd"
            """,
        ):
            reads_by_asset.setdefault(r["assetId"], []).append(r)

        existing_by_key = {
            (r["assetId"], r["horizon"], r["openedOn"]): r
            for r in rows(
                cur, 'SELECT id, status, "assetId", horizon, "openedOn" FROM "AssetThesis"'
            )
        }

        # Closes are needed from the earliest day a thesis could have opened, which is the
        # oldest stored setup. A margin is kept behind it because `open_close` is the newest
        # close at or *before* that day, and a market can have been shut on it.
        oldest = min(
            (r["periodEnd"] for runs_ in reads_by_asset.values() for r in runs_),
            default=today,
        )
        closes_by_asset: dict[str, list[dict]] = {}
        for r in rows(
            cur,
            """
            SELECT "assetId", date, close FROM "PriceSnapshot"
            WHERE close IS NOT NULL AND date >= %s
            ORDER BY "assetId", date
            """,
            (oldest - timedelta(days=30),),
        ):
            closes_by_asset.setdefault(r["assetId"], []).append(r)

        thesis_payload: list[tuple] = []
        check_payload: list[tuple] = []

        for a in assets:
            reads = reads_by_asset.get(a["id"], [])
            if not reads:
                continue
            series_closes = closes_by_asset.get(a["id"], [])
            last_close = series_closes[-1] if series_closes else None

            by_horizon: dict[str, list[dict]] = {}
            for read in reads:
                by_horizon.setdefault(read["horizon"], []).append(read)

            for horizon, series in by_horizon.items():
                latest = series[-1]
                now = verdicts(latest["conditions"])

                for run in runs(series):
                    first = run[0]
                    direction = first["state"]
                    opened_on = first["periodEnd"]

                    existing = existing_by_key.get((a["id"], horizon, opened_on))
                    # A broken thesis is finished. Reassessing it would let a later recovery
                    # quietly erase the fact that the level it named was passed.
                    if existing and existing["status"] == "broken":
                        frozen += 1
                        continue

                    # The same three facts, taken from the series already in hand: the range
                    # since the thesis opened, the close it opened at, and the newest close.
                    after = [c for c in series_closes if c["date"] > opened_on]
                    low = min((float(c["close"]) for c in after), default=None)
                    high = max((float(c["close"]) for c in after), default=None)
                    sessions = len(after)
                    open_close = next(
                        (c for c in reversed(series_closes) if c["date"] <= opened_on), None
                    )

                    level = (
                        float(first["invalidateLevel"])
                        if first["invalidateLevel"] is not None
                        else None
                    )
                    status, changed, held, reason = assess(
                        direction, verdicts(first["conditions"]), now, latest["state"],
                        level, low, high,
                    )
                    grade, note = grade_for(status, changed, held)

                    since = None
                    if open_close and last_close and open_close["close"]:
                        since = pct(float(last_close["close"]), float(open_close["close"]))

                    thesis_payload.append(
                        (
                            a["id"], horizon, direction, opened_on,
                            first["headline"], first["conditions"],
                            float(open_close["close"]) if open_close and open_close["close"] is not None else None,
                            level,
                            float(first["entryLevel"]) if first["entryLevel"] is not None else None,
                            status, reason,
                            ", ".join(changed) or "none", ", ".join(held) or "none",
                            latest["periodEnd"],
                            float(last_close["close"]) if last_close and last_close["close"] is not None else None,
                            since, sessions, grade, note, THESIS,
                        )
                    )
                    if not existing:
                        opened_count += 1
                    tally[status] += 1

                    # One frozen row per assessment date. DO NOTHING rather than an update,
                    # so running the job twice in a day cannot overwrite the morning's
                    # reading with the evening's.
                    # The check row is keyed on the thesis, which does not have an id until
                    # the batch above lands. It is collected against the thesis's natural key
                    # and resolved to the id in one statement after the loop.
                    check_payload.append(
                        (
                            latest["periodEnd"], status, reason,
                            ", ".join(changed) or "none", ", ".join(held) or "none",
                            float(last_close["close"]) if last_close and last_close["close"] is not None else None,
                            since, THESIS,
                            a["id"], horizon, opened_on,
                        )
                    )
                    checked += 1

        if thesis_payload:
            cur.executemany(THESIS_SQL, thesis_payload)
        if check_payload:
            cur.executemany(CHECK_SQL, check_payload)
        conn.commit()

        print(
            f"  {checked} theses assessed, {opened_count} opened for the first time, "
            f"{frozen} left alone because they are already broken"
        )
        print(
            f"  active {tally['active']}, weakening {tally['weakening']}, "
            f"broken {tally['broken']}"
        )
        if not checked:
            print(
                "  no directional state is stored yet. Theses only exist for buy and short "
                "reads, so this stays empty until setup.py writes one."
            )
        print(
            "  a status describes whether the recorded reason is still measurable. It is not "
            "advice and it does not say what will happen."
        )
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
