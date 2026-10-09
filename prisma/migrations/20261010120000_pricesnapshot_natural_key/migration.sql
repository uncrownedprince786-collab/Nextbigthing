-- Drop PriceSnapshot's surrogate key and make (assetId, date) the primary key.
--
-- Measured on this database on 2026-10-10, at 550,968 rows of Yahoo daily history:
--
--     heap                                    91 MB
--     PriceSnapshot_assetId_date_key          64 MB   unique (assetId, date)
--     PriceSnapshot_pkey                      39 MB   btree (id)
--     PriceSnapshot_date_idx                   5 MB
--     total                                  200 MB   of a 500 MB tier
--
-- `id` is a 37-byte text UUID. Nothing in the repository reads it: no query selects it, no join
-- uses it, no foreign key points at it, and neither write path names it -- `insert_snapshots`
-- lists nine columns in both its COPY and its upsert and lets the default produce the tenth. It
-- costs about 20 MB of heap and the whole 39 MB of its index, on the largest table in the budget.
--
-- `(assetId, date)` is the row's real identity. One close per asset per session is the premise of
-- every job that reads this table, and it was already enforced by the unique index above.
--
-- `USING INDEX` is the point of the third statement: it converts the existing unique index into
-- the primary key's index in place. Writing `PRIMARY KEY ("assetId", date)` instead would build a
-- second 64 MB index from scratch and then drop the first, which on a free tier is a peak nobody
-- needs to pay for.
--
-- **This changes no measurement.** Every close, volume, cap and OHLC value is left exactly as it
-- was. It is deliberately not a retention policy: `jobs/analogs.py` reads every stored close to
-- match today against the past, so shortening the history would shrink `analogs.count`, move
-- `medianPct` and change which names clear ANALOGS_CONFIRM_MIN. Dropping an unread key is the
-- saving that costs nothing; pruning the history is not.
--
-- NOTE on reclaiming the heap. Postgres marks a dropped column dead rather than rewriting the
-- table, so the ~20 MB of heap comes back on the next rewrite. The 39 MB of index is freed
-- immediately. `jobs/retention.py --reclaim` is where a VACUUM FULL belongs if it is wanted; it
-- takes an exclusive lock and is not run from a migration.
ALTER TABLE "PriceSnapshot" DROP CONSTRAINT "PriceSnapshot_pkey";
ALTER TABLE "PriceSnapshot" DROP COLUMN "id";
ALTER TABLE "PriceSnapshot"
  ADD CONSTRAINT "PriceSnapshot_pkey" PRIMARY KEY USING INDEX "PriceSnapshot_assetId_date_key";
