-- Four engines the architecture asks for that this schema had no way to express.
--
--  1. Story lineage. The hard prohibition is "do not treat one original report plus twenty
--     copies as twenty-one independent confirmations", and until now this code did exactly
--     that: the catalyst flag counted News rows, and deduping by url cannot see syndication
--     because twenty outlets genuinely have twenty urls. News.lineageId groups items that
--     carry the same story and NewsLineage is the story itself, so any count meant to measure
--     information counts stories instead of copies.
--
--  2. Robust change detection on HumanSignal. A ratio against a mean is dragged around by the
--     one busy day inside the baseline, which is the kind of day a news feed reliably
--     produces. (x - median) / (1.4826 * MAD) is not, and separating spike from persistent
--     change distinguishes a loud afternoon from a fortnight of heavier coverage.
--
--  3. SourceReliability. A Beta posterior per source and question, learned from measured
--     outcomes rather than declared in a config file. The prior exists so a source with two
--     observations cannot look perfect.
--
--  4. Coverage and Calibration. The first measures what the system cannot currently see,
--     because a dead feed and a quiet week are indistinguishable in the data and only one of
--     them is a finding. The second measures whether the confidence grades deserve belief,
--     which until it is measured is the one claim on the site resting on nothing.
--
-- All additive. Nothing already stored changes meaning.

-- AlterTable
ALTER TABLE "News" ADD COLUMN     "lineageId" TEXT,
ADD COLUMN     "isOriginal" BOOLEAN NOT NULL DEFAULT false;

-- AlterTable
ALTER TABLE "HumanSignal" ADD COLUMN     "recentStories" INTEGER NOT NULL DEFAULT 0,
ADD COLUMN     "baselineStoryDaily" DOUBLE PRECISION,
ADD COLUMN     "robustZ" DOUBLE PRECISION,
ADD COLUMN     "changeKind" TEXT NOT NULL DEFAULT 'none';

-- CreateTable
CREATE TABLE "NewsLineage" (
    "id" TEXT NOT NULL DEFAULT gen_random_uuid()::text,
    "targetRef" TEXT NOT NULL,
    "firstSeen" TIMESTAMP(3) NOT NULL,
    "lastSeen" TIMESTAMP(3) NOT NULL,
    "items" INTEGER NOT NULL,
    "publishers" INTEGER NOT NULL,
    "headline" TEXT NOT NULL,
    "rule" TEXT NOT NULL,
    "computedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "NewsLineage_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "SourceReliability" (
    "id" TEXT NOT NULL DEFAULT gen_random_uuid()::text,
    "source" TEXT NOT NULL,
    "eventClass" TEXT NOT NULL,
    "alpha" DOUBLE PRECISION NOT NULL DEFAULT 2,
    "beta" DOUBLE PRECISION NOT NULL DEFAULT 2,
    "observations" INTEGER NOT NULL DEFAULT 0,
    "successes" INTEGER NOT NULL DEFAULT 0,
    "expected" DOUBLE PRECISION,
    "criterion" TEXT NOT NULL,
    "updatedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "SourceReliability_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "Coverage" (
    "id" TEXT NOT NULL DEFAULT gen_random_uuid()::text,
    "source" TEXT NOT NULL,
    "expectedIntervalHours" DOUBLE PRECISION NOT NULL,
    "actualGapHours" DOUBLE PRECISION NOT NULL,
    "gapRatio" DOUBLE PRECISION NOT NULL,
    "criticality" DOUBLE PRECISION NOT NULL,
    "missRisk" DOUBLE PRECISION NOT NULL,
    "status" TEXT NOT NULL,
    "rows" INTEGER NOT NULL,
    "newest" TIMESTAMP(3),
    "note" TEXT,
    "computedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "Coverage_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "Calibration" (
    "id" TEXT NOT NULL DEFAULT gen_random_uuid()::text,
    "population" TEXT NOT NULL,
    "horizonDays" INTEGER NOT NULL,
    "bucket" TEXT NOT NULL,
    "predicted" DOUBLE PRECISION NOT NULL,
    "actual" DOUBLE PRECISION,
    "n" INTEGER NOT NULL,
    "brier" DOUBLE PRECISION,
    "logLoss" DOUBLE PRECISION,
    "note" TEXT,
    "computedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "Calibration_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE INDEX "News_lineageId_idx" ON "News"("lineageId");
CREATE INDEX "NewsLineage_targetRef_lastSeen_idx" ON "NewsLineage"("targetRef", "lastSeen");
CREATE UNIQUE INDEX "SourceReliability_source_eventClass_key"
    ON "SourceReliability"("source", "eventClass");
CREATE UNIQUE INDEX "Coverage_source_computedAt_key" ON "Coverage"("source", "computedAt");
CREATE INDEX "Coverage_status_computedAt_idx" ON "Coverage"("status", "computedAt");
CREATE UNIQUE INDEX "Calibration_population_horizonDays_bucket_computedAt_key"
    ON "Calibration"("population", "horizonDays", "bucket", "computedAt");
CREATE INDEX "Calibration_population_computedAt_idx" ON "Calibration"("population", "computedAt");
