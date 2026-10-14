"""The KSE-100 daily series from the exchange's own end-of-day endpoint.

    python tools/foundation/psx_index.py fetch [SYMBOL]      default KSE100
    python tools/foundation/psx_index.py verify

Why this works now and did not before
-------------------------------------
`https://dps.psx.com.pk/timeseries/eod/KSE100` was recorded twice as a 404 and once as a 403, and
both readings were true of the request that was sent. The endpoint needs **two** headers together:

  * `X-Req-Id`, the per-page token the site itself attaches to every one of its AJAX calls --
    `$.ajaxSetup({headers:{"X-Req-Id": window.__ps._k}})` in its own `static/script.js`; and
  * `X-Requested-With: XMLHttpRequest`, which jQuery adds to any same-origin request.

Sent alone, the first gives 404 and the second 403. Sent together, from a page that issued the
token, the endpoint answers 200. Nothing here solves a challenge, supplies a credential or evades
a control: the token is handed to every visitor in the page source and is used exactly as the
page uses it.

What the endpoint actually returns, and what it does not
--------------------------------------------------------
`{"status":1,"message":"","data":[[unixSeconds, close, volume, open], ...]}`, newest first.

**There is no high and no low.** Four fields arrive and four are stored; nothing is derived to
fill the other two, so this series cannot carry a true range, an ATR or a candle. The depth is
about five years, which is the endpoint's own limit and well short of the 2018-01-01 the frozen
target asks for -- so what this supplies is a partial history, and the manifest says so.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from http.cookiejar import CookieJar
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
RAW = ROOT / ".cache" / "acquire" / "psx_index"
OUT = ROOT / "data" / "foundation" / "psx_index"

BASE = "https://dps.psx.com.pk"
# Any company page issues a token; this one is simply a liquid name that is certain to exist.
TOKEN_PAGE = "/company/MARI"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/120.0 Safari/537.36")
# The frozen target's common cutoff for PSX instruments.
REQUIRED_FROM = "2018-01-01"


def opener():
    o = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))
    o.addheaders = [("User-Agent", UA), ("Accept-Language", "en-US,en;q=0.9")]
    return o


def fetch(symbol: str) -> dict:
    op = opener()
    with op.open(urllib.request.Request(BASE + TOKEN_PAGE,
                                        headers={"User-Agent": UA, "Accept": "text/html,*/*"}),
                 timeout=45) as r:
        page = r.read().decode("utf-8", "replace")
    m = re.search(r'window\.__ps\s*=\s*(\{.*?\})\s*;', page, re.S)
    if not m:
        return {"acquired": False, "reason": "the token page no longer carries window.__ps"}
    token = json.loads(m.group(1)).get("_k")
    if not token:
        return {"acquired": False, "reason": "window.__ps carries no _k token"}
    time.sleep(1.5)

    url = f"{BASE}/timeseries/eod/{symbol}"
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "X-Req-Id": token,                       # the page's own token
        "X-Requested-With": "XMLHttpRequest",    # what jQuery adds; both are needed
        "Referer": BASE + TOKEN_PAGE})
    try:
        with op.open(req, timeout=60) as r:
            body, status, ctype = r.read(), r.status, r.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e:
        return {"acquired": False, "httpStatus": e.code, "url": url,
                "reason": f"the endpoint answered {e.code}"}
    RAW.mkdir(parents=True, exist_ok=True)
    (RAW / f"{symbol}_eod.json").write_bytes(body)
    try:
        doc = json.loads(body)
    except ValueError:
        return {"acquired": False, "httpStatus": status, "url": url,
                "contentType": ctype, "bytes": len(body),
                "reason": "the endpoint answered with something that is not JSON"}
    return {"acquired": doc.get("status") == 1 and bool(doc.get("data")),
            "httpStatus": status, "url": url, "contentType": ctype, "bytes": len(body),
            "apiStatus": doc.get("status"), "apiMessage": doc.get("message"),
            "rows": len(doc.get("data") or []), "tokenUsed": True}


def validate(symbol: str) -> dict:
    raw = (RAW / f"{symbol}_eod.json").read_bytes()
    doc = json.loads(raw)
    rows = doc.get("data") or []
    seen: dict[str, list] = {}
    bad_shape = nulls = nonpos = 0
    for r in rows:
        if not isinstance(r, list) or len(r) != 4:
            bad_shape += 1
            continue
        ts, close, vol, opn = r
        if any(v is None for v in r):
            nulls += 1
            continue
        if close <= 0 or opn <= 0:
            nonpos += 1
            continue
        if vol < 0:
            nonpos += 1
            continue
        d = datetime.fromtimestamp(int(ts), timezone.utc).date().isoformat()
        seen.setdefault(d, [d, float(opn), float(close), float(vol)])
    ordered = [seen[k] for k in sorted(seen)]
    dupes = len(rows) - bad_shape - nulls - nonpos - len(ordered)
    # Gaps against weekdays, which is the honest denominator for an index with no holiday file.
    first = datetime.fromisoformat(ordered[0][0]).date()
    last = datetime.fromisoformat(ordered[-1][0]).date()
    weekdays = sum(1 for i in range(first.toordinal(), last.toordinal() + 1)
                   if datetime.fromordinal(i).weekday() < 5)
    return {"rowsReturned": len(rows), "malformedRows": bad_shape, "rowsWithNulls": nulls,
            "nonPositiveOrNegativeVolume": nonpos, "duplicateDatesCollapsed": dupes,
            "distinctDates": len(ordered), "first": ordered[0][0], "last": ordered[-1][0],
            "weekdaysInRange": weekdays,
            "weekdayCoverage": round(len(ordered) / weekdays, 4) if weekdays else None,
            "ordered": ordered}


def cmd_fetch() -> None:
    symbol = sys.argv[2] if len(sys.argv) > 2 else "KSE100"
    got = fetch(symbol)
    print(json.dumps(got, indent=1))
    if not got.get("acquired"):
        raise SystemExit(1)
    v = validate(symbol)
    ordered = v.pop("ordered")
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["date", "open", "close", "volume"])
    w.writerows(ordered)
    blob = buf.getvalue().encode()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{symbol}.csv").write_bytes(blob)
    manifest = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "series": symbol, "name": "KSE-100 index, daily close",
        "sourceUrl": got["url"],
        "sourceNote": ("requires X-Req-Id (the page's own token) and X-Requested-With together; "
                       "either alone returns 404 or 403"),
        "fields": ["date", "open", "close", "volume"],
        "fieldsNotProvided": ["high", "low"],
        "basis": "index level as published by the exchange; not a total-return index",
        "file": f"{symbol}.csv", "sha256": hashlib.sha256(blob).hexdigest(),
        "validation": v,
        "frozenTargetRequiredFrom": REQUIRED_FROM,
        "coverageAgainstFrozenTarget": (
            "PARTIAL" if v["first"] > REQUIRED_FROM else "COMPLETE"),
        "missingAgainstFrozenTarget": (
            f"{REQUIRED_FROM} .. {v['first']}" if v["first"] > REQUIRED_FROM else None),
        "licensing": ("PSX's terms forbid redistributing its market data feed without a licence, "
                      "delayed included; recovery-manifest.json carries this as "
                      "psx-redistribution-licence, an accepted unresolved risk. Acquisition and "
                      "private use are unaffected; publishing these levels is not cleared."),
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    print(json.dumps({k: val for k, val in manifest.items() if k != "validation"}, indent=1))
    print(json.dumps(v, indent=1))


def cmd_verify() -> None:
    man = json.loads((OUT / "manifest.json").read_text("utf-8"))
    blob = (OUT / man["file"]).read_bytes()
    print(json.dumps({"file": man["file"],
                      "sha256Matches": hashlib.sha256(blob).hexdigest() == man["sha256"],
                      "rows": len(blob.decode().splitlines()) - 1,
                      "claimedDistinctDates": man["validation"]["distinctDates"]}, indent=1))


COMMANDS = {"fetch": cmd_fetch, "verify": cmd_verify}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        raise SystemExit(2)
    COMMANDS[sys.argv[1]]()
