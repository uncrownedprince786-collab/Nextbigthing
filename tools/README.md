# tools

Read-only verification harnesses. Every statement in them is a `SELECT`; none writes a row.

They exist because the acceptance work on 2026-10-01 kept needing the same four questions
answered against the live database, and because a question answered by a committed script is
reproducible where one answered by a throwaway paste is not.

| script | answers |
| --- | --- |
| `acceptance.py` | the 27 acceptance criteria, each PASS / PARTIAL / FAIL with the measured figure |
| `intraday_chain.py` | the intraday chain end to end — source, bars, timestamps, session phases, exact 15/30/60 aggregation, completeness, setups, targets, retention, storage |
| `row_counts.py` | one row count per table, written to JSON so two runs can be diffed |
| `price_freshness.py` | newest stored date per price source, and whether today's rows landed |

Two of them are not read-only, and are listed apart because of it:

| script | does |
| --- | --- |
| `cloud_backup.py` | dumps every table to gzip CSV beside a manifest, re-reads what it wrote, and optionally uploads to Drive and the Sheets register. Reads the database; writes only files. |
| `restore_db.py` | reads one of those artifacts back into a database. The only thing here that can write rows, and the only one that refuses by default. |

## Recovering from a backup

`cloud_backup.py` writes a directory of `<table>.csv.gz` beside a `manifest.json`. `restore_db.py`
reads that directory back. Each file is what `COPY ... TO STDOUT (FORMAT csv, HEADER)` produced, so
an SQL NULL is an unquoted empty field and an empty string is `""`; the restore never parses a value
into Python, because both would arrive as `''` and the difference would be lost on the way back in.

```bash
python tools/restore_db.py verify  <dir>   # the artifact alone: files, checksums, row counts
python tools/restore_db.py plan    <dir>   # what would be loaded, in what order, against the target
python tools/restore_db.py restore <dir>   # load it, then read the target back and compare
```

**The target is `RESTORE_DATABASE_URL`, and there is no fall back to `DATABASE_URL`.** A restore is
refused unless that variable is set, and refused again if it names the same database as
`DATABASE_URL`, `SUPABASE_DATABASE_URL`, `DATABASE_URL_FALLBACK`, `DIRECT_DATABASE_URL` or the
primary of the moment — compared on host, port, database and the Supabase pooler user, so the pooled
and direct endpoints of one database are recognised as one database. A target that is not on this
machine needs `--allow-remote`, which a rehearsal does not need.

**The target must already be migrated**, to the migration the manifest was taken at, and every table
the backup covers must be empty. Nothing is dropped, truncated or deleted to make a restore fit, and
`_prisma_migrations` is never written: the migration that prepared the target already filled it.

A disposable target, start to finish:

```bash
docker run -d --name nbt-rehearsal -e POSTGRES_PASSWORD=... -p 55434:5432 postgres:16
docker exec nbt-rehearsal psql -U postgres -c "CREATE DATABASE nbt_rehearsal;"
DATABASE_URL=postgresql://postgres:...@127.0.0.1:55434/nbt_rehearsal \
  npx prisma migrate deploy --config prisma7.config.ts
RESTORE_DATABASE_URL=postgresql://postgres:...@127.0.0.1:55434/nbt_rehearsal \
  python tools/restore_db.py restore <dir>
docker rm -f nbt-rehearsal      # when the result has been read
```

### What the result means

The load is one transaction, so a target is either empty or complete. Row counts are compared to the
manifest before the commit; a disagreement rolls the whole load back rather than leaving a target
that is short a table and reads like a recovery.

Two different claims are printed, and they are not the same claim:

* `44 of 44 files match the manifest` — the **files** are the files. Checksums and row counts agree
  with what the backup recorded. This says nothing about any database.
* `VERIFIED: 43 tables, 688 rows, content digests equal` — the **database** now holds what the files
  hold. Every table is read back out through `COPY ... TO STDOUT` and compared by an XOR of per-row
  SHA-256 digests, which is order-independent because `COPY` has no `ORDER BY`.

A failure prints what disagreed and writes nothing. Re-running needs a freshly prepared target,
because the second attempt would otherwise find the first one's rows and refuse.

### What has actually been exercised

**A real backup, on 2026-10-13.** The artifact `cloud/from-artifact`
(`backup-2026-10-11T224424Z`, status `verified`, schema `20261011130000_decision_history`) is a
genuine dump of the primary, 44 tables and 867,839 rows, 29.9 MB compressed and 128.8 MB
decompressed. Copied to a scratch directory and left untouched where it lives, it was restored into
disposable containers twice:

| target | wall | peak RSS | result |
| --- | --- | --- | --- |
| PostgreSQL 16.15 | 184 s | 42.8 MB | 43 tables, 867,808 rows, every content digest equal |
| PostgreSQL 17.11 | 396 s | 43.7 MB | identical |

867,839 less 867,808 is the 31 rows of `_prisma_migrations`, which the migration writes and the
restore does not. Constraints after both: 45 foreign keys and 44 primary keys present, 138 indexes,
0 sequences — nothing was disabled to make the load fit. **42.8 MB of resident memory against a
128.8 MB dataset is the evidence that the path streams**: the whole artifact is never held.

A synthetic rehearsal on the same schema, reported separately from the above, covered the value
cases a real dump is unlikely to contain: a seeded database (576 assets, 30 products) plus rows
holding an SQL NULL, an empty string, commas, double quotes, embedded newlines, tabs, backslashes
and non-ASCII text, backed up and restored with the NULL and empty-string counts identical on both
sides.

Refusals exercised, each writing nothing and leaving the target at 0 rows: unset target, target
equal to the source, remote target, non-empty target, truncated gzip, one flipped byte, a missing
table file, a missing manifest, a wrong row count in the manifest, a table the backup does not
cover, and a column the target does not have.

**What this is not.** It is not evidence that the primary can be recovered *today*: the artifact is
from 2026-10-11, and no restore has been run against production, which is the only place a recovery
actually counts. It also does not establish the source server's version, because the manifest does
not record one — what the two rows above show is that the format restores into 16 and 17 alike.

## Running them

They read `DATABASE_URL` from the environment, or from the project's `.env`, exactly as the
jobs do. Nothing here points at a credential file outside the repo.

```bash
python tools/acceptance.py
python tools/intraday_chain.py
python tools/price_freshness.py
python tools/row_counts.py /tmp/before.json
```

## The idempotency proof

`row_counts.py` takes an output path so a before/after pair can be compared. Snapshot, re-run
the jobs, snapshot again, and diff: every entity table must be unchanged. `Coverage` and
`Calibration` are expected to grow, because they are append-only health history keyed on
`computedAt` — see the `Idempotency.APPEND_ONLY` list in `tests/test_brain.py`, which carries
the same exemption and the counts behind it.

`IntradayBar` can also legitimately grow between two snapshots taken while a market is open,
because new five minute bars genuinely arrive. The way to tell that apart from duplication is
the unique index: `IntradayBar_assetId_interval_ts_key` makes a duplicate `(asset, interval,
ts)` impossible, so a higher count with zero duplicate keys is new data rather than a
re-insert. `intraday_chain.py` checks exactly that.
