-- The investigation engine: what was looked at when something moved, including what was absent.
--
-- The catalyst flag answers "did news arrive". This answers the question after it. A large move
-- with nothing published behind it is the ordinary case rather than the exceptional one, and a
-- system that prints nothing then has told the reader less than one that says: we checked
-- company news, the sector, the calendar, the related names and the volume, and found a sector
-- move and no company story. So `notFound` is a stored field with content in it.
--
-- InvestigationFinding.status carries three values because an absent row collapses three
-- different answers into one. `found`, `absent` (checked, genuinely none) and `unavailable`
-- (could not be checked) are distinct, and "no news" and "the news source did not answer" look
-- identical in a row count while meaning opposite things.
--
-- observedAt is separate from the computedAt on the parent on purpose. Evidence has its own
-- date, and a story published after the close cannot be evidence about that close. Only a field
-- that stores when the evidence happened can show that.
--
-- InvestigationHypothesis is four competing explanations with an honest division between them:
-- market, sector and specific are measured directly by jobs/attribution.py, are exclusive by
-- construction and sum to the move, so no inference is performed on them. The news hypothesis
-- is the one that genuinely needs evidence and also the one no arithmetic can confirm.
--
-- priorBase is a real base rate measured from the stored population — how often each component
-- has actually led across every attribution row — and not a number chosen by hand, which would
-- be the manufactured figure this project exists not to produce.
--
-- posterior is nullable and stays null, with posteriorNote always stating why. Two different
-- reasons, both recorded: for the three measured components the evidence *is* the measurement,
-- so an update would be circular; for the news hypothesis a likelihood ratio needs a measured
-- P(evidence | hypothesis) and the outcome log has no matured rows. It is a column rather than
-- an omission so it can be filled once outcomes mature, without a migration.

-- CreateTable
CREATE TABLE "Investigation" (
    "id" TEXT NOT NULL DEFAULT gen_random_uuid()::text,
    "assetId" TEXT NOT NULL,
    "periodEnd" DATE NOT NULL,
    "trigger" TEXT NOT NULL,
    "triggerDetail" TEXT NOT NULL,
    "movePct" DOUBLE PRECISION,
    "robustZ" DOUBLE PRECISION,
    "volumeRatio" DOUBLE PRECISION,
    "headline" TEXT NOT NULL,
    "found" TEXT NOT NULL,
    "notFound" TEXT NOT NULL,
    "pointsToward" TEXT NOT NULL,
    "unconfirmed" TEXT NOT NULL,
    "leading" TEXT,
    "confidence" "Confidence" NOT NULL DEFAULT 'none',
    "confidenceNote" TEXT,
    "source" TEXT NOT NULL,
    "computedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "Investigation_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "InvestigationFinding" (
    "id" TEXT NOT NULL DEFAULT gen_random_uuid()::text,
    "investigationId" TEXT NOT NULL,
    "kind" TEXT NOT NULL,
    "status" TEXT NOT NULL,
    "detail" TEXT NOT NULL,
    "sourceName" TEXT,
    "observedAt" TIMESTAMP(3),

    CONSTRAINT "InvestigationFinding_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "InvestigationHypothesis" (
    "id" TEXT NOT NULL DEFAULT gen_random_uuid()::text,
    "investigationId" TEXT NOT NULL,
    "label" TEXT NOT NULL,
    "statement" TEXT NOT NULL,
    "priorBase" DOUBLE PRECISION,
    "priorNote" TEXT,
    "magnitude" DOUBLE PRECISION,
    "supporting" TEXT NOT NULL,
    "contradicting" TEXT NOT NULL,
    "posterior" DOUBLE PRECISION,
    "posteriorNote" TEXT NOT NULL,

    CONSTRAINT "InvestigationHypothesis_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
-- One investigation per asset per day, which is also the idempotency guarantee: a rerun
-- upserts onto this key rather than appending a second search of the same move.
CREATE UNIQUE INDEX "Investigation_assetId_periodEnd_key"
    ON "Investigation"("assetId", "periodEnd");
-- For the front page question: what was investigated today, and why.
CREATE INDEX "Investigation_periodEnd_trigger_idx" ON "Investigation"("periodEnd", "trigger");
CREATE UNIQUE INDEX "InvestigationFinding_investigationId_kind_key"
    ON "InvestigationFinding"("investigationId", "kind");
CREATE UNIQUE INDEX "InvestigationHypothesis_investigationId_label_key"
    ON "InvestigationHypothesis"("investigationId", "label");

-- AddForeignKey
ALTER TABLE "Investigation" ADD CONSTRAINT "Investigation_assetId_fkey"
    FOREIGN KEY ("assetId") REFERENCES "Asset"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "InvestigationFinding" ADD CONSTRAINT "InvestigationFinding_investigationId_fkey"
    FOREIGN KEY ("investigationId") REFERENCES "Investigation"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "InvestigationHypothesis" ADD CONSTRAINT "InvestigationHypothesis_investigationId_fkey"
    FOREIGN KEY ("investigationId") REFERENCES "Investigation"("id") ON DELETE CASCADE ON UPDATE CASCADE;
