"""Which market a prediction belongs to, over which horizon, and what can honestly be judged.

    import shadow_markets as mk
    mk.market_of("crypto", "coinpaprika")        # "Crypto"
    mk.matures_after(date(2026, 9, 25), 20, "US") # 20 US sessions later
    mk.capability("Crypto", "scalp")             # verifiable by daily closes? no, and why

Why this file exists
---------------------
The first shadow path labelled a live row with `CASE WHEN source = 'psx' THEN 'PK' ELSE 'US' END`.
That is wrong for three of the five markets the site already carries: FX pairs, commodity futures
and crypto were all filed under "US". A prediction on the euro filed as a US equity cannot be
grouped, scored, or filtered correctly later, so the mistake would not show up as a bug -- it
would show up as an FX model with a US model's results.

Two more questions live here, both asked before anything is recorded:

* **Which market is this, really?** Answered from `Asset.assetType` first and `Asset.source`
  second, in the same vocabulary `jobs/audit.py` (`YAHOO_MARKETS`), `jobs/seed.py` (industry
  markets) and `jobs/pool.py` already use. Nothing here invents a code.

* **Over what can each market and timeframe be judged?** A scalp call is a claim about minutes;
  the database stores daily closes and cannot order what happened inside a session, so a scalp
  prediction is not something this project can ever score. Saying so once, in a table, is cheaper
  than discovering it after a hundred predictions have matured into nothing measurable.

Sessions, not calendar days
----------------------------
`maturesAfter` was a calendar approximation (`as_of + horizon * 7 // 5 + 4`). It ignored weekends
and holidays, so a 20-session US horizon matured on a date the market was closed, and a crypto
horizon skipped days the market was open. The session count is the real axis: `sessions_after`
counts only days the market trades, using the same rule `jobs/sessions.py` enforces in SQL (crypto
every day, everything else weekdays). It is still an approximation of exchange holidays -- no
holiday calendar is stored -- and it says so rather than pretending otherwise.
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "jobs"))

from sessions import trades_on  # noqa: E402  (the one session rule; reused, not re-stated)

#: The five markets the project carries. Order is the order the site groups them in.
MARKETS = ("US", "PK", "FX", "Commodity", "Crypto")

#: Which markets trade on weekends. Only crypto; it is the same split `jobs/sessions.py` makes.
WEEKEND_MARKETS = ("Crypto",)


def market_of(asset_type: str | None, source: str | None = None) -> str:
    """The market code for an asset, from its type and (for equities) its source.

    `assetType` decides wherever it is unambiguous. `stock` is the one value shared by two
    markets, and there the source decides: `psx` is the Pakistan Stock Exchange, `yahoo` is US.
    Anything unrecognised is filed under `US`, which is the project's default market and the one
    a name with no better answer belongs to -- never a silent `PK`.
    """
    t = (asset_type or "").strip().lower()
    s = (source or "").strip().lower()
    if t == "crypto" or "paprika" in s or "coingecko" in s:
        return "Crypto"
    if t == "forex":
        return "FX"
    if t == "commodity":
        return "Commodity"
    if t == "stock" and s == "psx":
        return "PK"
    if s == "psx":
        return "PK"
    return "US"


#: Per timeframe: how many sessions it is judged over, what it is judged on, and whether the
#: stored daily closes can judge it at all. `sessions` is 0 for a horizon shorter than a session.
TIMEFRAMES: dict[str, dict] = {
    "scalp": {
        "sessions": 0,
        "judgedOn": "the move within a session, over minutes",
        "dailyClosesCanJudge": False,
        "why": "a scalp is a claim about minutes; daily closes cannot order what happened inside "
               "one session, so a scalp prediction is not scoreable from anything the project "
               "stores",
    },
    "intraday": {
        "sessions": 1,
        "judgedOn": "the same session's close",
        "dailyClosesCanJudge": True,
        "why": "one session's close is stored, so a decision to the close can be scored from it",
    },
    "swing": {
        "sessions": 20,
        "judgedOn": "the 20-session forward return against the +/-2% label band",
        "dailyClosesCanJudge": True,
        "why": "the horizon the model was trained on; the label rule is fixed in tools/make_dataset",
    },
    "position": {
        "sessions": 60,
        "judgedOn": "the 60-session forward return",
        "dailyClosesCanJudge": True,
        "why": "judgeable from daily closes, but needs 60 sessions of history after the decision",
    },
}

#: The session count a strategy name maps to. Kept here so a caller never passes a bare integer
#: whose meaning is unstated.
STRATEGY_SESSIONS = {name: spec["sessions"] for name, spec in TIMEFRAMES.items()}


def trades_on_market(market: str | None, day: date) -> bool:
    """Whether `market` has a session on `day`: crypto every day, everything else weekdays."""
    return trades_on("crypto" if market == "Crypto" else "stock", day)


def sessions_after(as_of: date, n: int, market: str | None) -> date:
    """The date of the `n`-th session strictly after `as_of`, for this market.

    `n` sessions after the decision session, not `n` calendar days. For a weekday market that
    lands on a weekday; for crypto it may land on a weekend, because crypto trades then.
    """
    if n < 0:
        raise ValueError("a horizon cannot be negative")
    d, seen = as_of, 0
    while seen < n:
        d += timedelta(days=1)
        if trades_on_market(market, d):
            seen += 1
    return d


def matures_after(as_of: date, horizon_sessions: int, market: str | None) -> date:
    """The first session on which this market's `horizon_sessions` forward window has elapsed."""
    return sessions_after(as_of, horizon_sessions, market)


def sessions_between(start: date, end: date, market: str | None) -> int:
    """How many sessions this market has in `(start, end]`."""
    if end < start:
        return 0
    return sum(1 for i in range(1, (end - start).days + 1)
               if trades_on_market(market, start + timedelta(days=i)))


def capability(market: str, timeframe: str) -> dict:
    """What a `timeframe` prediction in `market` can be judged on, split into the three things that
    were being conflated: whether the inputs exist, whether a market-specific prediction exists, and
    whether the outcome can be judged.

    Separate axes because they fail independently, and collapsing them into one "supported" flag is
    how a market silently becomes "covered". A market can have the inputs and a judgeable outcome
    while still being predicted by a model that was never tuned for it -- that is a relabel, not a
    market-specific model, and the caller has to be able to see the difference.
    """
    if market not in MARKETS:
        raise ValueError(f"unknown market {market!r}; known: {', '.join(MARKETS)}")
    if timeframe not in TIMEFRAMES:
        raise ValueError(f"unknown timeframe {timeframe!r}; known: {', '.join(TIMEFRAMES)}")
    tf = TIMEFRAMES[timeframe]
    verifiable = bool(tf["dailyClosesCanJudge"])
    reason = tf["why"]
    if not verifiable:
        reason = (f"{market}: {reason}")
    else:
        reason = (f"{market}: {reason}. Sessions are counted on this market's own calendar "
                  f"(crypto every day; {market} on weekdays otherwise).")
    return {
        "market": market,
        "timeframe": timeframe,
        "horizonSessions": tf["sessions"],
        "judgedOn": tf["judgedOn"],
        # Input: the factor and price pipeline stores the same fields for every market, and the live
        # lane has rows for each (US, PK, FX, Commodity, Crypto all present). Whether they are fresh
        # is a separate, per-run fact that the readiness report measures and this does not assume.
        "input": {
            "available": True,
            "note": "the factor/price tables carry rows for this market; freshness is a per-run "
                    "fact reported elsewhere, not a property of the market",
        },
        # Prediction: the candidate is a single global model. It is applied to every market, but it
        # was not trained or calibrated per market, so a call here is not a market-specific model's
        # call. False is the honest value until a per-market profile actually exists.
        "prediction": {
            "marketSpecific": False,
            "note": "one global model is applied; the features are not tuned or validated per "
                    "market, so this is a relabel and not a market-specific model",
        },
        # Outcome: the axis this function was originally about -- can daily closes judge it at all.
        "outcome": {
            "verifiable": verifiable,
            "judgedOn": tf["judgedOn"],
            "reason": reason,
        },
        # Kept for existing callers; identical to outcome.verifiable.
        "verifiable": verifiable,
        "reason": reason,
    }


def market_capability_matrix() -> list[dict]:
    """Every (market, timeframe) pair with its verifiability. The shape a server can render."""
    return [capability(m, tf) for m in MARKETS for tf in TIMEFRAMES]


def market_profile(market: str) -> dict:
    """The few facts a caller needs to reason about a market's calendar and data."""
    if market not in MARKETS:
        raise ValueError(f"unknown market {market!r}; known: {', '.join(MARKETS)}")
    return {
        "market": market,
        "tradesOnWeekends": market in WEEKEND_MARKETS,
        "priceSource": {
            "US": "Yahoo Finance daily closes (stocks, ETFs)",
            "PK": "Pakistan Stock Exchange daily closes",
            "FX": "Yahoo Finance daily closes (currency pairs)",
            "Commodity": "Yahoo Finance daily closes (futures)",
            "Crypto": "CoinPaprika daily closes",
        }[market],
        "sessionRule": ("every calendar day" if market in WEEKEND_MARKETS
                        else "Monday to Friday; exchange holidays are not stored and are not "
                             "subtracted"),
    }
