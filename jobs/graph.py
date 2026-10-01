"""Carry a flagged catalyst a bounded distance across the edges that are already stored.

The gap this closes: the edges exist — industry membership, a product linked to the assets
that make it, an event linked to the assets it concerns — and nothing ever walked them. A
catalyst on one name appeared on the radar and the two assets that share its only supplier
link appeared nowhere, so the one thing a graph is for was not being done with it.

What travels is relevance, which means *a reason to look*. It is not impact, not an effect,
and not a prediction. An edge here states a relationship somebody recorded; it does not state
that a move on one end reaches the other, and this job is careful never to imply it did. The
whole output is a reading list ordered by how close something sits to something that has
started being written about.

Why it is bounded, in three ways
--------------------------------
  * **Hops.** Two, and no further. At three hops almost everything in a 160 asset database is
    reachable from almost everything else, and a list that includes everything has told
    nobody anything.
  * **Edge size.** An edge group larger than MAX_GROUP is skipped entirely. "Shares an
    industry with 70 other listings" is a fact about the industry, not a connection between
    two of its members, and treating it as one is how a hub edge floods a graph.
  * **Edge weight.** Every edge is divided by the size of the group it comes from, so being
    one of two assets linked to a product counts for more than being one of twenty in a
    sector. Without this the arithmetic would rank the biggest sector first every night.

Each row stores the path it travelled in words, so a reader can see the chain and reject it.
An unexplained score would be precisely the "unsupported chain" this project exists not to
produce.

Run: python jobs/graph.py
Reads: HumanSignal, Asset, Industry, ProductAssetLink, EventLink
Writes: GraphRelevance
"""

from __future__ import annotations

import sys
from collections import deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from nbt import db, one, rows, step  # noqa: E402

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except Exception:  # noqa: BLE001
    pass

GRAPH = "Walked over stored relationship rows, bounded at two hops"

# How far relevance travels, and what it loses per hop. The decay is well under a half, so a
# two hop neighbour can never outrank a one hop neighbour reached by a comparable edge: the
# ordering has to agree with the plain English claim that closer is more relevant.
MAX_HOPS = 2
DECAY = 0.4

# An edge group bigger than this says something about the group, not about its members.
MAX_GROUP = 25

# Relative weight per kind of edge, with the reason. A product link and an event link were
# each written down about a specific pair of things; industry membership was written down
# about a list.
KIND_WEIGHT = {"product": 1.0, "event": 0.8, "industry": 0.5}

# Rows kept per asset, strongest first. An asset reached from eleven origins has not been
# connected to the news eleven times; it is in a busy neighbourhood, and the strongest few
# paths are the ones worth reading.
MAX_PER_ASSET = 5

# Below this a path is not worth a row. Two hops over two weak edges produces a number that
# is arithmetically real and means nothing.
MIN_SCORE = 0.02


def edge_weight(kind: str, group_size: int) -> float | None:
    """Weight of one edge, or None when the group it comes from is too big to mean anything.

    Divided by the number of other members, so the weight answers "how specific is this
    relationship" rather than "how popular is this group".
    """
    others = group_size - 1
    if others < 1 or group_size > MAX_GROUP:
        return None
    return KIND_WEIGHT.get(kind, 0.0) / others


def hop_score(previous: float, kind: str, group_size: int) -> float | None:
    """The score after travelling one more edge, or None when the edge is not usable."""
    w = edge_weight(kind, group_size)
    if w is None:
        return None
    return previous * w * DECAY


def groups_to_edges(groups: list[tuple[str, str, list[str]]]) -> dict[str, list[dict]]:
    """Turn (kind, label, members) groups into an adjacency map.

    Groups rather than pairs is the natural shape of the stored data: an industry row has
    members, a product link row has a product with members. Expanding them to pairs here
    keeps the size of the group — which is what the weight needs — attached to every edge it
    produced.
    """
    adj: dict[str, list[dict]] = {}
    for kind, label, members in groups:
        unique = sorted(set(members))
        if len(unique) < 2 or len(unique) > MAX_GROUP:
            continue
        for a in unique:
            for b in unique:
                if a == b:
                    continue
                adj.setdefault(a, []).append(
                    {"to": b, "kind": kind, "label": label, "size": len(unique)}
                )
    return adj


EDGE_WORDS = {
    "industry": "shares the {label} industry with it, alongside {n} others",
    "product": "is linked to the product {label}, which has {n} other assets linked to it",
    "event": "is linked to the dated item {label}, which concerns {n} others",
}


def walk(adj: dict[str, list[dict]], start: str, start_names: str) -> dict[str, dict]:
    """Breadth first from one origin, bounded, keeping the best path to each asset reached.

    Breadth first and not depth first because the bound is on hops: the first time a node is
    reached is by the fewest edges, and taking the best score at that depth avoids ranking a
    long chain above a short one on the strength of two generous weights.
    """
    best: dict[str, dict] = {}
    queue: deque[tuple[str, int, float, str]] = deque([(start, 0, 1.0, start_names)])
    seen = {start}

    while queue:
        node, hops, score, path = queue.popleft()
        if hops >= MAX_HOPS:
            continue
        for edge in adj.get(node, []):
            nxt = edge["to"]
            if nxt == start:
                continue
            onward = hop_score(score, edge["kind"], edge["size"])
            if onward is None or onward < MIN_SCORE:
                continue
            step_words = EDGE_WORDS[edge["kind"]].format(label=edge["label"], n=edge["size"] - 1)
            full = f"{path}; {step_words}"
            held = best.get(nxt)
            if not held or onward > held["score"]:
                best[nxt] = {
                    "score": onward,
                    "hops": hops + 1,
                    "path": full,
                    "kind": edge["kind"],
                }
            if nxt not in seen:
                seen.add(nxt)
                queue.append((nxt, hops + 1, onward, full))
    return best


def main() -> None:
    conn = db()
    cur = conn.cursor()
    try:
        step("walk flagged catalysts across stored relationships, two hops at most")

        assets = {
            r["id"]: r
            for r in rows(
                cur,
                """
                SELECT a.id, a.symbol, a.name, a."industryId", i.name AS industry
                FROM "Asset" a JOIN "Industry" i ON i.id = a."industryId"
                """,
            )
        }

        groups: list[tuple[str, str, list[str]]] = []
        by_industry: dict[str, list[str]] = {}
        for a in assets.values():
            by_industry.setdefault(a["industryId"], []).append(a["id"])
        for industry_id, members in by_industry.items():
            label = next(assets[m]["industry"] for m in members)
            groups.append(("industry", label, members))

        product_members: dict[str, list[str]] = {}
        product_name: dict[str, str] = {}
        for r in rows(
            cur,
            """
            SELECT l."productId", l."assetId", p.name
            FROM "ProductAssetLink" l JOIN "Product" p ON p.id = l."productId"
            """,
        ):
            product_members.setdefault(r["productId"], []).append(r["assetId"])
            product_name[r["productId"]] = r["name"]
        for pid, members in product_members.items():
            groups.append(("product", product_name[pid], members))

        event_members: dict[str, list[str]] = {}
        event_name: dict[str, str] = {}
        for r in rows(
            cur,
            """
            SELECT l."eventId", l."assetId", e.name
            FROM "EventLink" l JOIN "Event" e ON e.id = l."eventId"
            WHERE l."assetId" IS NOT NULL
            """,
        ):
            event_members.setdefault(r["eventId"], []).append(r["assetId"])
            event_name[r["eventId"]] = r["name"]
        for eid, members in event_members.items():
            groups.append(("event", event_name[eid], members))

        adj = groups_to_edges(groups)
        usable = sum(1 for _, _, m in groups if 2 <= len(set(m)) <= MAX_GROUP)
        print(
            f"  {len(groups)} stored relationship groups, {usable} small enough to carry an "
            f"edge, {sum(len(v) for v in adj.values())} directed edges"
        )

        latest = one(cur, 'SELECT max("periodEnd") AS d FROM "HumanSignal"')
        if not latest or not latest["d"]:
            print("  no news reading is stored, so there is no catalyst to walk from")
            return
        period = latest["d"]

        flagged = rows(
            cur,
            """
            SELECT h."assetId", h."productId", h."spikeRatio", a.symbol, a.name AS asset_name,
                   p.name AS product_name, p.id AS pid
            FROM "HumanSignal" h
            LEFT JOIN "Asset" a ON a.id = h."assetId"
            LEFT JOIN "Product" p ON p.id = h."productId"
            WHERE h."periodEnd" = %s AND h.catalyst = true
            ORDER BY h."spikeRatio" DESC NULLS LAST
            """,
            (period,),
        )
        print(f"  {len(flagged)} catalysts flagged on the {period} reading")

        # Origin -> {asset: best path}. A product origin has no node of its own in the asset
        # graph, so its entry points are the assets linked to it, entered at one hop.
        reached: dict[str, dict] = {}
        for f in flagged:
            if f["assetId"]:
                if f["assetId"] not in assets:
                    continue
                origin_kind, origin_id = "asset", f["assetId"]
                opening = f"{f['symbol']} has a catalyst flagged on the {period} reading"
                found = walk(adj, f["assetId"], opening)
            elif f["pid"]:
                origin_kind, origin_id = "product", f["pid"]
                opening = (
                    f"the product {f['product_name']} has a catalyst flagged on the "
                    f"{period} reading"
                )
                found = {}
                entries = set(product_members.get(f["pid"], []))
                # The product is the origin, so every asset linked to it is one hop away and
                # the weight is shared between them: a product with one linked asset points
                # at that asset, a product with twelve points at a list.
                w = KIND_WEIGHT["product"] / len(entries) if entries else None
                if w is None or len(entries) > MAX_GROUP:
                    continue
                for entry in entries:
                    if entry not in assets:
                        continue
                    base = {
                        "score": w,
                        "hops": 1,
                        "path": f"{opening}; {assets[entry]['symbol']} is one of the assets "
                        "linked to it",
                        "kind": "product",
                    }
                    held = found.get(entry)
                    if not held or base["score"] > held["score"]:
                        found[entry] = base
                    for node, hit in walk(adj, entry, base["path"]).items():
                        scaled = {**hit, "score": hit["score"] * w, "hops": hit["hops"] + 1}
                        if scaled["hops"] > MAX_HOPS or scaled["score"] < MIN_SCORE:
                            continue
                        held = found.get(node)
                        if not held or scaled["score"] > held["score"]:
                            found[node] = scaled
            else:
                continue

            for asset_id, hit in found.items():
                if asset_id not in assets:
                    continue
                # An asset that already carries its own catalyst is on the radar by itself.
                # Listing it here as well would double count one piece of news.
                if any(g["assetId"] == asset_id for g in flagged):
                    continue
                key = f"{asset_id}|{origin_kind}|{origin_id}"
                if key not in reached or hit["score"] > reached[key]["hit"]["score"]:
                    reached[key] = {
                        "assetId": asset_id,
                        "originKind": origin_kind,
                        "originId": origin_id,
                        "hit": hit,
                    }

        # Keep only the strongest few paths per asset, so a crowded neighbourhood produces a
        # short readable list rather than every chain that happens to exist.
        per_asset: dict[str, list[dict]] = {}
        for item in reached.values():
            per_asset.setdefault(item["assetId"], []).append(item)
        kept = []
        for asset_id, items in per_asset.items():
            items.sort(key=lambda i: -i["hit"]["score"])
            kept.extend(items[:MAX_PER_ASSET])

        cur.execute('DELETE FROM "GraphRelevance" WHERE "periodEnd" = %s', (period,))
        for item in kept:
            hit = item["hit"]
            cur.execute(
                """
                INSERT INTO "GraphRelevance" ("assetId", "periodEnd", "originKind", "originId",
                    score, hops, "edgeKind", path, note, source, "computedAt")
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now())
                ON CONFLICT ("assetId", "periodEnd", "originKind", "originId") DO UPDATE SET
                    score = EXCLUDED.score, hops = EXCLUDED.hops,
                    "edgeKind" = EXCLUDED."edgeKind", path = EXCLUDED.path,
                    note = EXCLUDED.note, "computedAt" = now()
                """,
                (
                    item["assetId"], period, item["originKind"], item["originId"],
                    hit["score"], hit["hops"], hit["kind"], hit["path"],
                    "An edge is a relationship somebody recorded. Relevance travelling along "
                    "one is a reason to look, never evidence that a move on one end reached "
                    "the other",
                    GRAPH,
                ),
            )
        conn.commit()

        print(f"  {len(per_asset)} assets reached, {len(kept)} paths stored")
        for hops in (1, 2):
            n = sum(1 for k in kept if k["hit"]["hops"] == hops)
            print(f"  {n:>4} at {hops} hop{'s' if hops > 1 else ''}")
        if not kept:
            print(
                "  nothing was reached. Either no catalyst is flagged, or every edge group "
                f"around the flagged names has more than {MAX_GROUP} members."
            )
        print(
            "  relevance is a reading order. It is not impact and it does not say a move "
            "travelled along an edge."
        )
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
