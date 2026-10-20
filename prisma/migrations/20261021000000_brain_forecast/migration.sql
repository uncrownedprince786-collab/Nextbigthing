-- Short-horizon forecasts, and what actually happened after them.
--
-- WHY NOT ShadowPrediction. That table is keyed on a session date and a horizon counted in
-- sessions, which is the right shape for a 20-session call and cannot express this one: a
-- five-minute forecast made at 14:35 UTC and another made at 14:40 are two different claims about
-- two different windows on the same calendar day, and `asOf DATE` collapses them into one row.
-- Widening it would change the identity of 566 existing rows and the scorer that grades them. So
-- this is a second pair of tables with minute precision, and the two never merge: a reader that
-- counts both would count two different experiments as one.
--
-- WHY A ROW PER BAR, NOT PER REQUEST. `asOf` is the close time of the newest bar the features were
-- read from, so every request inside the same five-minute bar produces the *same* forecast, and the
-- unique key turns the second and later writes into a no-op. The row that is stored is therefore
-- exactly the row the reader was shown, and the table grows with bars elapsed rather than with
-- traffic.
--
-- WHY THE INPUTS ARE STORED. `features`, `referencePrice`, `inputVersion`, `venue`, `barCount` and
-- `imputed` are what makes a graded forecast auditable rather than merely scored: without them a
-- wrong call cannot be told apart from a call made on a degraded window, which is the distinction
-- the whole data gate exists to draw.
CREATE TABLE "BrainForecast" (
    "id" TEXT NOT NULL DEFAULT gen_random_uuid()::text,
    "assetId" TEXT NOT NULL,
    "symbol" TEXT NOT NULL,
    "market" TEXT NOT NULL,

    -- The horizon as the reader chose it: the key, and the same reach in minutes, which is what
    -- `maturesAt` is computed from and what the scorer grades against.
    "horizonKey" TEXT NOT NULL,
    "horizonMinutes" INTEGER NOT NULL,
    -- Which corpus answered: '5m' or '4h'. Part of the horizon's identity, so a daily model can
    -- never be found serving a five-minute row.
    "interval" TEXT NOT NULL,

    -- The close time of the newest bar read. The decision instant, not the write time.
    "asOf" TIMESTAMP(3) NOT NULL,
    "maturesAt" TIMESTAMP(3) NOT NULL,

    "direction" TEXT NOT NULL,
    "probUp" DOUBLE PRECISION NOT NULL,
    "confidence" TEXT NOT NULL,
    "referencePrice" DOUBLE PRECISION NOT NULL,

    "modelVersion" TEXT NOT NULL,
    "modelSha256" TEXT NOT NULL,
    "featureSchema" TEXT NOT NULL,
    "features" JSONB,

    -- What the inputs were worth. 'ok' when every feature was observed, 'degraded' when one was
    -- imputed because the venue does not publish it; `imputed` names them. A degraded forecast is
    -- still a forecast and is still graded -- it is marked, not hidden.
    "quality" TEXT NOT NULL,
    "imputed" JSONB,
    "venue" TEXT NOT NULL,
    "patchedFrom" TEXT,
    "barCount" INTEGER NOT NULL,
    "inputAgeMs" INTEGER NOT NULL,

    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "BrainForecast_pkey" PRIMARY KEY ("id")
);

-- The identity of a forecast event: this model's bytes, this asset, this horizon, this bar. A
-- retry is the same event and collides; two bars are two events and do not.
CREATE UNIQUE INDEX "BrainForecast_identity_key"
    ON "BrainForecast"("modelVersion", "modelSha256", "assetId", "horizonKey", "asOf");
CREATE INDEX "BrainForecast_assetId_horizonKey_asOf_idx"
    ON "BrainForecast"("assetId", "horizonKey", "asOf" DESC);
CREATE INDEX "BrainForecast_maturesAt_idx" ON "BrainForecast"("maturesAt");
CREATE INDEX "BrainForecast_symbol_asOf_idx" ON "BrainForecast"("symbol", "asOf" DESC);

ALTER TABLE "BrainForecast" ADD CONSTRAINT "BrainForecast_assetId_fkey"
    FOREIGN KEY ("assetId") REFERENCES "Asset"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- The observation, separate from the claim, so grading never edits what was claimed.
--
-- One final result per forecast, enforced by a unique index on forecastId: a forecast matures
-- exactly once, and rerunning the scorer is idempotent rather than additive. There is no interim
-- mark here -- unlike a 20-session call there is nothing useful to say about a five-minute window
-- halfway through it.
CREATE TABLE "BrainForecastOutcome" (
    "id" TEXT NOT NULL DEFAULT gen_random_uuid()::text,
    "forecastId" TEXT NOT NULL,
    "observedPrice" DOUBLE PRECISION NOT NULL,
    -- The close time of the bar the observed price came from, which is at or after `maturesAt`.
    "observedAt" TIMESTAMP(3) NOT NULL,
    "realisedPct" DOUBLE PRECISION NOT NULL,
    "actual" TEXT NOT NULL,
    "correct" BOOLEAN NOT NULL,
    -- How far past maturity the observation was taken, so a late grading is visible rather than
    -- silently treated as an on-time one.
    "latenessMs" INTEGER NOT NULL,
    "source" TEXT NOT NULL,
    "scorerVersion" TEXT NOT NULL,
    "note" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "BrainForecastOutcome_pkey" PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX "BrainForecastOutcome_forecastId_key"
    ON "BrainForecastOutcome"("forecastId");
CREATE INDEX "BrainForecastOutcome_observedAt_idx" ON "BrainForecastOutcome"("observedAt");

ALTER TABLE "BrainForecastOutcome" ADD CONSTRAINT "BrainForecastOutcome_forecastId_fkey"
    FOREIGN KEY ("forecastId") REFERENCES "BrainForecast"("id") ON DELETE RESTRICT ON UPDATE RESTRICT;

-- The same backstop every other table carries (migration 20261019230000_rls_backstop): enabled
-- with no policy, so a grant that reaches `anon` by accident still returns no rows. The backend
-- connects as `postgres`, which bypasses RLS, so nothing in the application changes.
ALTER TABLE "BrainForecast" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "BrainForecastOutcome" ENABLE ROW LEVEL SECURITY;
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nbt_phase2_reader_20261013') THEN
    EXECUTE 'CREATE POLICY "nbt_phase2_reader_20261013_select" ON public."BrainForecast" FOR SELECT TO nbt_phase2_reader_20261013 USING (true)';
    EXECUTE 'CREATE POLICY "nbt_phase2_reader_20261013_select" ON public."BrainForecastOutcome" FOR SELECT TO nbt_phase2_reader_20261013 USING (true)';
  END IF;
END $$;
