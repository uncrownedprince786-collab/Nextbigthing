-- The measured-conditions layer.
--
-- A state is produced by explicit rules over stored numbers, and the row keeps everything
-- needed to rederive it by hand: every condition that was tested including the failures, the
-- inputs that were not available, and the conditions pointing the other way. That last column
-- exists because the easy way to build a clean signal is to drop the data that disagrees, and
-- a table with nowhere to put it would quietly encourage exactly that.
--
-- `missing` is the column that makes the rest trustworthy. A rule that could not be evaluated
-- is reported as unevaluated, never as satisfied.
--
-- Entry and invalidation are levels computed from stored closes with their window stated,
-- not targets and not predictions. It describes conditions; it is not advice.

-- CreateTable
CREATE TABLE "AssetSetup" (
    "id" TEXT NOT NULL DEFAULT gen_random_uuid()::text,
    "assetId" TEXT NOT NULL,
    "periodEnd" DATE NOT NULL,
    "horizon" TEXT NOT NULL,
    "state" TEXT NOT NULL,
    "headline" TEXT NOT NULL,
    "conditions" TEXT NOT NULL,
    "missing" TEXT NOT NULL,
    "against" TEXT NOT NULL,
    "entryLevel" DOUBLE PRECISION,
    "entryNote" TEXT,
    "invalidateLevel" DOUBLE PRECISION,
    "invalidateNote" TEXT,
    "rangeNote" TEXT,
    "confidence" "Confidence" NOT NULL DEFAULT 'none',
    "confidenceNote" TEXT,
    "source" TEXT NOT NULL,
    "computedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "AssetSetup_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "AssetSetup_assetId_periodEnd_horizon_key"
    ON "AssetSetup"("assetId", "periodEnd", "horizon");
CREATE INDEX "AssetSetup_state_periodEnd_idx" ON "AssetSetup"("state", "periodEnd");

-- AddForeignKey
ALTER TABLE "AssetSetup" ADD CONSTRAINT "AssetSetup_assetId_fkey"
    FOREIGN KEY ("assetId") REFERENCES "Asset"("id") ON DELETE CASCADE ON UPDATE CASCADE;
