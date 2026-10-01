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
