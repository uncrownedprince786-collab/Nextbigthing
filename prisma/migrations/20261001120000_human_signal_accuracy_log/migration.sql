-- Two additions. Neither changes an existing number, and neither reads a new source: both
-- are computed from News rows and PriceSnapshot rows the site already holds.
--
--  1. HumanSignal, the current discussion read for one asset or product in one window:
--     headline tone counted from a fixed word list, attention measured against the window
--     before, and a hype flag that is only ever both of those at once.
--  2. SignalLog, the accuracy record. A reading is written on the day it is generated and
--     jobs/accuracy.py returns at 30 and 60 days to store the move that followed.
--
-- Both carry targetRef, a copy of whichever of assetId or productId is set. Postgres treats
-- nulls as distinct in a unique index, so a key over the two nullable columns would not stop
-- a duplicate row for the same target; the alternative is a pair of partial indexes like the
-- ones News needs. One non-null column keeps the key plain and the upsert simple.

-- CreateEnum
CREATE TYPE "Tone" AS ENUM ('positive', 'negative', 'neutral');

-- CreateTable
CREATE TABLE "HumanSignal" (
    "id" TEXT NOT NULL DEFAULT gen_random_uuid()::text,
    "assetId" TEXT,
    "productId" TEXT,
    "targetRef" TEXT NOT NULL,
    "periodEnd" DATE NOT NULL,
    "windowDays" INTEGER NOT NULL,
    "items" INTEGER NOT NULL,
    "positive" INTEGER NOT NULL,
    "negative" INTEGER NOT NULL,
    "neutral" INTEGER NOT NULL,
    "tone" "Tone",
    "toneScore" DOUBLE PRECISION,
    "priorItems" INTEGER NOT NULL,
    "velocityPct" DOUBLE PRECISION,
    "attention" TEXT NOT NULL,
    "hypeTerms" INTEGER NOT NULL,
    "hypeShare" DOUBLE PRECISION,
    "hypeFlag" BOOLEAN NOT NULL DEFAULT false,
    "hypeNote" TEXT,
    "confidence" "Confidence" NOT NULL DEFAULT 'none',
    "confidenceNote" TEXT,
    "source" TEXT NOT NULL,
    "computedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "HumanSignal_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "SignalLog" (
    "id" TEXT NOT NULL DEFAULT gen_random_uuid()::text,
    "kind" TEXT NOT NULL,
    "assetId" TEXT,
    "productId" TEXT,
    "targetRef" TEXT NOT NULL,
    "issuedOn" DATE NOT NULL,
    "claim" TEXT NOT NULL,
    "factors" TEXT NOT NULL,
    "confidence" "Confidence" NOT NULL DEFAULT 'none',
    "baseDate" DATE,
    "baseClose" DOUBLE PRECISION,
    "move30Pct" DOUBLE PRECISION,
    "measured30On" DATE,
    "move60Pct" DOUBLE PRECISION,
    "measured60On" DATE,
    "status" TEXT NOT NULL DEFAULT 'open',
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "SignalLog_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "HumanSignal_targetRef_periodEnd_windowDays_key"
    ON "HumanSignal"("targetRef", "periodEnd", "windowDays");
CREATE INDEX "HumanSignal_assetId_periodEnd_idx" ON "HumanSignal"("assetId", "periodEnd");
CREATE INDEX "HumanSignal_productId_periodEnd_idx" ON "HumanSignal"("productId", "periodEnd");

CREATE UNIQUE INDEX "SignalLog_kind_targetRef_issuedOn_key"
    ON "SignalLog"("kind", "targetRef", "issuedOn");
CREATE INDEX "SignalLog_status_issuedOn_idx" ON "SignalLog"("status", "issuedOn");
CREATE INDEX "SignalLog_assetId_issuedOn_idx" ON "SignalLog"("assetId", "issuedOn");
CREATE INDEX "SignalLog_productId_issuedOn_idx" ON "SignalLog"("productId", "issuedOn");

-- AddForeignKey
ALTER TABLE "HumanSignal" ADD CONSTRAINT "HumanSignal_assetId_fkey"
    FOREIGN KEY ("assetId") REFERENCES "Asset"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "HumanSignal" ADD CONSTRAINT "HumanSignal_productId_fkey"
    FOREIGN KEY ("productId") REFERENCES "Product"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "SignalLog" ADD CONSTRAINT "SignalLog_assetId_fkey"
    FOREIGN KEY ("assetId") REFERENCES "Asset"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "SignalLog" ADD CONSTRAINT "SignalLog_productId_fkey"
    FOREIGN KEY ("productId") REFERENCES "Product"("id") ON DELETE CASCADE ON UPDATE CASCADE;
