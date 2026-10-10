"""Copy the irreplaceable tables from one Neon project to another, by natural key. One way, additive.

This is the half of a failover that is easy to get dangerously wrong, so it says what it will not do
before it says what it does.

What it will not do
-------------------
  * **Delete anything from the target.** A row removed from the source stays in the copy. A mirror
    that propagates deletions turns one bad run against an emptied source into an emptied backup,
    and the whole point of a backup is that it survives the source's worst day.
  * **Run in both directions at once.** There is a source and a target, named on the command line,
    and the job refuses to copy a database onto itself. Two writers is split-brain, and nothing
    here resolves one.
  * **Copy rows whose asset the target does not have.** They are counted and named, not forced in.

Why it copies by natural key and not by row
-------------------------------------------
Every asset id is `gen_random_uuid()` assigned when the seed ran, so two projects seeded separately
hold **different ids for the same stock**. A plain row copy of `DecisionLog` from the old project
into the new one would either violate its foreign key or, if an id happened to exist, attach one
name's decision history to another name. So each source asset id is translated through
`(industry slug, symbol)` -- the identity the seed itself uses -- to the target's own id, and a row
with no counterpart is skipped rather than guessed.

What it copies
--------------
`DecisionLog` -- the learning corpus, and the one table nothing may lose: its +1, +5 and +20 session
maturations are what the scorecard learns from and cannot be recomputed. `PriceSnapshot` -- what
the site renders from, so a standby without it has nothing to show. `SignalLog` and `AssetThesis`
-- the other two records of what the system claimed and when.

Everything else is derived by the nightly chain from those and from the sources, and is cheaper to
recompute than to copy: a standby is brought current by running the lanes against it.

Run: python jobs/mirror.py --from-env DATABASE_URL --to-env DATABASE_URL_FALLBACK,SUPABASE_DATABASE_URL
         [--tables a,b] [--since YYYY-MM-DD] [--dry-run]
     (--from and --to take a URL directly, and --to may repeat)
     (or --from-env NAME --to-env NAME to read the two URLs from environment variables, which keeps
      a connection string off the command line and out of shell history)
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except Exception:  # noqa: BLE001
    pass

# table -> the columns that identify a row, which is the conflict target on the other side.
#
# `assetId` is in three of four and is translated. `SignalLog` is keyed on what it signalled and
# when, with `assetId` an optional pointer; the pointer is translated when present and left null
# when the source row had none.
TABLES: dict[str, tuple[str, ...]] = {
    "DecisionLog": ("assetId", "periodEnd"),
    "PriceSnapshot": ("assetId", "date"),
    "SignalLog": ("kind", "targetRef", "issuedOn"),
    "AssetThesis": ("assetId", "horizon", "openedOn"),
    # The macro gatekeeper's stored answers. Mirrored so a standby that takes over serves the same vetoes
    # as the primary; absent on a target the migration has not reached, in which case `copy_table` skips it.
    "MacroGate": ("assetId", "periodEnd"),
}

# The date column each table is keyed on, for `--since`. A nightly mirror copies a trailing window
# and not the whole history: six hundred thousand price rows rewritten every night would be the
# redundant write this project has spent a session removing. The window for `DecisionLog` has to
# reach back past the longest maturation (+20 sessions is about a month), because a row logged weeks
# ago is still being updated as its outcomes arrive.
DATE_COLUMN = {
    "DecisionLog": "periodEnd",
    "PriceSnapshot": "date",
    "SignalLog": "issuedOn",
    "AssetThesis": "openedOn",
    "MacroGate": "periodEnd",
}

# Rows per statement and per commit. Small enough that a dropped pooler connection costs one batch,
# large enough that the copy is not a round trip per row.
BATCH = 1000


@dataclass
class Tally:
    read: int = 0
    copied: int = 0
    unchanged: int = 0
    unmatched: int = 0
    unmatched_assets: set = field(default_factory=set)


# --- pure helpers -------------------------------------------------------------------------------


def same_database_key(url: str) -> tuple:
    """What selects a database in `url`, with the pooler suffix and the credentials ignored."""
    from urllib.parse import parse_qs, urlparse

    u = urlparse(url)
    host = (u.hostname or "").replace("-pooler", "")
    return (host, u.port or 5432, u.path.lstrip("/"), tuple(sorted(parse_qs(u.query).get("options", []))))


def same_database(a: str, b: str) -> bool:
    """True when two connection strings name the same place, so a copy would be a no-op or worse.

    Compares everything that selects a database -- host with the pooler suffix removed, database
    name, and any `options` -- and ignores the credentials, because the same database reached
    through two roles is still one database. The `-pooler` host and its direct twin are the same
    server and must compare equal, or the one mistake this guard exists for passes by changing a
    hostname.
    """
    from urllib.parse import parse_qs, urlparse

    def ident(url: str) -> tuple:
        u = urlparse(url)
        host = (u.hostname or "").replace("-pooler", "")
        q = parse_qs(u.query)
        return (host, u.port or 5432, u.path.lstrip("/"), tuple(sorted(q.get("options", []))))

    return ident(a) == ident(b)


def remap_row(
    row: dict, key_cols: tuple[str, ...], asset_map: dict, unmatched: set, product_map: dict | None = None
) -> dict | None:
    """The row with `assetId` translated to the target's id, or None when it cannot be.

    A null `assetId` stays null: `SignalLog` carries an optional pointer and a signal about no
    particular asset is a legitimate row. A non-null id with no counterpart returns None and is
    recorded, because forcing it in would either break the foreign key or file the row under
    the wrong name.
    """
    out = dict(row)
    if out.get("assetId") is not None:
        mapped = asset_map.get(out["assetId"])
        if mapped is None:
            unmatched.add(out["assetId"])
            return None
        out["assetId"] = mapped
    # `productId` is the same kind of per-database UUID. It was copied untranslated, so on
    # 2026-10-10 the first SignalLog row about a product broke the target's foreign key and failed
    # the whole mirror run. Translated through the product's slug exactly as an asset is through
    # its (industry, symbol); a product the target does not have is skipped and counted.
    if out.get("productId") is not None and product_map is not None:
        mapped = product_map.get(out["productId"])
        if mapped is None:
            unmatched.add("product:" + str(out["productId"]))
            return None
        out["productId"] = mapped
    return out


def shared_columns(source_cols: list[str], target_cols: list[str], key: tuple[str, ...]) -> list[str]:
    """Columns present on both sides, in the target's order, minus the surrogate `id`.

    Intersected rather than taken from either side, so a column added to one project and not yet
    migrated on the other does not fail the whole copy -- it is simply not copied, and the next run
    after the migration picks it up. `id` is excluded because it is a per-database UUID and the
    natural key is what identifies a row across them. The key columns must all be present, or the
    conflict clause cannot be written.
    """
    shared = [c for c in target_cols if c in set(source_cols) and c != "id"]
    missing = [c for c in key if c not in shared]
    if missing:
        raise ValueError(f"key column(s) {missing} are missing from one side")
    return shared


def upsert_sql(table: str, columns: list[str], key: tuple[str, ...]) -> str:
    """INSERT ... ON CONFLICT (key) DO UPDATE ... WHERE changed, as text with psycopg placeholders.

    The WHERE is `IS DISTINCT FROM` for the reason the factor and decision upserts use it: a rerun
    that changes nothing must not rewrite the row, and half these columns are legitimately null so
    `<>` would skip a null-to-number change. It compares every non-key column, so a maturation
    that arrived on the source since the last run is carried and an unchanged row costs nothing.
    """
    q = lambda c: '"' + c.replace('"', '""') + '"'  # noqa: E731
    cols = ", ".join(q(c) for c in columns)
    marks = ", ".join(f"%({c})s" for c in columns)
    changing = [c for c in columns if c not in key]
    if not changing:
        return f'INSERT INTO {q(table)} ({cols}) VALUES ({marks}) ON CONFLICT ({", ".join(q(k) for k in key)}) DO NOTHING'
    sets = ", ".join(f"{q(c)} = EXCLUDED.{q(c)}" for c in changing)
    old = ", ".join(f"{q(table)}.{q(c)}" for c in changing)
    new = ", ".join(f"EXCLUDED.{q(c)}" for c in changing)
    return (
        f"INSERT INTO {q(table)} ({cols}) VALUES ({marks}) "
        f'ON CONFLICT ({", ".join(q(k) for k in key)}) DO UPDATE SET {sets} '
        f"WHERE ({old}) IS DISTINCT FROM ({new})"
    )


# --- the copy -----------------------------------------------------------------------------------


def asset_identity(cur) -> dict[str, tuple[str, str]]:
    """{asset id: (industry slug, symbol)} for one database."""
    cur.execute(
        'SELECT a.id, i.slug, a.symbol FROM "Asset" a JOIN "Industry" i ON i.id = a."industryId"'
    )
    return {r["id"]: (r["slug"], r["symbol"]) for r in cur.fetchall()}


def build_asset_map(source_ids: dict, target_ids: dict) -> dict[str, str]:
    """{source asset id: target asset id}, joined on (industry slug, symbol)."""
    by_identity = {identity: tid for tid, identity in target_ids.items()}
    return {sid: by_identity[identity] for sid, identity in source_ids.items() if identity in by_identity}


def product_identity(cur) -> dict[str, str]:
    """{product id: slug} for one database. The slug is unique, so it is the product's name across both."""
    cur.execute('SELECT id, slug FROM "Product"')
    return {r["id"]: r["slug"] for r in cur.fetchall()}


def build_product_map(source_ids: dict, target_ids: dict) -> dict[str, str]:
    """{source product id: target product id}, joined on slug."""
    by_slug = {slug: tid for tid, slug in target_ids.items()}
    return {sid: by_slug[slug] for sid, slug in source_ids.items() if slug in by_slug}


def columns_of(cur, table: str) -> list[str]:
    cur.execute(
        """
        SELECT column_name FROM information_schema.columns
         WHERE table_schema = current_schema() AND table_name = %s ORDER BY ordinal_position
        """,
        (table,),
    )
    return [r["column_name"] for r in cur.fetchall()]


def copy_table(
    src, dst, table: str, asset_map: dict, dry_run: bool, since: str | None = None, product_map: dict | None = None
) -> Tally:
    key = TABLES[table]
    tally = Tally()
    with src.cursor() as sc, dst.cursor() as dc:
        scols = columns_of(sc, table)
        tcols = columns_of(dc, table)
        if not scols or not tcols:
            print(f"  {table:14} absent on one side, skipped")
            return tally
        cols = shared_columns(scols, tcols, key)
        sql = upsert_sql(table, cols, key)
        where = f' WHERE "{DATE_COLUMN[table]}" >= %s' if since else ""
        select = (
            "SELECT " + ", ".join('"' + c + '"' for c in cols) + f' FROM "{table}"' + where + " ORDER BY "
            + ", ".join('"' + k + '"' for k in key)
        )
        # Server side cursor, so a table of 600,000 rows is streamed rather than held in memory.
        with src.cursor(name=f"mirror_{table.lower()}") as stream:
            stream.itersize = BATCH
            stream.execute(select, (since,) if since else None)
            while True:
                batch = stream.fetchmany(BATCH)
                if not batch:
                    break
                tally.read += len(batch)
                out = []
                for row in batch:
                    mapped = remap_row(dict(zip(cols, row)) if not isinstance(row, dict) else row, key, asset_map, tally.unmatched_assets, product_map)
                    if mapped is None:
                        tally.unmatched += 1
                    else:
                        out.append(mapped)
                if out and not dry_run:
                    dc.executemany(sql, out)
                    # rowcount over executemany is the number of rows actually written: a skipped
                    # unchanged row writes nothing, which is how the clause is verified end to end.
                    tally.copied += max(dc.rowcount, 0)
                    dst.commit()
                elif out:
                    tally.copied += len(out)
        tally.unchanged = tally.read - tally.unmatched - tally.copied
    return tally


def redact(text: str) -> str:
    """The text with any connection string in it replaced. Applied to every error this job prints.

    A driver's error can carry the whole connection string -- psycopg's "invalid connection option"
    does, and one was printed with a live password in it earlier in this project's history -- and
    this job's output goes to a CI log that anyone with repository access can read.
    """
    import re

    return re.sub(r"postgres(?:ql)?://[^\s\"']+", "postgresql://<redacted>", text)


def option_values(argv: list[str], name: str) -> list[str]:
    """Every value given for a repeatable option, in order."""
    return [argv[i + 1] for i, a in enumerate(argv) if a == name and i + 1 < len(argv)]


def mirror_one(src_url: str, label: str, dst_url: str, chosen: list[str], dry: bool, since: str | None) -> bool:
    """Copy into one target. True when it completed. Never raises, and never prints a credential.

    Each target is its own unit of failure. With three databases the one most likely to be down is
    the one being copied to, and a run that stopped at the first dead target would leave every
    later one stale -- the standby most worth refreshing is the one the dead one was standing in for.
    """
    import psycopg
    from psycopg.rows import dict_row

    print(f"\n== target: {label}")
    try:
        src = psycopg.connect(src_url, row_factory=dict_row, connect_timeout=30)
        dst = psycopg.connect(dst_url, row_factory=dict_row, connect_timeout=30)
    except Exception as e:  # noqa: BLE001
        print(f"  could not connect: {redact(str(e).splitlines()[0])}")
        return False
    try:
        with src.cursor() as sc, dst.cursor() as dc:
            amap = build_asset_map(asset_identity(sc), asset_identity(dc))
            pmap = build_product_map(product_identity(sc), product_identity(dc))
        print(f"  assets matched by (industry, symbol): {len(amap)}")
        print(("  DRY RUN, nothing written\n" if dry else "") + f"  {'table':14} {'read':>9} {'written':>9} {'unchanged':>10} {'unmatched':>10}")
        for table in chosen:
            t = copy_table(src, dst, table, amap, dry, since, pmap)
            print(f"  {table:14} {t.read:>9} {t.copied:>9} {t.unchanged:>10} {t.unmatched:>10}")
            if t.unmatched_assets:
                print(f"      {len(t.unmatched_assets)} source asset(s) have no counterpart here, e.g. {sorted(t.unmatched_assets)[:3]}")
        return True
    except Exception as e:  # noqa: BLE001
        print(f"  failed part way: {redact(str(e).splitlines()[0])}")
        return False
    finally:
        for c in (src, dst):
            try:
                c.close()
            except Exception:  # noqa: BLE001
                pass


def main(argv: list[str]) -> int:
    """One source, any number of targets. Exit 0 only if every target completed.

    Targets come from repeated `--to URL` and from `--to-env NAME[,NAME...]`, which reads each URL
    from an environment variable so no connection string is ever on a command line or in a shell
    history. The source is `--from URL` or `--from-env NAME`.
    """

    def single(name: str) -> str | None:
        vals = option_values(argv, name)
        return vals[0] if vals else None

    # Stripped: a secret pasted with its trailing line break names a database that does not exist.
    src_url = (single("--from") or os.environ.get(single("--from-env") or "") or "").strip() or None
    targets: list[tuple[str, str]] = [(f"--to #{n + 1}", u) for n, u in enumerate(option_values(argv, "--to"))]
    for group in option_values(argv, "--to-env"):
        for env_name in filter(None, (g.strip() for g in group.split(","))):
            url = (os.environ.get(env_name) or "").strip() or None
            if not url:
                print(f"{env_name} is not set, so that target is skipped")
                continue
            targets.append((env_name, url))
    dry = "--dry-run" in argv
    since = single("--since")
    chosen = (single("--tables") or ",".join(TABLES)).split(",")
    unknown = [t for t in chosen if t not in TABLES]
    if unknown:
        print(f"unknown table(s) {unknown}; choose from {', '.join(TABLES)}")
        return 2
    if not src_url or not targets:
        print("need a source and at least one target: --from/--to, or --from-env/--to-env")
        return 2
    for label, url in targets:
        if same_database(src_url, url):
            print(f"refusing: the source and the target {label} are the same database")
            return 2
    seen: set[tuple] = set()
    for label, url in targets:
        key = same_database_key(url)
        if key in seen:
            print(f"refusing: {label} names the same database as an earlier target")
            return 2
        seen.add(key)

    results = {label: mirror_one(src_url, label, url, chosen, dry, since) for label, url in targets}
    print("\nsummary: " + ", ".join(f"{label} {'ok' if ok else 'FAILED'}" for label, ok in results.items()))
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
