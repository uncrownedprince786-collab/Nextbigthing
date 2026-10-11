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


def trades_on(asset_type: str | None, day: date) -> bool:
    """Whether an asset of this type has a session on `day`: crypto every day, everything else on weekdays."""
    return (asset_type or "") == "crypto" or day.isoweekday() < 6
