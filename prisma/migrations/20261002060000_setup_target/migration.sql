-- Target ranges, one row per method, with the disagreement between methods preserved.
--
-- A separate table rather than columns on AssetSetup, because a target is the part of a setup
-- most likely to be absent. Five nullable columns in the middle of a row that is otherwise
-- always complete would also make "no target the data supports" and "target not computed yet"
-- the same state, and only the first of those is a finding.
--
-- One row per method is the point. Three independent measurements of the same question —
-- structure, volatility, and what actually followed similar past days — will not agree, and
-- averaging them into one number would manufacture a certainty none of them supports. So each
-- keeps its own range and its own note, and `agreement` records how far apart they were as a
-- share of the furthest one's distance. The UI shows the spread.
--
-- Nothing here is a prediction. A structural target is a price the series has already stopped
-- at; a volatility target is a distance this asset has typically covered; an analog target is a
-- measured distribution of past outcomes. Each note says what it is not.
--
-- A row is only written when the setup also has an invalidation level, because reward with no
-- risk behind it is a number with no decision attached to it. That is enforced by the job
-- rather than by a constraint, since the setup's own columns are nullable for good reasons.
--
-- No new horizon column is needed anywhere: AssetSetup.horizon is already free text with a
-- unique key on (assetId, periodEnd, horizon), so `intraday` and `longer` rows sit alongside
-- the existing `swing` ones with no schema change at all. The same asset reading differently on
-- different horizons is the intended behaviour, not a conflict to resolve.

-- CreateTable
CREATE TABLE "SetupTarget" (
    "id" TEXT NOT NULL DEFAULT gen_random_uuid()::text,
    "setupId" TEXT NOT NULL,
    "method" TEXT NOT NULL,
    "low" DOUBLE PRECISION NOT NULL,
    "high" DOUBLE PRECISION NOT NULL,
    "distancePct" DOUBLE PRECISION,
    "rewardRisk" DOUBLE PRECISION,
    "agreement" DOUBLE PRECISION,
    "note" TEXT NOT NULL,
    "source" TEXT NOT NULL,
    "computedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "SetupTarget_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
-- Also the idempotency guarantee: the job upserts onto this key, so a rerun replaces a
-- method's range rather than adding a second one.
CREATE UNIQUE INDEX "SetupTarget_setupId_method_key" ON "SetupTarget"("setupId", "method");

-- AddForeignKey
-- Cascade, because a target has no meaning without the setup it was measured for.
ALTER TABLE "SetupTarget" ADD CONSTRAINT "SetupTarget_setupId_fkey"
    FOREIGN KEY ("setupId") REFERENCES "AssetSetup"("id") ON DELETE CASCADE ON UPDATE CASCADE;
