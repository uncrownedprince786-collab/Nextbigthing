-- The event lifecycle, and the before/after states that make look-ahead bias impossible.
--
-- The gap this closes: a scheduled date whose day had passed simply stayed scheduled=true
-- forever. It never became evidence, so the system could remember that an earnings report was
-- coming and never learn anything from the one that happened.
--
-- EventState is the part that matters. Once an event has passed, every other table in this
-- database holds the post-event world, so asking "what did we know before the report" by
-- querying current data silently answers with information that did not exist then. Freezing
-- the before-state at the moment of resolution is the only honest way to ask later. Rows are
-- never rewritten: a correction becomes a new row with a later computedAt, so the record of
-- what was believed at the time survives its own revisions.
--
-- discoveredAt is separate from the event date and from createdAt on purpose. How long a date
-- was known is itself evidence — a report scheduled three months out is a different thing
-- from one announced yesterday.

-- AlterTable
ALTER TABLE "Event" ADD COLUMN     "lifecycle" TEXT NOT NULL DEFAULT 'discovered',
ADD COLUMN     "discoveredAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
ADD COLUMN     "resolvedAt" TIMESTAMP(3);

-- Everything already stored is a hand-written historical event, not a discovered schedule,
-- so it starts as historical rather than pretending it was ever upcoming.
UPDATE "Event" SET lifecycle = 'historical' WHERE scheduled = false;

-- CreateTable
CREATE TABLE "EventState" (
    "id" TEXT NOT NULL DEFAULT gen_random_uuid()::text,
    "eventId" TEXT NOT NULL,
    "assetId" TEXT NOT NULL,
    "phase" TEXT NOT NULL,
    "asOf" DATE NOT NULL,
    "close" DOUBLE PRECISION,
    "volume" DOUBLE PRECISION,
    "volumeRatio" DOUBLE PRECISION,
    "trailingPct" DOUBLE PRECISION,
    "tone" TEXT,
    "stories" INTEGER,
    "catalyst" BOOLEAN,
    "setupState" TEXT,
    "changePct" DOUBLE PRECISION,
    "windowDays" INTEGER,
    "source" TEXT NOT NULL,
    "computedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "EventState_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE INDEX "Event_lifecycle_date_idx" ON "Event"("lifecycle", "date");
CREATE UNIQUE INDEX "EventState_eventId_assetId_phase_key"
    ON "EventState"("eventId", "assetId", "phase");
CREATE INDEX "EventState_assetId_asOf_idx" ON "EventState"("assetId", "asOf");

-- AddForeignKey
ALTER TABLE "EventState" ADD CONSTRAINT "EventState_eventId_fkey"
    FOREIGN KEY ("eventId") REFERENCES "Event"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "EventState" ADD CONSTRAINT "EventState_assetId_fkey"
    FOREIGN KEY ("assetId") REFERENCES "Asset"("id") ON DELETE CASCADE ON UPDATE CASCADE;
