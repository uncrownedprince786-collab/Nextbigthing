"""Split an asset's recent move into the part the whole market made, the part its own
industry made, and the part that is left over.

Three competing accounts of the same move, measured rather than asserted:

    market      every asset quoted in the same exchange group moved about this much, so the
                move is what holding anything in that group did
    sector      its own industry moved further than the group did, so the move is what
                holding this industry did
    specific    neither of the above accounts for it, so what is left is particular to this
                asset

They are exclusive by construction, not by argument:

    total = market + sector + specific

where `market` is the median return across the exchange group, `sector` is the median across
the asset's own industry peers *minus* that market median, and `specific` is the asset's own
return minus its peer median. Medians rather than means throughout, because one 400% crypto
return would otherwise describe a sector nobody is in.

What this is not
----------------
This is co-movement, and it is reported as exactly that. It does not say the market caused
anything, and the leading component is the one the move is most *shared with*, which is a
different sentence from the one about cause. The words "because", "driven by" and "in
response to" do not appear in the output for the same reason they are banned from
`jobs/analysis.py`.

It is also not a posterior. A likelihood ratio needs a measured `P(E|H)`, no outcome row in
this database has matured, and choosing those numbers by hand would be fabrication. So the
three hypotheses carry measured magnitudes and shares, and the row says plainly that no
probability is attached to any of them.

A leader is only named when the sample supports one. Below MIN_PEERS the peer median is an
average of two or three names and the sector/specific split is noise; below DOMINANCE the
top two are too close to separate, and the row says they are too close instead of picking.

Run: python jobs/attribution.py
Reads: PriceSnapshot, Asset, Industry
Writes: MoveAttribution
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from nbt import db, median, rows, step  # noqa: E402

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except Exception:  # noqa: BLE001
    pass

METHOD = (
    "Median peer and median group returns over stored closes. A decomposition of shared "
    "movement, not a statement of cause"
)

# Sessions the move is measured over, and the calendar reach that gets roughly that many
# trading days. Both named here because the label has to mean the window actually used.
WINDOW_SESSIONS = 20
FOR_DAYS = 28

# Peers needed before the sector and specific parts are separated at all. Three is the floor
# jobs/setup.py already uses for an industry comparison, repeated rather than loosened: a
# median of two is the mean of two, and splitting a move against it would be arithmetic
# dressed as evidence.
MIN_PEERS = 3
# Names needed in the exchange group before the market part is treated as a market reading
# rather than as a handful of assets that happen to be stored.
MIN_GROUP = 8
# How much larger the top component must be than the second before it is called the leader.
DOMINANCE = 1.25

COMPONENT_WORDS = {
    "market": "what everything quoted in its exchange group did",
    "sector": "what its own industry did beyond the group",
    "specific": "what is left after both, which is particular to this asset",
}

# The leading component's own sentence. `specific` needs its own wording rather than a slot
# in a shared one: "the move is mostly shared with what is left over" is self-contradictory,
# because the left-over part is by definition the part that is not shared.
LEADER_SENTENCE = {
    "market": "The move is mostly shared with what everything quoted in its exchange group did.",
    "sector": "The move is mostly shared with what its own industry did beyond the group.",
    "specific": (
        "The largest of the three is the part left after both, so most of this move is not "
        "shared with its exchange group or its industry."
    ),
}


def decompose(asset_pct: float, peer_median: float, market_median: float) -> dict[str, float]:
    """The three parts, which sum to the asset's own return by construction."""
    return {
        "market": market_median,
        "sector": peer_median - market_median,
        "specific": asset_pct - peer_median,
    }


def shares(parts: dict[str, float]) -> dict[str, float] | None:
    """Each part's size as a share of the total movement accounted for.

    Absolute values, because a sector that fell while the asset rose has still accounted for
    a chunk of the distance between them, and signing the denominator would let two parts
    cancel into a share above one. None when every part is zero, which is a flat window and
    not a 100% attribution to anything.
    """
    total = sum(abs(v) for v in parts.values())
    if total <= 0:
        return None
    return {k: abs(v) / total for k, v in parts.items()}


def leader(
    parts: dict[str, float], peers: int, group: int
) -> tuple[str | None, float | None, str]:
    """(name, margin, why). None when the sample or the gap does not support naming one."""
    if peers < MIN_PEERS:
        return None, None, (
            f"only {peers} peers in its industry have the history to take a median from, "
            f"below the {MIN_PEERS} needed, so the industry and asset specific parts are not "
            "separated"
        )
    if group < MIN_GROUP:
        return None, None, (
            f"only {group} assets in its exchange group have the history to take a median "
            f"from, below the {MIN_GROUP} needed for a market reading"
        )
    ordered = sorted(parts.items(), key=lambda kv: abs(kv[1]), reverse=True)
    top, second = ordered[0], ordered[1]
    if abs(second[1]) <= 0:
        return top[0], None, "the other components are flat over this window"
    margin = abs(top[1]) / abs(second[1])
    if margin < DOMINANCE:
        return None, margin, (
            f"the largest two components are within {margin:.2f} times of each other, below "
            f"the {DOMINANCE} needed to separate them, so neither is named"
        )
    return top[0], margin, f"{margin:.2f} times the next largest component"


def sentence(total: float, parts: dict[str, float] | None, market: float, named: str | None) -> str:
    """One plain line. Every figure in it is one of the stored numbers."""
    if parts is None:
        return (
            f"Of its {WINDOW_SESSIONS} session move of {total:+.1f}%, {market:+.1f} points is "
            f"what everything quoted in its exchange group did. The remaining "
            f"{total - market:+.1f} points cannot be split between its industry and the asset "
            f"itself: fewer than {MIN_PEERS} peers have the history to take a median from."
        )
    body = (
        f"Of its {WINDOW_SESSIONS} session move of {total:+.1f}%, {parts['market']:+.1f} "
        f"points is what everything quoted in its exchange group did, {parts['sector']:+.1f} "
        f"points is what its own industry did beyond that, and {parts['specific']:+.1f} "
        "points is left over after both."
    )
    if named:
        return f"{body} {LEADER_SENTENCE[named]}"
    return f"{body} No one of the three is far enough ahead of the others to be named."


def returns(cur) -> list[dict]:
    """Every asset's return over the window, with its industry and exchange group.

    One query rather than one per asset: the medians need the whole population anyway, and
    160 round trips to compute a figure that is the same for every member of a group is the
    kind of cost that turns a nightly job into a queue.
    """
    return rows(
        cur,
        """
        WITH newest AS (
            SELECT a.id, a.symbol, a."industryId", i.market, max(p.date) AS asof
            FROM "Asset" a
            JOIN "Industry" i ON i.id = a."industryId"
            JOIN "PriceSnapshot" p ON p."assetId" = a.id AND p.close IS NOT NULL
            GROUP BY a.id, a.symbol, a."industryId", i.market
        )
        SELECT n.id, n.symbol, n."industryId", n.market, n.asof,
               (SELECT close FROM "PriceSnapshot"
                 WHERE "assetId" = n.id AND date = n.asof) AS last,
               (SELECT close FROM "PriceSnapshot"
                 WHERE "assetId" = n.id AND date <= n.asof - (%s * interval '1 day')
                 ORDER BY date DESC LIMIT 1) AS base
        FROM newest n
        """,
        (FOR_DAYS,),
    )


def main() -> None:
    today = date.today()
    conn = db()
    cur = conn.cursor()
    try:
        step("split each recent move into market, industry and asset specific parts")
        got = returns(cur)
        pcts: dict[str, float] = {}
        meta: dict[str, dict] = {}
        for r in got:
            if r["last"] is None or r["base"] is None or float(r["base"]) <= 0:
                continue
            pcts[r["id"]] = (float(r["last"]) / float(r["base"]) - 1.0) * 100.0
            meta[r["id"]] = r

        print(
            f"  {len(pcts)} of {len(got)} assets have {FOR_DAYS} calendar days of stored "
            "closes behind them"
        )

        by_industry: dict[str, list[str]] = {}
        by_market: dict[str, list[str]] = {}
        for asset_id, m in meta.items():
            by_industry.setdefault(m["industryId"], []).append(asset_id)
            by_market.setdefault(m["market"], []).append(asset_id)

        # The market median is one figure per exchange group, so it is computed once per
        # group rather than once per asset. Excluding the asset itself from its own market
        # median would change the figure by a 160th and make it a different number for every
        # row, which is worse: the group reading is meant to be the same thing every member
        # is compared against.
        market_median = {
            group: median([pcts[i] for i in ids]) for group, ids in by_market.items()
        }

        written = named_count = 0
        undecided: dict[str, int] = {}

        for asset_id, mine in sorted(pcts.items(), key=lambda kv: meta[kv[0]]["symbol"]):
            m = meta[asset_id]
            group_ids = by_market[m["market"]]
            peer_ids = [i for i in by_industry[m["industryId"]] if i != asset_id]
            market = market_median[m["market"]]
            if market is None:
                continue

            # With too few peers there is no peer median to subtract. The sector and specific
            # parts are then left null rather than estimated: crediting the whole non-market
            # remainder to the asset would read as a finding about the asset, when all it
            # measures is that its industry is thinly covered here.
            peer_med = median([pcts[i] for i in peer_ids]) if len(peer_ids) >= MIN_PEERS else None
            parts = decompose(mine, peer_med, market) if peer_med is not None else None
            split = shares(parts) if parts else None
            name, margin, why = (
                leader(parts, len(peer_ids), len(group_ids))
                if parts
                else (None, None, leader({}, len(peer_ids), len(group_ids))[2])
            )

            if name:
                named_count += 1
            else:
                key = why.split(",")[0][:48]
                undecided[key] = undecided.get(key, 0) + 1

            if len(peer_ids) < MIN_PEERS:
                grade = "low"
            elif len(peer_ids) >= 5 and len(group_ids) >= 20 and name:
                grade = "high"
            else:
                grade = "medium"

            note = (
                f"{len(peer_ids)} industry peers and {len(group_ids)} assets in the "
                f"{m['market']} group had enough history to take a median from. {why}. No "
                "probability is attached to any of the three: that would need a measured "
                "likelihood and no outcome row in this database has matured yet"
            )

            cur.execute(
                """
                INSERT INTO "MoveAttribution" ("assetId", "periodEnd", "windowDays",
                    "totalPct", "marketPct", "sectorPct", "specificPct", "marketShare",
                    "sectorShare", "specificShare", leader, "leaderMargin", peers,
                    "groupSize", headline, confidence, "confidenceNote", method, source,
                    "computedAt")
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::"Confidence",%s,%s,%s,
                        now())
                ON CONFLICT ("assetId", "periodEnd", "windowDays") DO UPDATE SET
                    "totalPct" = EXCLUDED."totalPct", "marketPct" = EXCLUDED."marketPct",
                    "sectorPct" = EXCLUDED."sectorPct",
                    "specificPct" = EXCLUDED."specificPct",
                    "marketShare" = EXCLUDED."marketShare",
                    "sectorShare" = EXCLUDED."sectorShare",
                    "specificShare" = EXCLUDED."specificShare",
                    leader = EXCLUDED.leader, "leaderMargin" = EXCLUDED."leaderMargin",
                    peers = EXCLUDED.peers, "groupSize" = EXCLUDED."groupSize",
                    headline = EXCLUDED.headline, confidence = EXCLUDED.confidence,
                    "confidenceNote" = EXCLUDED."confidenceNote",
                    "computedAt" = now()
                """,
                (
                    asset_id, today, WINDOW_SESSIONS, mine,
                    market,
                    parts["sector"] if parts else None,
                    parts["specific"] if parts else None,
                    split["market"] if split else None,
                    split["sector"] if split else None,
                    split["specific"] if split else None,
                    name, margin, len(peer_ids), len(group_ids),
                    sentence(mine, parts, market, name),
                    grade, note, METHOD, METHOD,
                ),
            )
            written += 1
            conn.commit()

        print(f"  wrote {written} rows, {named_count} with one component far enough ahead to name")
        for why, n in sorted(undecided.items(), key=lambda kv: -kv[1]):
            print(f"  {n:>4} undecided: {why}")
        print(
            "  these are shares of shared movement. Nothing here says an event, a sector or "
            "a market caused a price to move."
        )
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
