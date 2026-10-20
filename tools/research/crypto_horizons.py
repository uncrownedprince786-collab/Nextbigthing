"""The forecast durations the site offers, defined once for the trainer and the serving path.

A reader picks **how long they are asking about**, not a trading style, and that distinction is the
reason this table exists in its own module. "Scalp / Swing / Position" named a *style*, which is a
statement about how someone trades; the question a direction answers is "which way over the next
N minutes", which is a statement about a window. The two were being conflated on the asset page,
where picking the short style read as asking for a SHORT call.

Each row says which corpus answers it and over how many bars, so a 5-minute forecast can never be
served from a daily model: the interval is part of the horizon's identity and is stamped on every
artifact and every recorded forecast.

  * The four intraday horizons read the 5-minute corpus. 5 minutes is one bar, 15 is three, an
    hour is twelve, four hours is forty-eight.
  * The three session horizons read the 4-hour corpus, where one UTC day is six bars. Crypto has
    no exchange session, so "a session" here is a calendar day in UTC -- the same definition
    `jobs/prices.py` uses for a crypto close, and the reason it is stated rather than assumed.

The feature window is always `WARMUP` bars of the same interval, so the session models look back
48 days and the intraday models look back 24 hours. That is deliberate: a question about the next
month should not be answered from the last twenty-four hours of ticks.
"""

from __future__ import annotations

#: key -> (interval, bars ahead, minutes ahead, label, the sentence under the label)
HORIZONS: dict[str, dict] = {
    "m5": {
        "interval": "5m", "bars": 1, "minutes": 5,
        "label": "Next 5 minutes",
        "lead": "one 5-minute bar from now",
    },
    "m15": {
        "interval": "5m", "bars": 3, "minutes": 15,
        "label": "Next 15 minutes",
        "lead": "three 5-minute bars from now",
    },
    "h1": {
        "interval": "5m", "bars": 12, "minutes": 60,
        "label": "Next hour",
        "lead": "twelve 5-minute bars from now",
    },
    "h4": {
        "interval": "5m", "bars": 48, "minutes": 240,
        "label": "Rest of today",
        "lead": "four hours from now",
    },
    "d1": {
        "interval": "4h", "bars": 6, "minutes": 1440,
        "label": "Next session",
        "lead": "one UTC day from now",
    },
    "d5": {
        "interval": "4h", "bars": 30, "minutes": 7200,
        "label": "This week",
        "lead": "five UTC days from now",
    },
    "d20": {
        "interval": "4h", "bars": 120, "minutes": 28800,
        "label": "Coming month",
        "lead": "twenty UTC days from now",
    },
}

ORDER = ["m5", "m15", "h1", "h4", "d1", "d5", "d20"]

INTERVALS = sorted({h["interval"] for h in HORIZONS.values()})


def horizons_for(interval: str) -> list[str]:
    return [k for k in ORDER if HORIZONS[k]["interval"] == interval]
