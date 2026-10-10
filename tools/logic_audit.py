"""Check the arithmetic of every call: direction, stop side, zero risk, ATR stops, reward:risk, sub-cent.

    DATABASE_URL=<primary> python tools/logic_audit.py            database rows and the live pages
    SITE_URL=http://localhost:3000 python tools/logic_audit.py    against another deployment

Two halves, because the numbers live in two places:

  * The database: `DecisionLog` holds, per asset per day, the verdict, the entry band, the stop, the
    stored reward:risk and the close the call was read from -- written by `tools/decide.mjs` through
    the same `decideCall` the pages use. Checked for the newest logged day, every row.
  * The live pages: the take-profit level is computed when a page renders (`targetForCall`) and is
    never stored, so the target checks and the reward:risk recomputation read the market pages a
    reader sees, every row, with the full figures from each price's tooltip.

Read only. The session is opened read-only, so even a mistaken statement here could not write.

How the entry zone is built, because the stop checks depend on it: `AssetSetup` stores two levels,
the entry level and the invalidation level, and the zone is the range they span (lib/decisionInput.ts).
Until 2026-10-11 the stop sat on the zone's far edge; since then (brain.md rule 91, lib/resolve.ts
`bufferStop`) it sits at least 1.0 x atr14 beyond the zone, so a stop on the edge is a fault. The lists
publish only calls that pass the quality gate (lib/quality.ts): a measured take profit, reward:risk of
at least 1.2 and one confirmation, so a published row without them is a fault too. Withheld calls are
named in a folded list on each page and counted here.
Reward:risk is measured from the entry level the call trades from: the top of the zone for a LONG,
the bottom for a SHORT.
"""

from __future__ import annotations

import html as _html
import math
import os
import re
import sys
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = (os.environ.get("SITE_URL") or "https://nextbigthing-nu.vercel.app").rstrip("/")
PAGES = ("/", "/stocks", "/crypto", "/psx", "/forex", "/commodities")
ATR_MULTIPLE = 2.0  # lib/resolve.ts: a resolved call's own stop is 2 x atr14 from the close
BUFFER_ATR = 1.0  # lib/resolve.ts STOP_BUFFER_ATR: no stop nearer the zone than this many atr14
MIN_REWARD_RISK = 1.2  # lib/quality.ts: the least reward:risk a published call carries
MIN_CONFIRMATIONS = 1  # lib/quality.ts
EXAMPLES = 8


def database_url() -> str:
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        try:
            from dotenv import dotenv_values

            url = (dotenv_values(ROOT / ".env").get("DATABASE_URL") or "").strip()
        except Exception:  # noqa: BLE001
            url = ""
    if not url:
        raise SystemExit("DATABASE_URL is not set")
    return url


def provider(url: str) -> str:
    from urllib.parse import urlsplit

    host = (urlsplit(url).hostname or "").lower()
    return "Neon" if host.endswith(".neon.tech") else "Supabase" if "supabase" in host else "another host"


def fin(x) -> bool:
    return x is not None and isinstance(x, (int, float)) and math.isfinite(x)


# --- the database half ----------------------------------------------------------------------------


def audit_database(url: str) -> dict:
    import psycopg
    from psycopg.rows import dict_row

    with psycopg.connect(url, row_factory=dict_row, connect_timeout=20) as conn:
        conn.read_only = True
        cur = conn.cursor()
        cur.execute('SELECT max("periodEnd") AS d FROM "DecisionLog"')
        day = cur.fetchone()["d"]
        # The active pool only, as the pages and the nightly job are (jobs/pool.py): a name taken out of
        # the pool keeps the rows it was logged with earlier in the day, which no page shows and no run
        # rewrites, so they would be audited against rules they were never written under.
        select = """SELECT a.id AS "assetId", a.symbol, i.market, d.action, d.gate, d.confidence,
                      d."entryLow", d."entryHigh", d.invalidation, d."rewardRisk", d."baseClose"
                 FROM "DecisionLog" d JOIN "Asset" a ON a.id = d."assetId"
                 JOIN "Industry" i ON i.id = a."industryId"
                WHERE d."periodEnd" = %s"""
        try:
            cur.execute(select + " AND a.active", (day,))
        except Exception:  # noqa: BLE001 - no pool column: every name is in the pool
            conn.rollback()
            conn.read_only = True
            cur = conn.cursor()
            cur.execute(select, (day,))
        logged = cur.fetchall()
        try:
            cur.execute('SELECT count(*) AS n FROM "Asset" WHERE active')
            active = cur.fetchone()["n"]
        except Exception:  # noqa: BLE001 - the column is late; a database without it has no pool gate
            conn.rollback()
            conn.read_only = True
            cur = conn.cursor()
            cur.execute('SELECT count(*) AS n FROM "Asset"')
            active = cur.fetchone()["n"]
        try:
            cur.execute(
                'SELECT DISTINCT ON ("assetId") "assetId", atr14 FROM "AssetFactor" '
                'WHERE atr14 IS NOT NULL ORDER BY "assetId", "periodEnd" DESC'
            )
            atr = {r["assetId"]: r["atr14"] for r in cur.fetchall()}
        except Exception:  # noqa: BLE001
            conn.rollback()
            conn.read_only = True
            cur = conn.cursor()
            atr = {}
        cur.execute(
            """SELECT DISTINCT ON ("assetId", horizon) "assetId", horizon, "invalidateLevel", "entryLevel"
                 FROM "AssetSetup" WHERE horizon IN ('swing', 'longer')
                ORDER BY "assetId", horizon, "periodEnd" DESC"""
        )
        setup_stops: dict[str, set] = {}
        for r in cur.fetchall():
            for v in (r["invalidateLevel"], r["entryLevel"]):
                if fin(v):
                    setup_stops.setdefault(r["assetId"], set()).add(v)
        cur.execute(
            """SELECT count(*) FILTER (WHERE t.low <= 0 OR t.high <= 0) AS nonpositive,
                      count(*) FILTER (WHERE t.low > t.high) AS reversed,
                      count(*) FILTER (WHERE t."rewardRisk" IS NOT NULL AND (t."rewardRisk" <= 0
                                        OR t."rewardRisk" = 'Infinity'::float8 OR t."rewardRisk" = 'NaN'::float8)) AS bad_rr,
                      count(*) AS n
                 FROM "SetupTarget" t JOIN "AssetSetup" s ON s.id = t."setupId"
                WHERE s."periodEnd" >= %s::date - 14""",
            (day,),
        )
        targets = cur.fetchone()

    out = {
        "day": day, "active": active, "logged": len(logged), "actions": Counter(r["action"] for r in logged),
        "dir_wrong": [], "dir_inside": [], "dir_edge": 0, "dir_beyond": 0, "no_band": [], "no_stop": [],
        "zero_risk": [], "stop_at_close": [], "rr_bad": [], "rr_present": 0,
        "forced": 0, "forced_atr": 0, "forced_setup": 0, "forced_buffer": 0, "forced_other": [], "forced_no_atr": 0,
        "buffer_short": [], "no_atr": 0,
        "subcent": 0, "subcent_bad": [], "subcent_min_rel_risk": None, "targets": targets,
    }
    for r in logged:
        act, lo, hi, stop, close, sym = r["action"], r["entryLow"], r["entryHigh"], r["invalidation"], r["baseClose"], r["symbol"]
        if act not in ("LONG", "SHORT"):
            continue
        if not (fin(lo) and fin(hi)) or lo > hi or lo <= 0:
            out["no_band"].append(f"{sym} {act} band {lo}..{hi}")
            continue
        if not fin(stop) or stop <= 0:
            out["no_stop"].append(f"{sym} {act} stop {stop}")
            continue
        long = act == "LONG"
        # Where the stop sits against the zone. LONG: beyond (< low), at the edge (== low), inside, wrong side.
        if long:
            where = "beyond" if stop < lo else "edge" if stop == lo else "inside" if stop < hi else "wrong"
        else:
            where = "beyond" if stop > hi else "edge" if stop == hi else "inside" if stop > lo else "wrong"
        if where == "wrong":
            out["dir_wrong"].append(f"{sym} {act} zone {lo}..{hi} stop {stop}")
        elif where == "inside":
            out["dir_inside"].append(f"{sym} {act} zone {lo}..{hi} stop {stop}")
        else:
            out["dir_" + where] += 1
        entry = hi if long else lo
        risk = abs(entry - stop)
        if risk == 0 or risk <= abs(entry) * 1e-12:
            out["zero_risk"].append(f"{sym} {act} entry {entry} stop {stop}")
        a14 = atr.get(r["assetId"])
        if fin(a14) and a14 > 0:
            beyond = (lo - stop) if long else (stop - hi)
            # 1e-4 relative: stops are rounded to eight significant digits (lib/resolve.ts).
            if beyond < BUFFER_ATR * a14 * (1 - 1e-4):
                out["buffer_short"].append(f"{sym} {act} zone {lo}..{hi} stop {stop}: {beyond / a14:.2f} x atr14 beyond the zone")
        else:
            out["no_atr"] += 1
        if fin(close) and stop == close:
            out["stop_at_close"].append(f"{sym} {act} close {close} stop {stop}")
        if r["rewardRisk"] is not None:
            out["rr_present"] += 1
            if not fin(r["rewardRisk"]) or r["rewardRisk"] <= 0:
                out["rr_bad"].append(f"{sym} {act} stored rewardRisk {r['rewardRisk']}")
        if str(r["gate"]).startswith("forced-"):
            out["forced"] += 1
            a = atr.get(r["assetId"])
            own = setup_stops.get(r["assetId"], set())
            if any(abs(stop - v) <= max(abs(v), 1e-300) * 1e-9 for v in own):
                out["forced_setup"] += 1
            elif fin(a) and a > 0 and fin(close):
                ratio = abs(close - stop) / a
                if abs(ratio - ATR_MULTIPLE) <= 0.01:
                    out["forced_atr"] += 1
                elif abs(ratio - BUFFER_ATR) <= 0.01:
                    out["forced_buffer"] += 1
                else:
                    out["forced_other"].append(f"{sym} {act} {r['gate']} |close-stop|/atr14 = {ratio:.3f}")
            else:
                out["forced_no_atr"] += 1
                out["forced_other"].append(f"{sym} {act} {r['gate']} stop {stop}: no atr14 and not the setup's own")
        if fin(close) and close < 1:
            out["subcent"] += 1
            rel = risk / close if close else 0
            if lo <= 0 or stop <= 0 or rel <= 1e-6 or len({lo, hi, stop}) < 2:
                out["subcent_bad"].append(f"{sym} close {close} zone {lo}..{hi} stop {stop}")
            m = out["subcent_min_rel_risk"]
            out["subcent_min_rel_risk"] = rel if m is None else min(m, rel)
    return out


# --- the live-page half ---------------------------------------------------------------------------

LABEL = re.compile(r'<span class="[^"]*lg:sr-only">([^<]+)</span>')
TITLE = re.compile(r'title="([^"]*)"')
# A number must start with a digit: the rupee mark is "Rs.", and a pattern allowing a leading point
# read "Rs.1,234.56" as ".1234" and ".56" -- the first run of this script reported 65 PSX "violations"
# that were its own parsing.
NUMBER = re.compile(r"-?\d[\d,]*(?:\.\d+)?")


def price_of(title: str) -> float | None:
    """The first number in a price tooltip ("$1,234.56", "Rs.1,234.56", "$0.000004043", "$-5.00")."""
    m = NUMBER.search(_html.unescape(title))
    try:
        return float(m.group(0).replace(",", "")) if m else None
    except ValueError:
        return None


def half_unit(title: str) -> float:
    """Half of the last printed digit's place: how far the true value can sit from the printed one."""
    m = NUMBER.search(_html.unescape(title))
    if not m or "." not in m.group(0):
        return 0.5
    return 0.5 * 10 ** -len(m.group(0).split(".")[1])


def prices_in(cell: str) -> list[float]:
    return [v for v, _ in prices_with_rounding(cell)]


def prices_with_rounding(cell: str) -> list[tuple[float, float]]:
    out = []
    for t in TITLE.findall(cell):
        t = _html.unescape(t)
        # Only a price tooltip ("$1,234.56", "Rs.102.50", "USD 1.1201"): the take-profit cell's own title
        # is a sentence ("Measured from ...", "Projected at 2 x the risk ..."), and its "2" is not a price.
        if not re.match(r"^\s*(?:\$|Rs\.|[A-Z]{3} )?-?\d", t):
            continue
        v = price_of(t)
        if v is not None:
            out.append((v, half_unit(t)))
    return out


def parse_rows(page_html: str) -> list[dict]:
    rows = []
    for li in re.findall(r"<li(?:\s[^>]*)?>(.*?)</li>", page_html, re.S):
        sym = re.search(r'href="/asset/([^"#?]+)"', li)
        if not sym or ">Action</span>" not in li:
            continue
        parts = LABEL.split(li)
        cells = {parts[i]: parts[i + 1] for i in range(1, len(parts) - 1, 2)}
        action_html = cells.get("Action", "")
        action = "LONG" if ">LONG<" in action_html else "SHORT" if ">SHORT<" in action_html else "WAIT"
        rr = re.search(r"(-?\d+\.\d):1", re.sub(r"<[^>]+>", "", cells.get("Reward:risk", "")))
        rows.append({
            "symbol": _html.unescape(sym.group(1)),
            "action": action,
            "entry": prices_in(cells.get("Entry zone", "")),
            "stop": prices_in(cells.get("Stop loss", "")),
            "target": prices_in(cells.get("Take profit", "")),
            "rr": float(rr.group(1)) if rr else None,
            "confirmations": (lambda m: int(m.group(1)) if m else None)(re.search(r"(\d+) of 5", re.sub(r"<[^>]+>", "", cells.get("Confirmations", "")))),
            # The rounding of every printed level, so a reward:risk can be checked against what the
            # printed figures allow rather than against a guessed tolerance.
            "half": {v: h for cell in ("Entry zone", "Stop loss", "Take profit") for v, h in prices_with_rounding(cells.get(cell, ""))},
        })
    return rows


def audit_pages() -> dict:
    seen: dict[str, dict] = {}
    out = {"rows": 0, "names": 0, "actions": Counter(), "inconsistent": [], "t_wrong": [], "t_none": 0,
           "s_wrong": [], "s_inside": [], "s_edge": 0, "s_beyond": 0, "zero_risk": [], "rr_bad": [],
           "rr_mismatch": [], "rr_checked": 0, "subcent_rows": 0, "subcent_bad": [], "t_missing": [],
           "rr_low": [], "unconfirmed": [], "withheld": 0}
    for path in PAGES:
        req = urllib.request.Request(SITE + path, headers={"User-Agent": "nbt-logic-audit"})
        with urllib.request.urlopen(req, timeout=60) as r:
            page = r.read().decode("utf-8", "replace")
        if path != "/":
            m = re.search(r"Not published: (?:<!-- -->)?(\d+)", page)
            out["withheld"] += int(m.group(1)) if m else 0
        for row in parse_rows(page):
            out["rows"] += 1
            key = row["symbol"]
            if key in seen:
                a, b = seen[key], row
                if (a["action"], a["entry"], a["stop"], a["target"], a["rr"]) != (b["action"], b["entry"], b["stop"], b["target"], b["rr"]):
                    out["inconsistent"].append(f"{key} differs between pages")
                continue
            seen[key] = row
    out["names"] = len(seen)
    for sym, r in seen.items():
        out["actions"][r["action"]] += 1
        if r["action"] not in ("LONG", "SHORT") or not r["entry"] or not r["stop"]:
            continue
        long = r["action"] == "LONG"
        lo, hi = min(r["entry"]), max(r["entry"])
        stop = r["stop"][0]
        if long:
            where = "beyond" if stop < lo else "edge" if stop == lo else "inside" if stop < hi else "wrong"
        else:
            where = "beyond" if stop > hi else "edge" if stop == hi else "inside" if stop > lo else "wrong"
        if where == "wrong":
            out["s_wrong"].append(f"{sym} {r['action']} zone {lo}..{hi} stop {stop}")
        elif where == "inside":
            out["s_inside"].append(f"{sym} {r['action']} zone {lo}..{hi} stop {stop}")
        else:
            out["s_" + where] += 1
        entry = hi if long else lo
        risk = abs(entry - stop)
        if risk == 0:
            out["zero_risk"].append(f"{sym} {r['action']} entry {entry} stop {stop}")
        if entry < 1:
            out["subcent_rows"] += 1
            if min([lo, hi, stop] + r["target"]) <= 0 or risk == 0:
                out["subcent_bad"].append(f"{sym} zone {lo}..{hi} stop {stop} target {r['target']}")
        if not r["target"]:
            out["t_none"] += 1
            if r["rr"] is not None:
                out["rr_bad"].append(f"{sym} prints R:R {r['rr']} with no target")
            out["t_missing"].append(f"{sym} {r['action']} zone {lo}..{hi} stop {stop}: published with no take profit")
            continue
        if r["rr"] is not None and r["rr"] < MIN_REWARD_RISK:
            out["rr_low"].append(f"{sym} {r['action']} published at {r['rr']}:1")
        if r["confirmations"] is not None and r["confirmations"] < MIN_CONFIRMATIONS:
            out["unconfirmed"].append(f"{sym} {r['action']} published with {r['confirmations']} of 5")
        tlo, thi = min(r["target"]), max(r["target"])
        if (long and not tlo > hi) or (not long and not thi < lo):
            out["t_wrong"].append(f"{sym} {r['action']} zone {lo}..{hi} target {tlo}..{thi}")
        if r["rr"] is None:
            continue
        if r["rr"] <= 0:
            out["rr_bad"].append(f"{sym} prints R:R {r['rr']}:1")
        near = tlo if long else thi
        if risk > 0:
            out["rr_checked"] += 1
            calc = abs(near - entry) / risk
            # Every printed figure is rounded: each level by half its last digit's place, the ratio by
            # 0.05. The true ratio lies in the interval the printed levels allow; a printed ratio outside
            # it (widened by its own 0.05) cannot have come from these levels.
            h = r["half"]
            e_r, e_k = h.get(near, 0) + h.get(entry, 0), h.get(entry, 0) + h.get(stop, 0)
            reward = abs(near - entry)
            low = max(reward - e_r, 0) / (risk + e_k)
            high = (reward + e_r) / (risk - e_k) if risk > e_k else math.inf
            if not (low - 0.05 - 1e-9 <= r["rr"] <= high + 0.05 + 1e-9):
                out["rr_mismatch"].append(
                    f"{sym} {r['action']} prints {r['rr']}:1, levels allow {low:.2f} to {high:.2f}:1 (entry {entry}, stop {stop}, target near {near})"
                )
    return out


def show(title: str, items: list[str]) -> None:
    if items:
        print(f"  {title}: {len(items)}")
        for line in items[:EXAMPLES]:
            print(f"    - {line}")
        if len(items) > EXAMPLES:
            print(f"    ... and {len(items) - EXAMPLES} more")


def main() -> int:
    pages_only = "--pages-only" in sys.argv
    url = None if pages_only else database_url()
    print(f"database: {'skipped (--pages-only)' if pages_only else provider(url) + ' (read-only session)'}   site: {SITE}")
    db = None if pages_only else audit_database(url)
    pg = audit_pages()
    if db is None:
        db = {"day": "-", "active": "-", "logged": 0, "actions": Counter(), "dir_wrong": [], "dir_inside": [],
              "dir_edge": 0, "dir_beyond": 0, "no_band": [], "no_stop": [], "zero_risk": [], "stop_at_close": [],
              "rr_bad": [], "rr_present": 0, "forced": 0, "forced_atr": 0, "forced_setup": 0, "forced_other": [],
              "forced_no_atr": 0, "forced_buffer": 0, "buffer_short": [], "no_atr": 0, "subcent": 0, "subcent_bad": [], "subcent_min_rel_risk": None,
              "targets": {"n": 0, "nonpositive": 0, "reversed": 0, "bad_rr": 0}}

    print(f"\n== database: DecisionLog for {db['day']} (newest logged day)")
    print(f"  active assets {db['active']}, calls logged {db['logged']}, verdicts {dict(db['actions'])}")
    print(f"  stop vs zone: beyond the zone {db['dir_beyond']}, ON THE ZONE'S EDGE {db['dir_edge']}, "
          f"inside the zone {len(db['dir_inside'])}, wrong side {len(db['dir_wrong'])}")
    print(f"  buffer: {len(db['buffer_short'])} stops nearer the zone than {BUFFER_ATR} x atr14, {db['no_atr']} calls with no atr14 to check")
    show("STOP NEARER THE ZONE THAN THE BUFFER", db["buffer_short"])
    show("WRONG SIDE", db["dir_wrong"]); show("STOP INSIDE THE ZONE", db["dir_inside"])
    show("no entry band", db["no_band"]); show("no stop", db["no_stop"])
    show("ZERO RISK (entry == stop)", db["zero_risk"]); show("stop equal to the close", db["stop_at_close"])
    print(f"  stored reward:risk present {db['rr_present']}, invalid {len(db['rr_bad'])}")
    show("INVALID STORED R:R", db["rr_bad"])
    print(f"  resolved (forced) calls {db['forced']}: stop = 2.00 x atr14 from the close {db['forced_atr']}, "
          f"= 1.50 x atr14 beyond the zone {db['forced_buffer']}, = the setup's own level {db['forced_setup']}, other {len(db['forced_other'])}")
    show("FORCED STOP NOT EXPLAINED", db["forced_other"])
    m = db["subcent_min_rel_risk"]
    print(f"  under $1: {db['subcent']} calls, smallest risk {m * 100:.2f}% of the close" if m is not None else f"  under $1: {db['subcent']} calls")
    show("SUB-DOLLAR COLLAPSE", db["subcent_bad"])
    t = db["targets"]
    print(f"  stored targets (last 14 days) {t['n']}: non-positive {t['nonpositive']}, low > high {t['reversed']}, invalid R:R {t['bad_rr']}")

    print(f"\n== live pages: {pg['rows']} rows, {pg['names']} names, verdicts {dict(pg['actions'])}")
    print(f"  stop vs zone: beyond {pg['s_beyond']}, ON THE EDGE {pg['s_edge']}, inside {len(pg['s_inside'])}, wrong side {len(pg['s_wrong'])}")
    show("WRONG SIDE", pg["s_wrong"]); show("STOP INSIDE THE ZONE", pg["s_inside"])
    show("ZERO RISK", pg["zero_risk"])
    print(f"  published rows {pg['names']}, withheld by the quality gate {pg['withheld']} (named, folded, on the market pages)")
    print(f"  targets: shown {pg['names'] - pg['t_none'] - pg['actions'].get('WAIT', 0)}, none {pg['t_none']}, on the wrong side {len(pg['t_wrong'])}")
    show("PUBLISHED WITHOUT A TAKE PROFIT", pg["t_missing"])
    show(f"PUBLISHED UNDER {MIN_REWARD_RISK}:1", pg["rr_low"])
    show("PUBLISHED WITHOUT A CONFIRMATION", pg["unconfirmed"])
    show("TARGET ON THE WRONG SIDE", pg["t_wrong"])
    print(f"  reward:risk recomputed {pg['rr_checked']}: mismatched {len(pg['rr_mismatch'])}, invalid {len(pg['rr_bad'])}")
    show("R:R MISMATCH", pg["rr_mismatch"]); show("INVALID R:R", pg["rr_bad"])
    print(f"  under $1: {pg['subcent_rows']} rows, collapsed {len(pg['subcent_bad'])}")
    show("SUB-DOLLAR COLLAPSE", pg["subcent_bad"]); show("DIFFERENT ON TWO PAGES", pg["inconsistent"])

    faults = {
        "directional (wrong side or inside the zone)": len(db["dir_wrong"]) + len(db["dir_inside"]) + len(pg["s_wrong"]) + len(pg["s_inside"]) + len(pg["t_wrong"]),
        "entry == stop": len(db["zero_risk"]) + len(pg["zero_risk"]),
        "invalid or mismatched R:R": len(db["rr_bad"]) + len(pg["rr_bad"]) + len(pg["rr_mismatch"]) + t["bad_rr"],
        "sub-dollar collapse": len(db["subcent_bad"]) + len(pg["subcent_bad"]) + t["nonpositive"],
        "unexplained forced stop": len(db["forced_other"]),
        "missing band/stop on a call": len(db["no_band"]) + len(db["no_stop"]),
        "page disagreement": len(pg["inconsistent"]),
        "stop on the zone's edge (rule 91)": db["dir_edge"] + pg["s_edge"],
        "stop nearer the zone than 1.0 x atr14": len(db["buffer_short"]),
        "published call without a take profit": len(pg["t_missing"]),
        f"published call under {MIN_REWARD_RISK}:1": len(pg["rr_low"]),
        "published call without a confirmation": len(pg["unconfirmed"]),
    }
    print("\n== verdict")
    for k, v in faults.items():
        print(f"  {k:45s} {v}")
    ok = not any(faults.values())
    print("  PASSED MATHEMATICALLY" if ok else "  LOGIC CORRUPTED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
