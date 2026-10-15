"""Download a published SBP EasyData series the way its own download button does.

    python tools/foundation/sbp_easydata.py list            the series this knows how to fetch
    python tools/foundation/sbp_easydata.py get <KEY>       fetch one series by its EasyData key
    python tools/foundation/sbp_easydata.py frozen          the two the frozen target names

Why this exists
---------------
The KIBOR and SBP policy-rate histories were twice recorded as unreachable, because every static
path on sbp.org.pk is either a current-value page or a JavaScript document search over per-day
PDFs. They are, in fact, published -- in SBP's EasyData portal, an Oracle APEX 19.2 application,
where the series page carries a "Download Available Series" button.

That button is an ordinary page submit: `apex.submit({request:'DOWNLOAD'})` posts the page's own
form to `wwv_flow.accept`. This does the same thing, with the same public session the portal hands
any visitor: no login, no credential, no access control touched, and the portal's own declared
date range used as the request range rather than a guess. What comes back is the file the button
produces.

APEX 19.2 protects page items with per-item checksums, so the submit has to carry each item's `ck`
value from the rendered page -- which is why this reads the page first and never constructs a
request out of nothing.
"""

from __future__ import annotations

import html
import json
import re
import sys
import urllib.parse
import urllib.error
import urllib.request
from datetime import datetime, timezone
from http.cookiejar import CookieJar
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
STAGE = ROOT / ".cache" / "acquire" / "sbp"
OUT = ROOT / "data" / "foundation" / "sbp"

BASE = "https://easydata.sbp.org.pk/apex/"
HOME = "https://easydata.sbp.org.pk/"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/120.0 Safari/537.36")

# The two series the frozen target names, by their EasyData keys.
FROZEN = {
    "TS_GP_IR_SIRPR_AH.SBPOL0030": {
        "name": "SBP Policy (Target) Rate",
        "basis": "policy rate, per annum; not an interbank rate and not a repo amount"},
    "TS_GP_BAM_SIRKIBOR_D": {
        "name": "Structure of Interest Rates: KIBORs and KIBIDs",
        "basis": "interbank offered/bid rates by tenor; not the policy rate",
        "isDataset": True},
}


class CaptureRedirect(urllib.request.HTTPRedirectHandler):
    """Stop at the redirect and remember where it pointed.

    The submit answers 302 to the page that serves the file and gives that Location as `http://`.
    Following it as issued is a protocol downgrade the site's edge answers 403 to, so it is
    followed by hand over https -- through the same opener, because a second opener means a second
    cookie jar and the portal answers that with "Your session has expired".
    """
    location: str | None = None
    armed: bool = False          # only the submit is intercepted; ordinary navigation follows

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not CaptureRedirect.armed:
            return super().redirect_request(req, fp, code, msg, headers, newurl)
        CaptureRedirect.location = newurl
        return None


def opener():
    o = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()),
                                    CaptureRedirect)
    o.addheaders = [("User-Agent", UA), ("Accept", "text/html,application/xhtml+xml,*/*"),
                    ("Accept-Language", "en-US,en;q=0.9")]
    return o


def unescape(u: str) -> str:
    return html.unescape(u).encode().decode("unicode_escape")


def items_from(page: str, prefix: str) -> list[dict]:
    """Every page item of this page, with the per-item checksum APEX 19.2 requires on submit.

    Both hidden and visible inputs: the date filters the download honours are ordinary text
    fields, and leaving them out submits a page that is not the one the user was shown.
    """
    out, seen = [], set()
    for tag in re.findall(r"<input[^>]*>", page):
        name = re.search(r'name="(' + prefix + r'[A-Z0-9_]*)"', tag)
        if not name:
            continue
        n = name.group(1)
        if n in seen:
            continue
        v = re.search(r'value="([^"]*)"', tag)
        ck = re.search(r'<input[^>]*data-for="' + re.escape(n) + r'"[^>]*value="([^"]*)"', page)
        seen.add(n)
        out.append({"n": n, "v": html.unescape(v.group(1)) if v else "",
                    "ck": ck.group(1) if ck else ""})
    return out


def hidden(page: str, field: str, by: str = "name") -> str:
    """One hidden field's value, looked up by `name` or by `id`.

    APEX 19.2 carries the three fields that decide whether a submit is accepted --
    `pPageItemsProtected`, `pSalt` and `pPageItemsRowVersion` -- with an `id` and **no** `name`,
    and writes the value before the id. Looking only for `name=` finds none of them, and the
    submit comes back "Page protection violation".
    """
    attr = "id" if by == "id" else "name"
    m = re.search(r'<input[^>]*' + attr + r'="' + field + r'"[^>]*value="([^"]*)"', page)
    if not m:
        m = re.search(r'<input[^>]*value="([^"]*)"[^>]*' + attr + r'="' + field + r'"', page)
    return html.unescape(m.group(1)) if m else ""


def fetch(key: str) -> dict:
    """Walk the portal to the series' download page and submit its own DOWNLOAD request."""
    op = opener()

    def get(url: str):
        r = op.open(urllib.parse.urljoin(BASE, url), timeout=60)
        return r, r.read()

    _, home_b = get(HOME)
    home = home_b.decode("utf-8", "replace")

    base_key = key.split(".")[0]
    link = re.search(r'href="(f\?p=10:220:[^"]*' + re.escape(key) + r'[^"]*)"', home)
    if not link:
        link = re.search(r'href="(f\?p=10:21[01]:[^"]*' + re.escape(base_key) + r'[^"]*)"', home)
    if not link:
        return {"key": key, "acquired": False,
                "reason": "the portal's front page does not link this series today"}
    _, page_b = get(unescape(link.group(1)))
    page = page_b.decode("utf-8", "replace")

    # A single series downloads through page 222; a whole dataset through page 213. Both are the
    # same submit with a different page and item prefix, so the page decides which one applies
    # rather than the caller guessing.
    dl = re.search(r"redirect\('(f\?p=10:(?:222|213):[^']+)'\)", page)
    if not dl:
        return {"key": key, "acquired": False,
                "reason": "no download page is offered for this series"}
    step = "213" if ":213:" in dl.group(1) else "222"
    prefix = f"P{step}_"
    rng = re.search(r"SERIES_MIN_DATE,P222_SERIES_MAX_DATE[^:]*:[^,]+,[^,]+,([^,]+),([^,]+),",
                    unescape(dl.group(1)))
    _, f_b = get(unescape(dl.group(1)))
    form = f_b.decode("utf-8", "replace")

    payload = {
        "p_flow_id": hidden(form, "p_flow_id") or "10",
        "p_flow_step_id": hidden(form, "p_flow_step_id") or step,
        "p_instance": hidden(form, "p_instance"),
        "p_page_submission_id": hidden(form, "p_page_submission_id"),
        "p_request": "DOWNLOAD",
        "p_reload_on_submit": hidden(form, "p_reload_on_submit") or "A",
        "p_json": json.dumps({
            "pageItems": {"itemsToSubmit": items_from(form, prefix),
                          "protected": hidden(form, "pPageItemsProtected", by="id"),
                          "rowVersion": hidden(form, "pPageItemsRowVersion", by="id")},
            "salt": hidden(form, "pSalt", by="id"),
        }),
    }
    req = urllib.request.Request(
        urllib.parse.urljoin(BASE, "wwv_flow.accept"),
        data=urllib.parse.urlencode(payload).encode(),
        headers={"User-Agent": UA, "Content-Type": "application/x-www-form-urlencoded",
                 "Accept": "*/*", "Referer": urllib.parse.urljoin(BASE, unescape(dl.group(1)))})
    CaptureRedirect.location = None
    CaptureRedirect.armed = True
    body, ctype, disp, status = b"", "", "", None
    try:
        with op.open(req, timeout=120) as r:
            body, ctype, disp, status = (r.read(), r.headers.get("Content-Type", ""),
                                         r.headers.get("Content-Disposition", ""), r.status)
    except urllib.error.HTTPError as e:
        status = e.code
        if CaptureRedirect.location is None:
            CaptureRedirect.location = e.headers.get("Location")
    CaptureRedirect.armed = False
    if CaptureRedirect.location:
        target = CaptureRedirect.location.replace("http://", "https://", 1)
        CaptureRedirect.location = None
        with op.open(urllib.request.Request(
                target, headers={"User-Agent": UA, "Accept": "*/*"}), timeout=240) as r:
            body, ctype, disp, status = (r.read(), r.headers.get("Content-Type", ""),
                                         r.headers.get("Content-Disposition", ""), r.status)
    # A redirect back into the app means the submit was rejected; a file means it worked.
    looks_html = b"<!DOCTYPE html" in body[:200] or "text/html" in ctype
    STAGE.mkdir(parents=True, exist_ok=True)
    raw = STAGE / f"{key.replace('.', '_')}.raw"
    raw.write_bytes(body)
    return {"key": key, "acquired": not looks_html, "httpStatus": status,
            "contentType": ctype, "contentDisposition": disp, "bytes": len(body),
            "savedTo": str(raw.relative_to(ROOT)),
            "portalDateRange": [rng.group(1), rng.group(2)] if rng else None,
            "reason": None if not looks_html else
                      "the portal answered with a page rather than a file"}


def parse_delimited(blob: bytes) -> list[dict]:
    """Rows of {date, value...} from whatever delimited text the portal returned."""
    text = blob.decode("utf-8-sig", "replace")
    rows, header = [], None
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = [p.strip().strip('"') for p in re.split(r"[,\t;|]", line)]
        if header is None and not re.match(r"^\d|^\d{1,2}-\w{3}", parts[0]):
            header = parts
            continue
        rows.append(parts)
    return {"header": header, "rows": rows}


def cmd_frozen() -> None:
    report = {"fetchedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"), "series": {}}
    for key, meta in FROZEN.items():
        print(f"  {key} ...", flush=True)
        got = fetch(key)
        if got.get("acquired"):
            blob = (ROOT / got["savedTo"]).read_bytes()
            parsed = parse_delimited(blob)
            got["headerRow"] = parsed["header"]
            got["dataRows"] = len(parsed["rows"])
            got["firstRow"] = parsed["rows"][0] if parsed["rows"] else None
            got["lastRow"] = parsed["rows"][-1] if parsed["rows"] else None
        report["series"][key] = {**meta, **got}
        print("   ", json.dumps({k: v for k, v in got.items() if k != "savedTo"})[:260], flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "easydata_report.json").write_text(json.dumps(report, indent=1, default=str),
                                              encoding="utf-8")
    print(json.dumps(report, indent=1, default=str)[:1200])


def cmd_list() -> None:
    print(json.dumps(FROZEN, indent=1))


def cmd_get() -> None:
    key = sys.argv[2]
    print(json.dumps(fetch(key), indent=1, default=str))


COMMANDS = {"list": cmd_list, "get": cmd_get, "frozen": cmd_frozen}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        raise SystemExit(2)
    COMMANDS[sys.argv[1]]()
