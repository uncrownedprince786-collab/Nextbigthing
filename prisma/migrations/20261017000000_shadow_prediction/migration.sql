-- Shadow predictions: output from a model candidate that is NOT approved for production,
-- recorded so its outcome can be measured after the horizon matures.
--
-- Its own table on purpose. `DecisionCall` holds the rule engine's published calls, and adding a
-- nullable `modelVersion` there would make it structurally possible for an unapproved candidate's
-- output to reach a published path through a query someone forgot to filter. A separate table
-- makes that impossible rather than merely discouraged.
--
-- `approved` is false by default and no code path sets it true. `imputed` is the column that
-- stops a prediction built from imputed averages looking identical to one built from observed
-- evidence: at training an absent feature takes the training mean, which is measured and fine,
-- and at inference the same rule silently turns a failed macro refresh into "an average day".
--
-- Every outcome column is nullable, and null means "the horizon has not matured", never "no
-- move" -- the same rule the accuracy log and the analog pool already follow.
CREATE TABLE "ShadowPrediction" (
    "id" TEXT NOT NULL DEFAULT gen_random_uuid()::text,
    "asOf" DATE NOT NULL,
    "assetId" TEXT NOT NULL,
    "symbol" TEXT NOT NULL,
    "market" TEXT NOT NULL,
    "predicted" TEXT NOT NULL,
    "scores" JSONB,
    "modelVersion" TEXT NOT NULL,
    "modelSha256" TEXT NOT NULL,
    "featureSchema" TEXT NOT NULL,
    "datasetVersion" TEXT,
    "approved" BOOLEAN NOT NULL DEFAULT false,
    "quality" TEXT NOT NULL,
    "imputed" JSONB,
    "imputedCount" INTEGER NOT NULL DEFAULT 0,
    "missingCritical" JSONB,
    "contextStatus" JSONB,
    "macroAsOf" DATE,
    "macroAgeDays" INTEGER,
    "horizonSessions" INTEGER NOT NULL DEFAULT 20,
    "maturesAfter" DATE,
    "outcomeLabel" TEXT,
    "outcomeFwd" DOUBLE PRECISION,
    "outcomeAt" TIMESTAMP(3),
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "runId" TEXT,
    "commit" TEXT,
    CONSTRAINT "ShadowPrediction_pkey" PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX "ShadowPrediction_modelVersion_assetId_asOf_key"
    ON "ShadowPrediction"("modelVersion", "assetId", "asOf");
CREATE INDEX "ShadowPrediction_asOf_modelVersion_idx"
    ON "ShadowPrediction"("asOf", "modelVersion");
CREATE INDEX "ShadowPrediction_maturesAfter_outcomeLabel_idx"
    ON "ShadowPrediction"("maturesAfter", "outcomeLabel");
