-- Additive extension of ShadowPrediction, and its outcomes as their own table.
--
-- Identity. The old key (modelVersion, assetId, asOf) allowed exactly one prediction per model per
-- asset per session, so two strategies could never both record a call on the same day. The new key
-- adds modelSha256 (the artifact bytes, not the version name someone may have reused), strategy,
-- timeframe and the horizon. Genuinely distinct prediction events no longer collide; a retry of the
-- same event still does, because the writer upserts ON CONFLICT against exactly this key.
-- `timeframe` is NOT NULL with a default so the unique index is total -- a nullable column would
-- let duplicate rows through, since NULL never equals NULL in a unique index.
--
-- Values given to existing rows are established by the rows themselves. strategy and timeframe
-- default to 'swing' because all 566 existing rows carry horizonSessions 20, the swing horizon of
-- the 20-session label they were made under. referencePrice, features, sources and inputCutoff stay
-- NULL for them: the exact close and feature vector a past run saw cannot be recovered from the
-- stored row without re-deriving it, and a re-derivation is not the original input. NULL means
-- "not recorded", never "no value" -- the rule the outcome columns already follow.
ALTER TABLE "ShadowPrediction" ADD COLUMN "strategy" TEXT NOT NULL DEFAULT 'swing';
ALTER TABLE "ShadowPrediction" ADD COLUMN "timeframe" TEXT NOT NULL DEFAULT 'swing';
ALTER TABLE "ShadowPrediction" ADD COLUMN "referencePrice" DOUBLE PRECISION;
ALTER TABLE "ShadowPrediction" ADD COLUMN "features" JSONB;
ALTER TABLE "ShadowPrediction" ADD COLUMN "sources" JSONB;
ALTER TABLE "ShadowPrediction" ADD COLUMN "inputCutoff" TIMESTAMP(3);

DROP INDEX "ShadowPrediction_modelVersion_assetId_asOf_key";
CREATE UNIQUE INDEX "ShadowPrediction_identity_key"
    ON "ShadowPrediction"("modelVersion", "modelSha256", "strategy", "timeframe", "assetId",
                           "asOf", "horizonSessions");
CREATE INDEX "ShadowPrediction_market_strategy_timeframe_idx"
    ON "ShadowPrediction"("market", "strategy", "timeframe");

-- A prediction is an immutable claim; an outcome is a later observation of what actually happened.
-- Its own table so scoring never edits a prediction, and so an interim mark and the final matured
-- result can both exist. `final` is false for an interim mark and true for the matured result; the
-- unique key (predictionId, observedOn, final) lets many interim marks on different sessions
-- coexist while enforcing an exactly-once final result, so rerunning the scorer is idempotent
-- rather than additive. `observedOn` is NOT NULL so that key is total.
CREATE TABLE "ShadowOutcome" (
    "id" TEXT NOT NULL DEFAULT gen_random_uuid()::text,
    "predictionId" TEXT NOT NULL,
    "final" BOOLEAN NOT NULL DEFAULT false,
    "label" TEXT,
    "fwdPct" DOUBLE PRECISION,
    "referencePrice" DOUBLE PRECISION,
    "observedPrice" DOUBLE PRECISION,
    "observedOn" DATE NOT NULL,
    "fromSession" DATE NOT NULL,
    "toSession" DATE,
    "sessionsElapsed" INTEGER,
    "horizonSessions" INTEGER NOT NULL,
    "mfe" DOUBLE PRECISION,
    "mae" DOUBLE PRECISION,
    "source" TEXT,
    "scoringRule" TEXT,
    "scorerVersion" TEXT,
    "note" TEXT,
    "observedAt" TIMESTAMP(3),
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "ShadowOutcome_pkey" PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX "ShadowOutcome_predictionId_observedOn_final_key"
    ON "ShadowOutcome"("predictionId", "observedOn", "final");
CREATE INDEX "ShadowOutcome_final_label_idx" ON "ShadowOutcome"("final", "label");
CREATE INDEX "ShadowOutcome_observedOn_idx" ON "ShadowOutcome"("observedOn");

ALTER TABLE "ShadowOutcome" ADD CONSTRAINT "ShadowOutcome_predictionId_fkey"
    FOREIGN KEY ("predictionId") REFERENCES "ShadowPrediction"("id")
    ON DELETE RESTRICT ON UPDATE RESTRICT;
