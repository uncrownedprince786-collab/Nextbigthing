-- Four additions. All additive, nothing already stored changes meaning.
--
--  1. open, high and low on PriceSnapshot. Both sources published these from the start and
--     the jobs discarded them, which put the day's range out of reach: with only a close,
--     "where did it finish inside the day" and "how wide was the day" cannot be asked at
--     all. Nullable on purpose — a row written before today keeps its blank rather than
--     being back-filled from the close, which would read as a day that never moved. The
--     Yahoo job refetches from 2019 on every run, so US history fills on the next one.
--
--  2. AssetAnalog: what measurably followed the past days that most resembled the latest
--     day. Count and spread are stored beside the average because the same setup appears in
--     the sample with both outcomes, and an average on its own hides that.
--
--  3. scheduled, notes and EventLink on the event tables. EventImpact ties an event to an
--     asset by measuring a move after it, so it cannot exist before the event does. This is
--     the forward half, and it is what lets a dated item that has not happened yet appear
--     next to the assets it concerns.
--
--  4. 1 and 5 day horizons on SignalLog. A catalyst is short-horizon by nature and measuring
--     it only at 30 days answers a question nobody asked about it.

-- AlterTable
ALTER TABLE "PriceSnapshot" ADD COLUMN     "open" DOUBLE PRECISION,
ADD COLUMN     "high" DOUBLE PRECISION,
ADD COLUMN     "low" DOUBLE PRECISION;

-- AlterTable
ALTER TABLE "Event" ADD COLUMN     "notes" TEXT,
ADD COLUMN     "scheduled" BOOLEAN NOT NULL DEFAULT false;

-- AlterTable
ALTER TABLE "SignalLog" ADD COLUMN     "move1Pct" DOUBLE PRECISION,
ADD COLUMN     "measured1On" DATE,
ADD COLUMN     "move5Pct" DOUBLE PRECISION,
ADD COLUMN     "measured5On" DATE;

-- CreateTable
CREATE TABLE "AssetAnalog" (
    "id" TEXT NOT NULL DEFAULT gen_random_uuid()::text,
    "assetId" TEXT NOT NULL,
    "periodEnd" DATE NOT NULL,
    "horizonDays" INTEGER NOT NULL,
    "dayReturnPct" DOUBLE PRECISION NOT NULL,
    "volumeRatio" DOUBLE PRECISION,
    "fiveDayPct" DOUBLE PRECISION,
    "toleranceNote" TEXT NOT NULL,
    "matches" INTEGER NOT NULL,
    "positive" INTEGER NOT NULL,
    "meanPct" DOUBLE PRECISION,
    "medianPct" DOUBLE PRECISION,
    "minPct" DOUBLE PRECISION,
    "maxPct" DOUBLE PRECISION,
    "confidence" "Confidence" NOT NULL DEFAULT 'none',
    "confidenceNote" TEXT,
    "source" TEXT NOT NULL,
    "computedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "AssetAnalog_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "EventLink" (
    "id" TEXT NOT NULL DEFAULT gen_random_uuid()::text,
    "eventId" TEXT NOT NULL,
    "assetId" TEXT,
    "productId" TEXT,
    "relation" TEXT NOT NULL,
    "targetRef" TEXT NOT NULL,

    CONSTRAINT "EventLink_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "AssetAnalog_assetId_periodEnd_horizonDays_key"
    ON "AssetAnalog"("assetId", "periodEnd", "horizonDays");
CREATE INDEX "AssetAnalog_assetId_periodEnd_idx" ON "AssetAnalog"("assetId", "periodEnd");

CREATE UNIQUE INDEX "EventLink_eventId_targetRef_key" ON "EventLink"("eventId", "targetRef");
CREATE INDEX "EventLink_assetId_idx" ON "EventLink"("assetId");
CREATE INDEX "EventLink_productId_idx" ON "EventLink"("productId");

CREATE INDEX "Event_scheduled_date_idx" ON "Event"("scheduled", "date");

-- AddForeignKey
ALTER TABLE "AssetAnalog" ADD CONSTRAINT "AssetAnalog_assetId_fkey"
    FOREIGN KEY ("assetId") REFERENCES "Asset"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "EventLink" ADD CONSTRAINT "EventLink_eventId_fkey"
    FOREIGN KEY ("eventId") REFERENCES "Event"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "EventLink" ADD CONSTRAINT "EventLink_assetId_fkey"
    FOREIGN KEY ("assetId") REFERENCES "Asset"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "EventLink" ADD CONSTRAINT "EventLink_productId_fkey"
    FOREIGN KEY ("productId") REFERENCES "Product"("id") ON DELETE CASCADE ON UPDATE CASCADE;
