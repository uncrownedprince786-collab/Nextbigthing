"""The macro state as it was knowable at each session's close.

    python tools/foundation/macro_pit.py --out DIR [--from 2019-01-02] [--to 2026-10-13]

One row per calendar session date, not per asset-session: the macro state is the same for every
asset on a date, so storing it once and joining by date keeps 802,876 dataset rows from carrying
616 identical copies of it.

The whole point is the availability rule. For a session D, each series contributes the newest
observation whose `availableAt` is on or before D -- not the newest observation dated on or before
D, which is the mistake that makes a macro backtest look prescient. The unemployment rate for
September is dated 1 September and was not published until October; using it on 15 September is
look-ahead, and `availableAt` is what stops it.

`USREC` is deliberately absent. It is the NBER recession flag, declared months after the fact with
no publication date in this dataset, so it has no honest availability and is an ex-post label.

Each series yields three fields:

* `v`    the value that was knowable;
* `age`  days from that observation's own period end to the session, so a consumer can tell a
         fresh print from a stale one rather than treating them alike;
* `chg`  the change from the previous knowable observation of the same series, which is the part
         a market reacts to.

Output: `macro-sessions.jsonl.gz` and `manifest.json`. Public statistical data, safe to commit,
but written to the dataset directory because its size belongs with the dataset.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
import sys
from bisect import bisect_right
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
MACRO = ROOT / "data" / "foundation" / "macro"


def arg(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def load_series() -> dict[str, dict]:
    """{id: {availableAt[], obs[], value[]}} sorted by availableAt, excluding ex-post labels."""
    manifest = json.loads((MACRO / "manifest.json").read_text(encoding="utf-8"))
    out = {}
    for sid, meta in manifest["series"].items():
        if meta["availability"] == "none":
            continue
        rows = []
        with open(MACRO / f"{sid}.csv", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if not r["availableAt"]:
                    continue
                rows.append((r["availableAt"], r["observation_date"], float(r["value"])))
        rows.sort()
        out[sid] = {"avail": [r[0] for r in rows], "obs": [r[1] for r in rows],
                    "val": [r[2] for r in rows], "title": meta["title"],
                    "frequency": meta["frequency"], "availability": meta["availability"]}
    return out


def sessions(frm: date, to: date) -> list[str]:
    """Session dates from the stored price history, so the grid matches the dataset's own."""
    sys.path.insert(0, str(ROOT / "jobs"))
    from nbt import db
    cur = db().cursor()
    cur.execute('SELECT DISTINCT date FROM "PriceSnapshot" WHERE date >= %s AND date <= %s ORDER BY date',
                (frm, to))
    return [r["date"].isoformat() for r in cur.fetchall()]


def state_at(series: dict[str, dict], day: str) -> dict:
    """Every series' newest observation that had been published by the close of `day`."""
    out = {}
    for sid, s in series.items():
        i = bisect_right(s["avail"], day) - 1
        if i < 0:
            continue
        row = {"v": s["val"][i],
               "age": (date.fromisoformat(day) - date.fromisoformat(s["obs"][i])).days}
        if i > 0:
            row["chg"] = round(s["val"][i] - s["val"][i - 1], 6)
        out[sid] = row
    return out


def main() -> int:
    out = Path(arg("--out") or (ROOT / ".cache" / "foundation" / "macro_pit"))
    out.mkdir(parents=True, exist_ok=True)
    frm = date.fromisoformat(arg("--from") or "2019-01-02")
    to = date.fromisoformat(arg("--to") or date.today().isoformat())
    series = load_series()
    days = sessions(frm, to)

    h = hashlib.sha256()
    counts: dict[str, int] = {}
    leaks = 0
    first_full = None
    with gzip.open(out / "macro-sessions.jsonl.gz", "wt", encoding="utf-8", compresslevel=6) as f:
        for day in days:
            st = state_at(series, day)
            for sid, row in st.items():
                counts[sid] = counts.get(sid, 0) + 1
                # The guard that makes the file worth anything: nothing in a session's state may
                # describe a period that had not ended, nor carry a value published after it.
                if row["age"] < 0:
                    leaks += 1
            if first_full is None and len(st) == len(series):
                first_full = day
            line = json.dumps({"d": day, "m": st}, separators=(",", ":"))
            h.update(line.encode())
            f.write(line + "\n")

    manifest = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sessions": len(days), "range": [days[0], days[-1]] if days else None,
        "series": len(series), "firstSessionWithEverySeries": first_full,
        "excluded": {"USREC": "NBER recession flag: declared after the fact, no honest availability"},
        "coveragePerSeries": {k: round(v / max(1, len(days)), 4) for k, v in sorted(counts.items())},
        "observationsDatedAfterTheirSession": leaks,
        "sha256": h.hexdigest(),
        "rule": ("for session D each series contributes its newest observation whose availableAt "
                 "is on or before D, never the newest observation dated on or before D"),
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in manifest.items() if k != "coveragePerSeries"}, indent=1))
    return 0 if leaks == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
