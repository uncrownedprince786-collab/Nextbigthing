-- Intraday bars, and the record of what each fetch actually returned.
--
-- Stored at one canonical interval and derived upward. Five minutes is canonical because it is
-- the finest this provider serves more than a week of, and because 15, 30 and 60 all divide
-- into it exactly. Fetching each interval separately would multiply the request count by four
-- to obtain numbers already implied by the five minute series, which on a free endpoint is the
-- difference between a job that runs and one that gets banned.
--
-- `interval` is part of the unique key rather than a column to filter later. A 5m bar and a 15m
-- bar covering the same minute are two different observations of it, and a query that forgot to
-- say which it wanted would silently mix them into a series that never existed.
--
-- `derived` is stored rather than inferred from the interval, because this provider can serve
-- 15m directly and such a row is not derived. The distinction matters: a derived bar is
-- reproducible arithmetic, a fetched one is evidence, and evidence has to stay recoverable.
--
-- volume is nullable on purpose. A zero-volume bar is a real quiet five minutes, and collapsing
-- "no trades" and "no data" into the same value is exactly the silent data loss this schema
-- exists to prevent.
--
-- IntradaySession is the completeness record, and it is a separate table because the interesting
-- cases are the ones with no bars to store. Once bars are written, a provider that served half a
-- session looks identical to a genuinely quiet session; the only way to tell them apart is to
-- have written down how many bars the session should have had. barsExpected comes from the
-- provider's own stated trading period, never from a constant, so a half day holiday session is
-- not reported as a partial feed.
--
-- The `unsupported` status is what keeps the capability honest for assets this provider cannot
-- serve at all. PSX publishes end-of-day files and no intraday series, so its symbols get a row
-- saying that rather than no row — an absent row and an unserved asset would otherwise look
-- identical, and the first is a gap in the job while the second is a gap in the world.

-- CreateTable
CREATE TABLE "IntradayBar" (
    "id" TEXT NOT NULL DEFAULT gen_random_uuid()::text,
    "assetId" TEXT NOT NULL,
    "interval" INTEGER NOT NULL,
    "ts" TIMESTAMP(3) NOT NULL,
    "sessionDate" DATE NOT NULL,
    "open" DOUBLE PRECISION NOT NULL,
    "high" DOUBLE PRECISION NOT NULL,
    "low" DOUBLE PRECISION NOT NULL,
    "close" DOUBLE PRECISION NOT NULL,
    "volume" DOUBLE PRECISION,
    "phase" TEXT NOT NULL DEFAULT 'regular',
    "derived" BOOLEAN NOT NULL DEFAULT false,
    "derivedFrom" INTEGER,
    "source" TEXT NOT NULL,
    "retrievedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "IntradayBar_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "IntradaySession" (
    "id" TEXT NOT NULL DEFAULT gen_random_uuid()::text,
    "assetId" TEXT NOT NULL,
    "sessionDate" DATE NOT NULL,
    "interval" INTEGER NOT NULL,
    "status" TEXT NOT NULL,
    "barsExpected" INTEGER,
    "barsStored" INTEGER NOT NULL DEFAULT 0,
    "barsNull" INTEGER NOT NULL DEFAULT 0,
    "exchangeTz" TEXT,
    "firstTs" TIMESTAMP(3),
    "lastTs" TIMESTAMP(3),
    "note" TEXT NOT NULL,
    "source" TEXT NOT NULL,
    "retrievedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "IntradaySession_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
--
-- The unique index is also the idempotency guarantee: a rerun of the job upserts onto it, so a
-- retried workflow stores no duplicate bar.
CREATE UNIQUE INDEX "IntradayBar_assetId_interval_ts_key"
    ON "IntradayBar"("assetId", "interval", "ts");
-- The shape every read uses: one asset, one interval, one session, in time order.
CREATE INDEX "IntradayBar_assetId_interval_sessionDate_idx"
    ON "IntradayBar"("assetId", "interval", "sessionDate");
-- For the retention sweep, which deletes by age across all assets at once.
CREATE INDEX "IntradayBar_sessionDate_idx" ON "IntradayBar"("sessionDate");
CREATE UNIQUE INDEX "IntradaySession_assetId_sessionDate_interval_key"
    ON "IntradaySession"("assetId", "sessionDate", "interval");
-- For the health question: what is partial or failed, most recent first.
CREATE INDEX "IntradaySession_status_sessionDate_idx"
    ON "IntradaySession"("status", "sessionDate");

-- AddForeignKey
ALTER TABLE "IntradayBar" ADD CONSTRAINT "IntradayBar_assetId_fkey"
    FOREIGN KEY ("assetId") REFERENCES "Asset"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "IntradaySession" ADD CONSTRAINT "IntradaySession_assetId_fkey"
    FOREIGN KEY ("assetId") REFERENCES "Asset"("id") ON DELETE CASCADE ON UPDATE CASCADE;
