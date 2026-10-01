-- Thesis memory, move attribution, and a bounded walk over the edges already stored.
--
-- Three gaps, one migration, because all three read rows that already exist and none of them
-- adds a source.
--
-- AssetThesis / ThesisCheck. AssetSetup is honest about today and silent about yesterday: a
-- buy read written two weeks ago on conditions that have since reversed looked identical to
-- one written this morning. A thesis is the run of consecutive reads on which one directional
-- state was held, and the opening day's conditions are copied onto the row rather than
-- re-derived. Copied, because recomputing them from today's data would answer "what would we
-- have said then, knowing what we know now", which is the one question a frozen reason exists
-- to prevent. ThesisCheck is separate because the thesis row is updated and a check never is:
-- the sequence of checks is the history of a reason decaying, not a status showing its last
-- value.
--
-- MoveAttribution. Three competing accounts of the same move that are exclusive by
-- construction rather than by argument: total = market + sector + specific. It is co-movement
-- and says so; the leading component is what the move is most shared with, which is not a
-- claim about cause. No probability is attached, because a likelihood ratio needs a measured
-- P(E|H) and no outcome row in this database has matured. sectorPct and specificPct are
-- nullable together on purpose: below three industry peers the remainder is left unsplit
-- rather than credited to the asset.
--
-- GraphRelevance. The edges existed and nothing ever walked them. What travels is a reason to
-- look, bounded at two hops, with hub-sized edge groups skipped and every edge divided by the
-- size of the group it came from. The path is stored in words, because a score without its
-- chain is the unsupported chain this project exists not to produce.

-- CreateTable
CREATE TABLE "AssetThesis" (
    "id" TEXT NOT NULL DEFAULT gen_random_uuid()::text,
    "assetId" TEXT NOT NULL,
    "horizon" TEXT NOT NULL,
    "direction" TEXT NOT NULL,
    "openedOn" DATE NOT NULL,
    "openHeadline" TEXT NOT NULL,
    "openConditions" TEXT NOT NULL,
    "openClose" DOUBLE PRECISION,
    "invalidateLevel" DOUBLE PRECISION,
    "entryLevel" DOUBLE PRECISION,
    "status" TEXT NOT NULL,
    "reason" TEXT NOT NULL,
    "changed" TEXT NOT NULL,
    "held" TEXT NOT NULL,
    "asOf" DATE NOT NULL,
    "lastClose" DOUBLE PRECISION,
    "changePctSinceOpen" DOUBLE PRECISION,
    "sessionsSince" INTEGER NOT NULL DEFAULT 0,
    "confidence" "Confidence" NOT NULL DEFAULT 'none',
    "confidenceNote" TEXT,
    "source" TEXT NOT NULL,
    "computedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "AssetThesis_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "ThesisCheck" (
    "id" TEXT NOT NULL DEFAULT gen_random_uuid()::text,
    "thesisId" TEXT NOT NULL,
    "asOf" DATE NOT NULL,
    "status" TEXT NOT NULL,
    "reason" TEXT NOT NULL,
    "changed" TEXT NOT NULL,
    "held" TEXT NOT NULL,
    "close" DOUBLE PRECISION,
    "changePctSinceOpen" DOUBLE PRECISION,
    "source" TEXT NOT NULL,
    "computedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "ThesisCheck_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "MoveAttribution" (
    "id" TEXT NOT NULL DEFAULT gen_random_uuid()::text,
    "assetId" TEXT NOT NULL,
    "periodEnd" DATE NOT NULL,
    "windowDays" INTEGER NOT NULL,
    "totalPct" DOUBLE PRECISION NOT NULL,
    "marketPct" DOUBLE PRECISION NOT NULL,
    "sectorPct" DOUBLE PRECISION,
    "specificPct" DOUBLE PRECISION,
    "marketShare" DOUBLE PRECISION,
    "sectorShare" DOUBLE PRECISION,
    "specificShare" DOUBLE PRECISION,
    "leader" TEXT,
    "leaderMargin" DOUBLE PRECISION,
    "peers" INTEGER NOT NULL,
    "groupSize" INTEGER NOT NULL,
    "headline" TEXT NOT NULL,
    "confidence" "Confidence" NOT NULL DEFAULT 'none',
    "confidenceNote" TEXT,
    "method" TEXT NOT NULL,
    "source" TEXT NOT NULL,
    "computedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "MoveAttribution_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "GraphRelevance" (
    "id" TEXT NOT NULL DEFAULT gen_random_uuid()::text,
    "assetId" TEXT NOT NULL,
    "periodEnd" DATE NOT NULL,
    "originKind" TEXT NOT NULL,
    "originId" TEXT NOT NULL,
    "score" DOUBLE PRECISION NOT NULL,
    "hops" INTEGER NOT NULL,
    "edgeKind" TEXT NOT NULL,
    "path" TEXT NOT NULL,
    "note" TEXT NOT NULL,
    "source" TEXT NOT NULL,
    "computedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "GraphRelevance_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "AssetThesis_assetId_horizon_openedOn_key"
    ON "AssetThesis"("assetId", "horizon", "openedOn");
CREATE INDEX "AssetThesis_status_asOf_idx" ON "AssetThesis"("status", "asOf");
CREATE UNIQUE INDEX "ThesisCheck_thesisId_asOf_key" ON "ThesisCheck"("thesisId", "asOf");
CREATE INDEX "ThesisCheck_asOf_idx" ON "ThesisCheck"("asOf");
CREATE UNIQUE INDEX "MoveAttribution_assetId_periodEnd_windowDays_key"
    ON "MoveAttribution"("assetId", "periodEnd", "windowDays");
CREATE INDEX "MoveAttribution_periodEnd_leader_idx" ON "MoveAttribution"("periodEnd", "leader");
CREATE UNIQUE INDEX "GraphRelevance_assetId_periodEnd_originKind_originId_key"
    ON "GraphRelevance"("assetId", "periodEnd", "originKind", "originId");
CREATE INDEX "GraphRelevance_periodEnd_score_idx" ON "GraphRelevance"("periodEnd", "score");

-- AddForeignKey
ALTER TABLE "AssetThesis" ADD CONSTRAINT "AssetThesis_assetId_fkey"
    FOREIGN KEY ("assetId") REFERENCES "Asset"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "ThesisCheck" ADD CONSTRAINT "ThesisCheck_thesisId_fkey"
    FOREIGN KEY ("thesisId") REFERENCES "AssetThesis"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "MoveAttribution" ADD CONSTRAINT "MoveAttribution_assetId_fkey"
    FOREIGN KEY ("assetId") REFERENCES "Asset"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "GraphRelevance" ADD CONSTRAINT "GraphRelevance_assetId_fkey"
    FOREIGN KEY ("assetId") REFERENCES "Asset"("id") ON DELETE CASCADE ON UPDATE CASCADE;
