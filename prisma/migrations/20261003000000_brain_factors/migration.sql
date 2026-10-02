-- AlterTable
ALTER TABLE "AssetAnalog" ADD COLUMN     "p25Pct" DOUBLE PRECISION,
ADD COLUMN     "p75Pct" DOUBLE PRECISION;

-- CreateTable
CREATE TABLE "AssetFactor" (
    "id" TEXT NOT NULL DEFAULT gen_random_uuid()::text,
    "assetId" TEXT NOT NULL,
    "periodEnd" DATE NOT NULL,
    "r1" DOUBLE PRECISION,
    "r5" DOUBLE PRECISION,
    "r20" DOUBLE PRECISION,
    "returnZ" DOUBLE PRECISION,
    "volumeRatio" DOUBLE PRECISION,
    "peerMedianR20" DOUBLE PRECISION,
    "relStrength" DOUBLE PRECISION,
    "peers" INTEGER NOT NULL DEFAULT 0,
    "sma20" DOUBLE PRECISION,
    "sma50" DOUBLE PRECISION,
    "rangePct" DOUBLE PRECISION,
    "drawdownPct" DOUBLE PRECISION,
    "eventInDays" INTEGER,
    "newsStories" INTEGER,
    "bars" INTEGER NOT NULL,
    "source" TEXT NOT NULL,
    "computedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "AssetFactor_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "AnalogMatch" (
    "id" TEXT NOT NULL DEFAULT gen_random_uuid()::text,
    "analogId" TEXT NOT NULL,
    "matchedOn" DATE NOT NULL,
    "distance" DOUBLE PRECISION NOT NULL,
    "rank" INTEGER NOT NULL,
    "nextPct" DOUBLE PRECISION,
    "differences" TEXT NOT NULL,
    "computedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "AnalogMatch_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "DecisionLog" (
    "id" TEXT NOT NULL DEFAULT gen_random_uuid()::text,
    "assetId" TEXT NOT NULL,
    "periodEnd" DATE NOT NULL,
    "action" TEXT NOT NULL,
    "gate" TEXT NOT NULL,
    "confidence" TEXT NOT NULL,
    "entryLow" DOUBLE PRECISION,
    "entryHigh" DOUBLE PRECISION,
    "invalidation" DOUBLE PRECISION,
    "factorId" TEXT,
    "analogRefs" TEXT NOT NULL DEFAULT '',
    "eventInDays" INTEGER,
    "baseClose" DOUBLE PRECISION,
    "move1Pct" DOUBLE PRECISION,
    "measured1On" DATE,
    "move5Pct" DOUBLE PRECISION,
    "measured5On" DATE,
    "move20Pct" DOUBLE PRECISION,
    "measured20On" DATE,
    "status" TEXT NOT NULL DEFAULT 'open',
    "computedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "DecisionLog_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "ChunkRun" (
    "id" TEXT NOT NULL DEFAULT gen_random_uuid()::text,
    "job" TEXT NOT NULL,
    "source" TEXT NOT NULL,
    "chunk" TEXT NOT NULL DEFAULT '1/1',
    "rowsWritten" INTEGER NOT NULL DEFAULT 0,
    "asked" INTEGER NOT NULL DEFAULT 0,
    "newest" TIMESTAMP(3),
    "status" TEXT NOT NULL,
    "note" TEXT NOT NULL,
    "durationMs" INTEGER NOT NULL DEFAULT 0,
    "startedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "ChunkRun_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE INDEX "AssetFactor_periodEnd_idx" ON "AssetFactor"("periodEnd");

-- CreateIndex
CREATE UNIQUE INDEX "AssetFactor_assetId_periodEnd_key" ON "AssetFactor"("assetId", "periodEnd");

-- CreateIndex
CREATE INDEX "AnalogMatch_analogId_rank_idx" ON "AnalogMatch"("analogId", "rank");

-- CreateIndex
CREATE UNIQUE INDEX "AnalogMatch_analogId_matchedOn_key" ON "AnalogMatch"("analogId", "matchedOn");

-- CreateIndex
CREATE INDEX "DecisionLog_status_periodEnd_idx" ON "DecisionLog"("status", "periodEnd");

-- CreateIndex
CREATE INDEX "DecisionLog_gate_status_idx" ON "DecisionLog"("gate", "status");

-- CreateIndex
CREATE UNIQUE INDEX "DecisionLog_assetId_periodEnd_key" ON "DecisionLog"("assetId", "periodEnd");

-- CreateIndex
CREATE INDEX "ChunkRun_job_startedAt_idx" ON "ChunkRun"("job", "startedAt");

-- CreateIndex
CREATE INDEX "ChunkRun_status_startedAt_idx" ON "ChunkRun"("status", "startedAt");

-- CreateIndex
CREATE INDEX "ChunkRun_source_startedAt_idx" ON "ChunkRun"("source", "startedAt");

-- AddForeignKey
ALTER TABLE "AssetFactor" ADD CONSTRAINT "AssetFactor_assetId_fkey" FOREIGN KEY ("assetId") REFERENCES "Asset"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "AnalogMatch" ADD CONSTRAINT "AnalogMatch_analogId_fkey" FOREIGN KEY ("analogId") REFERENCES "AssetAnalog"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "DecisionLog" ADD CONSTRAINT "DecisionLog_assetId_fkey" FOREIGN KEY ("assetId") REFERENCES "Asset"("id") ON DELETE CASCADE ON UPDATE CASCADE;
