-- The newest quote per asset: one row each, upserted in place by jobs/live.py.
--
-- A new table and nothing else. It touches no existing column, needs no backfill, and stays the size
-- of the universe: the key is the asset, so a newer quote overwrites the older and nothing accumulates.
-- That is deliberate. A row per tick would grow by 576 x 288 a day, which is the growth that took the
-- first database over its quota.
--
-- It is never an input to a decision. The rule table reads closes from "PriceSnapshot"; a quote is
-- displayed beside a close with the time it was struck, and does not replace one.
CREATE TABLE "LiveQuote" (
  "assetId"   TEXT             NOT NULL,
  "price"     DOUBLE PRECISION NOT NULL,
  "quotedAt"  TIMESTAMP(3)     NOT NULL,
  "source"    TEXT             NOT NULL,
  "updatedAt" TIMESTAMP(3)     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "LiveQuote_pkey" PRIMARY KEY ("assetId")
);

ALTER TABLE "LiveQuote"
  ADD CONSTRAINT "LiveQuote_assetId_fkey" FOREIGN KEY ("assetId") REFERENCES "Asset"("id") ON DELETE CASCADE ON UPDATE CASCADE;
