-- The macro gatekeeper's answers: one row per name per session, a veto layer over the rule table.
--
-- A new table and nothing else. It touches no existing column and needs no backfill; with the gate
-- off, which is its default, the table stays empty and every verdict is exactly what it was.
--
-- Every answer is stored, the EXECUTE ones and the fail-open fallbacks too, so the layer can be scored
-- against what followed. A table of only refusals could not say whether the refusals were right.
CREATE TABLE "MacroGate" (
  "id"        TEXT             NOT NULL DEFAULT gen_random_uuid()::text,
  "assetId"   TEXT             NOT NULL,
  "periodEnd" DATE             NOT NULL,
  "direction" TEXT             NOT NULL,
  "verdict"   TEXT             NOT NULL,
  "reason"    TEXT,
  "rationale" TEXT             NOT NULL,
  "valid"     BOOLEAN          NOT NULL,
  "fallback"  TEXT,
  "model"     TEXT             NOT NULL,
  "newsCount" INTEGER          NOT NULL,
  "createdAt" TIMESTAMP(3)     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "MacroGate_pkey" PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX "MacroGate_assetId_periodEnd_key" ON "MacroGate"("assetId", "periodEnd");
CREATE INDEX "MacroGate_periodEnd_verdict_idx" ON "MacroGate"("periodEnd", "verdict");

ALTER TABLE "MacroGate"
  ADD CONSTRAINT "MacroGate_assetId_fkey" FOREIGN KEY ("assetId") REFERENCES "Asset"("id") ON DELETE CASCADE ON UPDATE CASCADE;
