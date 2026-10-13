"""Which bars are sessions, in the SQL every reader of closes uses (brain.md rule 95).

Yahoo answered Saturday and Sunday stub bars for currency pairs after 2026-10-10 and they were stored as
sessions. A weekday market's weekend bar is not a close: read as one it made a Sunday look like a fresh
session, moved every N-session window a day early and fed a one-day return that never traded. Crypto
trades every day and keeps its weekend bars.

`session_bar` is the predicate for a "PriceSnapshot" row; it is equal to `sessionBarSql` in
lib/sessions.ts, which a test pins, so the site and the jobs skip the same bars.
"""

from __future__ import annotations

from datetime import date


def session_bar(alias: str | None = None) -> str:
    """SQL that is true for a bar that is a session: any day for crypto, Monday to Friday otherwise."""
    p = f"{alias}." if alias else ""
    return (
        f'(EXTRACT(ISODOW FROM {p}"date") < 6 OR {p}"assetId" IN '
        f'(SELECT id FROM "Asset" WHERE "assetType" = \'crypto\'))'
    )


def newest_session_bars(
    columns: list[str], *, assets: bool = False, oldest_first: bool = True, as_of: bool = False
) -> str:
    """SQL for the newest `%s` session bars of every asset, one index probe per asset.

    Every caller of this used to say the same thing with `row_number() OVER (PARTITION BY
    "assetId" ORDER BY date DESC)` and a `WHERE rn <= n`, which Postgres can only answer by
    reading and sorting the whole table -- all 781,163 rows to keep the 73,049 the callers
    wanted. There is no loose index scan, so the only way to use `PriceSnapshot_pkey` for a
    per-asset newest is to ask it once per asset: that is the lateral below, and it is the
    same rows in the same order, measured on 2026-10-12.

    Driving from `Asset` rather than from `PriceSnapshot` loses nothing: `assetId` is a
    foreign key onto `Asset` with `ON DELETE CASCADE`, so a priced row without an asset
    cannot exist. It also puts `assetType` in reach, which is how the crypto half of the
    session rule is answered here without the `IN (SELECT ...)` subquery `session_bar` needs.

    Placeholders, in the order they must be passed: the as-of date when `as_of` is set, then
    the row limit, then the asset ids when `assets` is set.
    """
    # `assetId` is always carried out of the lateral, because every caller keys its result by
    # it, and a caller that names it as well must not select it twice.
    rest = [c for c in columns if c != "assetId"]
    inner = ", ".join(f's."{c}"' for c in ["assetId", *rest])
    outer = ", ".join(f'b."{c}"' for c in ["assetId", *rest])
    scope = "\n        WHERE a.id = ANY(%s)" if assets else ""
    # A historical replay wants the newest bars *as they stood* on a past day, not the newest
    # bars now. This is the only difference; the shape and the ordering are untouched.
    bound = "\n              AND s.date <= %s" if as_of else ""
    return f'''
        SELECT {outer}
        FROM "Asset" a
        CROSS JOIN LATERAL (
            SELECT {inner} FROM "PriceSnapshot" s
            WHERE s."assetId" = a.id AND s.close IS NOT NULL{bound}
              AND (EXTRACT(ISODOW FROM s."date") < 6 OR a."assetType" = 'crypto')
            ORDER BY s.date DESC
            LIMIT %s
        ) b{scope}
        ORDER BY b."assetId", b.date {"ASC" if oldest_first else "DESC"}'''


def trades_on(asset_type: str | None, day: date) -> bool:
    """Whether an asset of this type has a session on `day`: crypto every day, everything else on weekdays."""
    return (asset_type or "") == "crypto" or day.isoweekday() < 6
