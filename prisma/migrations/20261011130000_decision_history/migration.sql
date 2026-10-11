-- Append-only decision history and call outcomes (brain.md rule 95).
--
-- "DecisionLog" is unique on (assetId, periodEnd) and every pass of the decision job on a day rewrote that
-- day's row: 2026-10-10 carries the computedAt of eight separate passes, and 55 LONG and 12 SHORT calls
-- made at 20:15 survive nowhere after the 23:14 pass turned them into WAIT. "DecisionLog" stays as the
-- current call per day; every run is now recorded once, with its calls, and never rewritten.
-- "CallOutcome" is the evaluation of one exact call, bound by its id: the directional verdict and the
-- simulated trade side by side, final once the call's window has closed.

CREATE TABLE "DecisionRun" (
    "id" TEXT NOT NULL,
    "periodEnd" DATE NOT NULL,
    "pass" TEXT NOT NULL,
    "status" TEXT NOT NULL DEFAULT 'running',
    "startedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "finishedAt" TIMESTAMP(3),
    "commit" TEXT,
    "trigger" TEXT,
    "servedFrom" TEXT,
    "fingerprint" TEXT,
    "sessions" JSONB,
    "sourceHealth" JSONB,
    "assets" INTEGER NOT NULL DEFAULT 0,
    "written" INTEGER NOT NULL DEFAULT 0,
    "published" INTEGER NOT NULL DEFAULT 0,
    "note" TEXT,
    CONSTRAINT "DecisionRun_pkey" PRIMARY KEY ("id")
);
CREATE INDEX "DecisionRun_periodEnd_startedAt_idx" ON "DecisionRun"("periodEnd", "startedAt");

CREATE TABLE "DecisionCall" (
    "id" TEXT NOT NULL DEFAULT gen_random_uuid()::text,
    "runId" TEXT NOT NULL,
    "assetId" TEXT NOT NULL,
    "symbol" TEXT NOT NULL,
    "market" TEXT NOT NULL,
    "periodEnd" DATE NOT NULL,
    "baseSession" DATE,
    "baseClose" DOUBLE PRECISION,
    "action" TEXT NOT NULL,
    "gate" TEXT NOT NULL,
    "confidence" TEXT NOT NULL,
    "entryLow" DOUBLE PRECISION,
    "entryHigh" DOUBLE PRECISION,
    "stop" DOUBLE PRECISION,
    "target" DOUBLE PRECISION,
    "rewardRisk" DOUBLE PRECISION,
    "atr14" DOUBLE PRECISION,
    "published" BOOLEAN NOT NULL DEFAULT false,
    "gateReasons" TEXT,
    "execution" TEXT,
    "horizon" TEXT,
    "validFrom" DATE,
    "validUntil" DATE,
    "legs" TEXT,
    "intent" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "DecisionCall_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "DecisionCall_runId_fkey" FOREIGN KEY ("runId") REFERENCES "DecisionRun"("id") ON DELETE RESTRICT ON UPDATE RESTRICT
);
CREATE UNIQUE INDEX "DecisionCall_runId_assetId_key" ON "DecisionCall"("runId", "assetId");
CREATE INDEX "DecisionCall_assetId_periodEnd_idx" ON "DecisionCall"("assetId", "periodEnd");
CREATE INDEX "DecisionCall_periodEnd_published_idx" ON "DecisionCall"("periodEnd", "published");

CREATE TABLE "CallOutcome" (
    "callId" TEXT NOT NULL,
    "evaluatedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "final" BOOLEAN NOT NULL DEFAULT false,
    "direction" TEXT NOT NULL,
    "move5Pct" DOUBLE PRECISION,
    "trade" TEXT NOT NULL,
    "fillOn" DATE,
    "fillPrice" DOUBLE PRECISION,
    "exitOn" DATE,
    "exitPrice" DOUBLE PRECISION,
    "grossR" DOUBLE PRECISION,
    "gapThrough" BOOLEAN NOT NULL DEFAULT false,
    "sessions" INTEGER NOT NULL DEFAULT 0,
    "note" TEXT,
    CONSTRAINT "CallOutcome_pkey" PRIMARY KEY ("callId"),
    CONSTRAINT "CallOutcome_callId_fkey" FOREIGN KEY ("callId") REFERENCES "DecisionCall"("id") ON DELETE RESTRICT ON UPDATE RESTRICT
);
CREATE INDEX "CallOutcome_trade_idx" ON "CallOutcome"("trade");

-- Immutability, enforced by the database rather than by the job's good behaviour.
--   DecisionCall: never updated or removed.
--   DecisionRun:  may change only while it is still running (to record how it finished); never removed.
--   CallOutcome:  may change only while it is not final; never removed.
CREATE FUNCTION nbt_refuse_change() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION '% on "%" refused: decision history is append-only (brain.md rule 95)', TG_OP, TG_TABLE_NAME;
END;
$$;

CREATE FUNCTION nbt_run_finish_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF OLD."status" <> 'running' THEN
    RAISE EXCEPTION 'run % is %, and a finished run is not rewritten (brain.md rule 95)', OLD."id", OLD."status";
  END IF;
  IF NEW."id" <> OLD."id" OR NEW."periodEnd" <> OLD."periodEnd" OR NEW."pass" <> OLD."pass"
     OR NEW."startedAt" <> OLD."startedAt" OR NEW."fingerprint" IS DISTINCT FROM OLD."fingerprint" THEN
    RAISE EXCEPTION 'a run''s identity is not rewritten (brain.md rule 95)';
  END IF;
  RETURN NEW;
END;
$$;

CREATE FUNCTION nbt_outcome_until_final() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF OLD."final" THEN
    RAISE EXCEPTION 'the outcome of call % is final and is not rewritten (brain.md rule 95)', OLD."callId";
  END IF;
  RETURN NEW;
END;
$$;

CREATE TRIGGER "DecisionCall_append_only" BEFORE UPDATE OR DELETE ON "DecisionCall"
  FOR EACH ROW EXECUTE FUNCTION nbt_refuse_change();
CREATE TRIGGER "DecisionRun_finish_only" BEFORE UPDATE ON "DecisionRun"
  FOR EACH ROW EXECUTE FUNCTION nbt_run_finish_only();
CREATE TRIGGER "DecisionRun_kept" BEFORE DELETE ON "DecisionRun"
  FOR EACH ROW EXECUTE FUNCTION nbt_refuse_change();
CREATE TRIGGER "CallOutcome_until_final" BEFORE UPDATE ON "CallOutcome"
  FOR EACH ROW EXECUTE FUNCTION nbt_outcome_until_final();
CREATE TRIGGER "CallOutcome_kept" BEFORE DELETE ON "CallOutcome"
  FOR EACH ROW EXECUTE FUNCTION nbt_refuse_change();
