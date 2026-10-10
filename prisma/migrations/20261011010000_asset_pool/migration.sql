-- The active scanning pool (jobs/pool.py). An asset below its market's liquidity floor is set
-- inactive and leaves the lists and the nightly calls; it is never deleted, its prices keep
-- updating, and it returns when its volume clears the floor again. `poolNote` says why it is out,
-- or that it was added by discovery and when.
ALTER TABLE "Asset" ADD COLUMN "active" BOOLEAN NOT NULL DEFAULT true;
ALTER TABLE "Asset" ADD COLUMN "poolNote" TEXT;
