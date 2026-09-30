-- The catalyst side of the discussion reading.
--
-- HumanSignal already measures attention over 30 days against the 30 before. That is a
-- trend, and a trend is the wrong instrument for the thing that actually costs a reader
-- money: an article, a statement or a report landing in the last few days that was not
-- landing before. Four items in three days against a baseline of one a week is an event and
-- reads as nothing at all on a monthly comparison, because a month is long enough to bury it.
--
-- So these columns measure the short window against the long one's daily rate, and are kept
-- separate from velocityPct rather than folded into it. Both are true at once and they
-- answer different questions.
--
-- All additive, all defaulted, and nothing already stored changes meaning.

ALTER TABLE "HumanSignal" ADD COLUMN     "recentItems" INTEGER NOT NULL DEFAULT 0,
ADD COLUMN     "baselineDaily" DOUBLE PRECISION,
ADD COLUMN     "spikeRatio" DOUBLE PRECISION,
ADD COLUMN     "catalyst" BOOLEAN NOT NULL DEFAULT false,
ADD COLUMN     "catalystNote" TEXT;

-- Asked for by the front page and by the asset pages: what has a catalyst right now, newest
-- first. A partial index, because the flag is false for nearly every row and an index over
-- the false ones would be most of the table.
CREATE INDEX "HumanSignal_catalyst_idx" ON "HumanSignal"("periodEnd" DESC)
    WHERE "catalyst" = true;
