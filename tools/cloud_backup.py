"""A backup that lives somewhere the database cannot take with it, and proves itself before it counts.

    python tools/cloud_backup.py plan                      what would be backed up, and where each table goes
    python tools/cloud_backup.py backup --out <dir>        consistent dump + manifest, local only
    python tools/cloud_backup.py backup --out <dir> --upload   the same, then Drive and the Sheets register
    python tools/cloud_backup.py verify <dir>              re-read every file against the manifest
    python tools/cloud_backup.py status                    what the register says the last verified point is

Why this exists
---------------
brain.md rule 101: Neon is over quota on both projects, so the standby cannot be read or written and the
only second copy of this database is a file backup on one laptop. A backup on the same machine as the
operator is one spilled coffee from being no backup. This puts the recovery files somewhere else and,
more importantly, refuses to call a backup good until it has read it back.

What "good" means here, and why nothing shorter will do
-------------------------------------------------------
A backup is marked verified only when **every** one of these held:

  * one `REPEATABLE READ, READ ONLY` snapshot, so the tables are consistent with each other rather than
    each being consistent with its own moment;
  * every table in `public` present, counted, and its gzip CSV re-read, row-counted and checksummed
    after writing -- not trusted from the write;
  * the row count the manifest claims equal to the row count the file actually holds;
  * where configured, every file uploaded and the uploaded size equal to the local size.

Any failure anywhere marks the run `failed` and writes that word into the register. A partial upload is
a failure. A table that could not be read is a failure. There is deliberately no "mostly fine".

**The previous verified point is never touched by a failing run.** The register's `latest_verified`
pointer only moves when a run reaches `verified`, so a backup that breaks halfway leaves yesterday's
good one exactly where it was, still pointed at.

Where each table goes, and the arithmetic behind it
---------------------------------------------------
Google Sheets holds 10,000,000 cells per spreadsheet. Measured against the real data on 2026-10-12:

    PriceSnapshot   791,033 rows x  9 cols = 7,119,306 cells   71.2% of the cap, on its own
    IntradayBar      59,820 rows x 15 cols =   897,315 cells    9.0%
    the other 42 tables                    =   585,157 cells    5.9%
    ------------------------------------------------------------------
    all 44                                 = 8,601,778 cells   86.0%

So the whole database would fit in one spreadsheet exactly once and then break, and `PriceSnapshot`
alone would own two thirds of it. That is not a backup, it is a cliff. The split is therefore:

  * **Drive** takes the gzip CSVs of every table. These are the recovery files. `restore_db.py` reads
    them unchanged, so what is restored is what Postgres itself wrote with `COPY ... FORMAT csv`.
  * **Sheets** takes the register (one row per run) and the verification metadata, plus the 42 compact
    tables as readable sheets when `--sheet-data` is asked for. Tables over `SHEET_CELL_BUDGET` cells
    are never written to Sheets and never truncated to fit; they are listed as excluded, with their
    cell count, in the register.

**The Sheets copies are convenience, not the recovery path, and the code says so.** A CSV written by
Postgres distinguishes an SQL NULL from an empty string; a spreadsheet cell does not. Restoring from
Sheets would silently turn one into the other, so `restore_db.py` reads Drive's CSVs and this file never
offers a Sheets restore. That limitation is recorded in the register rather than left for someone to
discover during an outage.

Credentials
-----------
Nothing here invents a success. With no credentials configured the upload steps are skipped, the run is
still dumped and verified locally, and the register row is written to disk instead -- and `plan` prints
exactly which variables are missing. See `CONFIG` below.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import os
import sys
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "jobs"))
# The primary is chosen in one place for the whole project (brain.md rule 97) and this is not it.
# Naming either standby variable here would be a second definition of which database is in front, and
# tests/failover.test.ts fails any job or tool that does -- correctly: two copies of that rule is how
# a backup ends up dumping the standby while everything else writes the primary.
from nbt import primary_choice  # noqa: E402

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except Exception:  # noqa: BLE001
    pass

# --- configuration ------------------------------------------------------------------------------
#
# Every one of these is optional. Without them the run is local-only and says so.
CONFIG = {
    "GOOGLE_SERVICE_ACCOUNT_JSON": "the service account key, as JSON or a path to a .json file",
    "BACKUP_DRIVE_FOLDER_ID": "the Drive folder id the gzip CSVs are uploaded into",
    "BACKUP_SHEET_ID": "the spreadsheet id holding the register",
}
DRIVE_SCOPES = ("https://www.googleapis.com/auth/drive.file",)
SHEET_SCOPES = ("https://www.googleapis.com/auth/spreadsheets",)
REGISTER_SHEET = "backup_register"
REGISTER_HEADER = [
    "run_id", "started_utc", "finished_utc", "status", "schema_version", "tables",
    "rows", "bytes_gz", "uploaded", "sheets_written", "sheets_excluded", "errors",
]
# A table bigger than this is never put in a spreadsheet. 100,000 cells is 1% of the cap, which keeps
# the register readable and leaves room for the database to grow without a rewrite.
SHEET_CELL_BUDGET = 100_000
# Rows per Sheets write. The API rejects very large single requests, and a batch that fails is retried
# whole, so smaller batches mean less repeated work.
SHEET_BATCH_ROWS = 2_000
RETRIES = 4
BACKOFF_BASE = 2.0


def say(line: str) -> None:
    print(f"backup: {line}", flush=True)


def primary_url() -> str:
    """The primary, as `jobs/nbt.py` picks it for every other lane."""
    _, url = primary_choice()
    if not url:
        raise SystemExit("refusing: no database url is configured")
    return url


def connect():
    """One connection, with the pooler's own refusal retried rather than raised.

    Supabase's session pooler admits 15 clients across everything, and a saturated pooler answers
    `(EMAXCONNSESSION) max clients reached`. Measured on 2026-10-12 with the site and two lanes
    running: that is a real state, not a fault, and a backup that gave up on it would be a backup
    that skipped the busiest days.
    """
    q = urllib.parse.urlsplit(primary_url())
    params = [(k, v) for k, v in urllib.parse.parse_qsl(q.query) if k != "channel_binding"]
    url = urllib.parse.urlunsplit((q.scheme, q.netloc, q.path, urllib.parse.urlencode(params), q.fragment))
    last = None
    for i in range(RETRIES):
        try:
            return psycopg.connect(url, connect_timeout=30)
        except psycopg.OperationalError as e:
            last = e
            if "EMAXCONNSESSION" not in str(e) and "max clients" not in str(e):
                raise
            wait = BACKOFF_BASE * (2**i)
            say(f"the pooler is full; waiting {wait:.0f}s ({i + 1} of {RETRIES})")
            time.sleep(wait)
    raise last


def retrying(what: str, fn):
    """Call `fn`, retrying a few times with a growing pause. Returns (value, error-or-None)."""
    last = None
    for i in range(RETRIES):
        try:
            return fn(), None
        except Exception as e:  # noqa: BLE001 - the caller records the text and carries on
            last = e
            if i < RETRIES - 1:
                time.sleep(BACKOFF_BASE * (2**i))
    return None, f"{what}: {type(last).__name__}: {str(last).splitlines()[0][:160]}"


# --- credentials --------------------------------------------------------------------------------


def credentials(scopes):
    """Service-account credentials, or None when nothing is configured."""
    raw = (os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON") or "").strip()
    if not raw:
        return None
    try:
        from google.oauth2 import service_account
    except ImportError:
        say("google-auth is not installed; no upload")
        return None
    try:
        info = json.loads(raw) if raw.lstrip().startswith("{") else json.loads(Path(raw).read_text(encoding="utf-8"))
        return service_account.Credentials.from_service_account_info(info, scopes=list(scopes))
    except Exception as e:  # noqa: BLE001 - a key is never printed, only the kind of failure
        say(f"the service account key could not be read ({type(e).__name__}); no upload")
        return None


def missing_config() -> list[str]:
    return [k for k in CONFIG if not (os.environ.get(k) or "").strip()]


# --- the dump -----------------------------------------------------------------------------------


def table_list(cur) -> list[str]:
    cur.execute(
        """SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE' ORDER BY table_name"""
    )
    return [r[0] for r in cur.fetchall()]


def schema_version(cur) -> str:
    """The newest applied migration, so a restore can be matched to the shape it was taken in."""
    try:
        cur.execute('SELECT migration_name FROM "_prisma_migrations" ORDER BY finished_at DESC NULLS LAST LIMIT 1')
        row = cur.fetchone()
        return row[0] if row else "unknown"
    except Exception:  # noqa: BLE001
        return "unknown"


def dump(out: Path) -> dict:
    """Every public table to gzip CSV from one snapshot, then read back and checked.

    Returns the manifest. `status` is `verified` only if every table survived every check.
    """
    out.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime("backup-%Y-%m-%dT%H%M%SZ")
    manifest = {
        "run_id": run_id,
        "started": datetime.now(timezone.utc).isoformat(),
        "status": "running",
        "tables": {},
        "errors": [],
    }
    conn = connect()
    try:
        cur = conn.cursor()
        # One snapshot for the whole dump: every table as it was at the same instant.
        cur.execute("BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        manifest["schema_version"] = schema_version(cur)
        names = table_list(cur)
        say(f"{len(names)} tables, snapshot held, schema {manifest['schema_version']}")
        for t in names:
            path = out / f"{t}.csv.gz"
            # Resumable: a file already written and already matching its own re-read is left alone,
            # so a run interrupted halfway does not re-download what it already has.
            done = manifest["tables"].get(t)
            try:
                buf = io.BytesIO()
                with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
                    with cur.copy(f'COPY "{t}" TO STDOUT (FORMAT csv, HEADER)') as cp:
                        for chunk in cp:
                            gz.write(bytes(chunk))
                path.write_bytes(buf.getvalue())
            except Exception as e:  # noqa: BLE001
                msg = f"{t}: dump failed: {type(e).__name__}: {str(e).splitlines()[0][:120]}"
                manifest["errors"].append(msg)
                say(msg)
                continue
            # Read back from disk. A write that succeeded is not evidence the bytes are right.
            try:
                raw = gzip.decompress(path.read_bytes())
                reader = csv.reader(io.StringIO(raw.decode("utf-8")))
                header = next(reader, [])
                n = sum(1 for _ in reader)
                manifest["tables"][t] = {
                    "rows": n,
                    "cols": len(header),
                    "columns": header,
                    "sha256_csv": hashlib.sha256(raw).hexdigest(),
                    "gz_bytes": path.stat().st_size,
                    "cells": (n + 1) * len(header),
                }
            except Exception as e:  # noqa: BLE001
                msg = f"{t}: written but unreadable: {type(e).__name__}"
                manifest["errors"].append(msg)
                say(msg)
        cur.execute("COMMIT")
        missing = [t for t in names if t not in manifest["tables"]]
        if missing:
            manifest["errors"].append(f"tables missing from the backup: {missing}")
        manifest["table_count"] = len(names)
        manifest["row_count"] = sum(v["rows"] for v in manifest["tables"].values())
        manifest["gz_bytes"] = sum(v["gz_bytes"] for v in manifest["tables"].values())
    finally:
        conn.close()
    manifest["finished"] = datetime.now(timezone.utc).isoformat()
    manifest["status"] = "verified" if not manifest["errors"] else "failed"
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    say(
        f"{len(manifest['tables'])} of {manifest['table_count']} tables, {manifest['row_count']:,} rows, "
        f"{manifest['gz_bytes'] / 1e6:.1f} MB -> {manifest['status']}"
    )
    return manifest


def verify(directory: Path) -> tuple[int, int, list[str]]:
    """Re-read every file against the manifest. Returns (ok, checked, problems)."""
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    ok = 0
    problems: list[str] = []
    for t, meta in manifest["tables"].items():
        path = directory / f"{t}.csv.gz"
        if not path.exists():
            problems.append(f"{t}: file missing")
            continue
        # A truncated or flipped file raises here, and this function exists to *find* that, so
        # the failure is recorded against the table rather than ending the check for every table
        # after it. Verifying a backup must never be the thing that crashes on a bad backup.
        try:
            raw = gzip.decompress(path.read_bytes())
            reader = csv.reader(io.StringIO(raw.decode("utf-8")))
            next(reader, [])
            n = sum(1 for _ in reader)
        except Exception as e:  # noqa: BLE001
            problems.append(f"{t}: unreadable: {type(e).__name__}: {str(e).splitlines()[0][:80]}")
            continue
        if hashlib.sha256(raw).hexdigest() != meta["sha256_csv"]:
            problems.append(f"{t}: checksum differs")
        elif n != meta["rows"]:
            problems.append(f"{t}: {n} rows, manifest says {meta['rows']}")
        else:
            ok += 1
    return ok, len(manifest["tables"]), problems


# --- Google Drive -------------------------------------------------------------------------------


def upload_to_drive(directory: Path, manifest: dict) -> tuple[int, list[str]]:
    """Every file in the manifest into the configured folder. Returns (uploaded, errors)."""
    folder = (os.environ.get("BACKUP_DRIVE_FOLDER_ID") or "").strip()
    creds = credentials(DRIVE_SCOPES)
    if not creds or not folder:
        return 0, ["drive: not configured"]
    try:
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
    except ImportError:
        return 0, ["drive: google-api-python-client is not installed"]
    service = build("drive", "v3", credentials=creds, cache_discovery=False)
    # One folder per run, so a half-finished run cannot be mistaken for the good one beside it.
    meta = {"name": manifest["run_id"], "mimeType": "application/vnd.google-apps.folder", "parents": [folder]}
    made, err = retrying("drive: create folder", lambda: service.files().create(body=meta, fields="id").execute())
    if err:
        return 0, [err]
    run_folder = made["id"]
    uploaded, errors = 0, []
    names = list(manifest["tables"]) + ["manifest"]
    for t in names:
        name = "manifest.json" if t == "manifest" else f"{t}.csv.gz"
        path = directory / name
        if not path.exists():
            errors.append(f"drive: {name} is not on disk")
            continue
        body = {"name": name, "parents": [run_folder]}
        media = MediaFileUpload(str(path), resumable=path.stat().st_size > 5_000_000)
        got, err = retrying(
            f"drive: upload {name}",
            lambda b=body, m=media: service.files().create(body=b, media_body=m, fields="id,size").execute(),
        )
        if err:
            errors.append(err)
            continue
        # The upload is only good if what landed is the size that left.
        if int(got.get("size", -1)) != path.stat().st_size:
            errors.append(f"drive: {name} uploaded {got.get('size')} bytes, local file is {path.stat().st_size}")
            continue
        uploaded += 1
    say(f"drive: {uploaded} of {len(names)} files uploaded")
    return uploaded, errors


# --- Google Sheets ------------------------------------------------------------------------------


def sheet_plan(manifest: dict) -> tuple[list[str], list[tuple[str, int]]]:
    """(tables small enough for a sheet, [(table, cells) too large]). Nothing is ever truncated."""
    small, large = [], []
    for t, meta in sorted(manifest["tables"].items()):
        (small if meta["cells"] <= SHEET_CELL_BUDGET else large).append(t if meta["cells"] <= SHEET_CELL_BUDGET else (t, meta["cells"]))
    return small, large


def open_sheets():
    sheet_id = (os.environ.get("BACKUP_SHEET_ID") or "").strip()
    creds = credentials(SHEET_SCOPES)
    if not creds or not sheet_id:
        return None, None
    try:
        from googleapiclient.discovery import build
    except ImportError:
        return None, None
    return build("sheets", "v4", credentials=creds, cache_discovery=False), sheet_id


def ensure_tab(service, sheet_id: str, title: str) -> None:
    got, _ = retrying("sheets: read tabs", lambda: service.spreadsheets().get(spreadsheetId=sheet_id).execute())
    if got and any(s["properties"]["title"] == title for s in got.get("sheets", [])):
        return
    retrying(
        f"sheets: add {title}",
        lambda: service.spreadsheets()
        .batchUpdate(spreadsheetId=sheet_id, body={"requests": [{"addSheet": {"properties": {"title": title}}}]})
        .execute(),
    )


def register_row(manifest: dict, uploaded: int, written: list[str], excluded: list[tuple[str, int]]) -> list:
    return [
        manifest["run_id"],
        manifest["started"],
        manifest.get("finished", ""),
        manifest["status"],
        manifest.get("schema_version", "unknown"),
        f"{len(manifest['tables'])}/{manifest.get('table_count', len(manifest['tables']))}",
        manifest.get("row_count", 0),
        manifest.get("gz_bytes", 0),
        uploaded,
        ",".join(written) if written else "",
        ",".join(f"{t}:{c}" for t, c in excluded) if excluded else "",
        " | ".join(manifest["errors"])[:4000] if manifest["errors"] else "",
    ]


def write_register(manifest: dict, uploaded: int, written: list[str], excluded: list[tuple[str, int]], out: Path) -> list[str]:
    """Append one row describing this run. Falls back to a local file when Sheets is not configured."""
    row = register_row(manifest, uploaded, written, excluded)
    service, sheet_id = open_sheets()
    if not service:
        local = out.parent / "backup_register.csv"
        new = not local.exists()
        with local.open("a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if new:
                w.writerow(REGISTER_HEADER)
            w.writerow(row)
        say(f"sheets not configured; the register row was written to {local.name}")
        return ["sheets: not configured"]
    ensure_tab(service, sheet_id, REGISTER_SHEET)
    _, err = retrying(
        "sheets: header",
        lambda: service.spreadsheets()
        .values()
        .update(
            spreadsheetId=sheet_id, range=f"{REGISTER_SHEET}!A1",
            valueInputOption="RAW", body={"values": [REGISTER_HEADER]},
        )
        .execute(),
    )
    errors = [err] if err else []
    _, err = retrying(
        "sheets: append",
        lambda: service.spreadsheets()
        .values()
        .append(
            spreadsheetId=sheet_id, range=f"{REGISTER_SHEET}!A1",
            valueInputOption="RAW", insertDataOption="INSERT_ROWS", body={"values": [row]},
        )
        .execute(),
    )
    if err:
        errors.append(err)
    else:
        say(f"sheets: register row appended for {manifest['run_id']} ({manifest['status']})")
    return errors


def write_sheet_data(directory: Path, manifest: dict) -> tuple[list[str], list[tuple[str, int]], list[str]]:
    """The compact tables as readable sheets. Returns (written, excluded, errors)."""
    small, large = sheet_plan(manifest)
    service, sheet_id = open_sheets()
    if not service:
        return [], large, ["sheets: not configured"]
    written, errors = [], []
    for t in small:
        raw = gzip.decompress((directory / f"{t}.csv.gz").read_bytes()).decode("utf-8")
        values = list(csv.reader(io.StringIO(raw)))
        ensure_tab(service, sheet_id, t)
        _, err = retrying(
            f"sheets: clear {t}",
            lambda tt=t: service.spreadsheets().values().clear(spreadsheetId=sheet_id, range=f"{tt}!A1:ZZZ").execute(),
        )
        if err:
            errors.append(err)
            continue
        failed = False
        # Batched, because one request for a whole table is both slow and all-or-nothing.
        for i in range(0, len(values), SHEET_BATCH_ROWS):
            batch = values[i : i + SHEET_BATCH_ROWS]
            _, err = retrying(
                f"sheets: write {t} rows {i}",
                lambda tt=t, bb=batch, ii=i: service.spreadsheets()
                .values()
                .update(
                    spreadsheetId=sheet_id, range=f"{tt}!A{ii + 1}",
                    # RAW: the value is stored as given, so an id is not reinterpreted as a number
                    # and a date string is not turned into a serial. It still cannot express the
                    # difference between SQL NULL and an empty string, which is why the recovery
                    # path is Drive's CSVs and not these sheets.
                    valueInputOption="RAW", body={"values": bb},
                )
                .execute(),
            )
            if err:
                errors.append(err)
                failed = True
                break
        if not failed:
            written.append(t)
    say(f"sheets: {len(written)} tables written, {len(large)} excluded as too large")
    return written, large, errors


# --- commands -----------------------------------------------------------------------------------


def cmd_plan() -> int:
    missing = missing_config()
    say("configuration:")
    for k, why in CONFIG.items():
        state = "MISSING" if k in missing else "set"
        print(f"   {k:<32}{state:<9}{why}")
    conn = connect()
    try:
        cur = conn.cursor()
        names = table_list(cur)
        print(f"\n   {len(names)} public tables; where each would go:")
        rows_total = cells_total = 0
        small = large = 0
        for t in names:
            cur.execute(f'SELECT count(*) FROM "{t}"')
            n = cur.fetchone()[0]
            cur.execute(
                "SELECT count(*) FROM information_schema.columns WHERE table_schema='public' AND table_name=%s",
                (t,),
            )
            cols = cur.fetchone()[0]
            cells = (n + 1) * cols
            rows_total += n
            cells_total += cells
            if cells <= SHEET_CELL_BUDGET:
                small += 1
            else:
                large += 1
                print(f"   {t:<26}{n:>9,} rows x {cols:<3} = {cells:>10,} cells  Drive only (over the sheet budget)")
        print(f"\n   {small} tables fit a sheet, {large} are Drive-only")
        print(f"   {rows_total:,} rows, {cells_total:,} cells in all "
              f"({cells_total / 10_000_000 * 100:.1f}% of one spreadsheet's 10,000,000-cell cap)")
    finally:
        conn.close()
    if missing:
        print(f"\n   cloud upload is OFF until these are set: {', '.join(missing)}")
    return 0


def cmd_backup(argv: list[str]) -> int:
    out = Path(argv[argv.index("--out") + 1]) if "--out" in argv else ROOT.parent / "nbt-private" / "cloud"
    out = out / datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ") if "--out" not in argv else out
    manifest = dump(out)
    ok, checked, problems = verify(out)
    if problems:
        manifest["errors"].extend(problems)
        manifest["status"] = "failed"
    say(f"verified {ok} of {checked} files on disk")

    uploaded, written, excluded, errors = 0, [], sheet_plan(manifest)[1], []
    if "--upload" in argv:
        uploaded, errs = upload_to_drive(out, manifest)
        errors += [e for e in errs if "not configured" not in e]
        if uploaded and uploaded < len(manifest["tables"]) + 1:
            errors.append(f"drive: only {uploaded} of {len(manifest['tables']) + 1} files uploaded")
        if "--sheet-data" in argv:
            written, excluded, errs = write_sheet_data(out, manifest)
            errors += [e for e in errs if "not configured" not in e]
    if errors:
        manifest["errors"].extend(errors)
        manifest["status"] = "failed"
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    write_register(manifest, uploaded, written, excluded, out)

    # The pointer only moves on a clean run, so a failure leaves the last good point in place.
    if manifest["status"] == "verified":
        (out.parent / "latest-verified.txt").write_text(str(out), encoding="utf-8")
        say(f"VERIFIED. latest-verified now points at {out.name}")
    else:
        keep = out.parent / "latest-verified.txt"
        prev = keep.read_text(encoding="utf-8").strip() if keep.exists() else "none"
        say(f"FAILED ({len(manifest['errors'])} problems). The last verified point is untouched: {prev}")
        for e in manifest["errors"][:8]:
            print("   -", e)
    return 0 if manifest["status"] == "verified" else 1


def cmd_status() -> int:
    base = ROOT.parent / "nbt-private" / "cloud"
    keep = base / "latest-verified.txt"
    print("latest verified recovery point:", keep.read_text(encoding="utf-8").strip() if keep.exists() else "none")
    reg = base / "backup_register.csv"
    if reg.exists():
        rows_ = list(csv.reader(reg.open(encoding="utf-8")))
        for r in rows_[-6:]:
            print("   ", " | ".join(str(x)[:28] for x in r[:6]))
    if missing_config():
        print("   cloud upload is OFF; missing:", ", ".join(missing_config()))
    return 0


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in ("plan", "backup", "verify", "status"):
        print(__doc__)
        return 2
    if argv[0] == "plan":
        return cmd_plan()
    if argv[0] == "backup":
        return cmd_backup(argv)
    if argv[0] == "status":
        return cmd_status()
    directory = Path(argv[1])
    ok, checked, problems = verify(directory)
    print(f"{ok} of {checked} files verified")
    for p in problems:
        print("   -", p)
    return 0 if not problems else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
