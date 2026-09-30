-- Three additions, none of which change an existing number.
--
--  1. A market and a currency on Industry, and a currency on Asset. Ranking only ever
--     happens inside one industry, so nothing here starts comparing a rupee with a dollar;
--     the columns exist so a size figure can be labelled with the unit it is actually in.
--     Everything already stored is a US listing quoted in dollars, hence the defaults.
--  2. Event and EventImpact, for measuring what moved in the window after a dated event.
--  3. MarketplaceItem, for public marketplace rankings, kept out of the demand score.

-- AlterEnum
ALTER TYPE "AnalysisKind" ADD VALUE 'eventImpact';

-- AlterTable
ALTER TABLE "Industry" ADD COLUMN     "market" TEXT NOT NULL DEFAULT 'US',
ADD COLUMN     "currency" TEXT NOT NULL DEFAULT 'USD';

-- AlterTable
ALTER TABLE "Asset" ADD COLUMN     "currency" TEXT NOT NULL DEFAULT 'USD';

-- AlterTable
ALTER TABLE "Analysis" ADD COLUMN     "eventId" TEXT;

-- CreateTable
CREATE TABLE "Event" (
    "id" TEXT NOT NULL DEFAULT gen_random_uuid()::text,
    "slug" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "summary" TEXT NOT NULL,
    "date" DATE NOT NULL,
    "category" TEXT NOT NULL,
    "source" TEXT NOT NULL,
    "sourceUrl" TEXT NOT NULL,
    "sort" INTEGER NOT NULL DEFAULT 0,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "Event_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "EventImpact" (
    "id" TEXT NOT NULL DEFAULT gen_random_uuid()::text,
    "eventId" TEXT NOT NULL,
    "assetId" TEXT NOT NULL,
    "windowDays" INTEGER NOT NULL,
    "startDate" DATE NOT NULL,
    "startClose" DOUBLE PRECISION NOT NULL,
    "endDate" DATE NOT NULL,
    "endClose" DOUBLE PRECISION NOT NULL,
    "changePct" DOUBLE PRECISION NOT NULL,
    "volumeChangePct" DOUBLE PRECISION,
    "rank" INTEGER NOT NULL,
    "confidence" "Confidence" NOT NULL DEFAULT 'none',
    "confidenceNote" TEXT,
    "source" TEXT NOT NULL,

    CONSTRAINT "EventImpact_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "MarketplaceItem" (
    "id" TEXT NOT NULL DEFAULT gen_random_uuid()::text,
    "marketplace" TEXT NOT NULL,
    "categorySlug" TEXT NOT NULL,
    "categoryName" TEXT NOT NULL,
    "rank" INTEGER NOT NULL,
    "title" TEXT NOT NULL,
    "url" TEXT NOT NULL,
    "itemRef" TEXT NOT NULL,
    "periodEnd" DATE NOT NULL,
    "previousRank" INTEGER,
    "source" TEXT NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "MarketplaceItem_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "Event_slug_key" ON "Event"("slug");
CREATE INDEX "Event_date_idx" ON "Event"("date");
CREATE INDEX "EventImpact_eventId_rank_idx" ON "EventImpact"("eventId", "rank");
CREATE UNIQUE INDEX "EventImpact_eventId_assetId_windowDays_key"
    ON "EventImpact"("eventId", "assetId", "windowDays");
CREATE INDEX "MarketplaceItem_categorySlug_periodEnd_idx"
    ON "MarketplaceItem"("categorySlug", "periodEnd");
CREATE INDEX "MarketplaceItem_periodEnd_idx" ON "MarketplaceItem"("periodEnd");
CREATE UNIQUE INDEX "MarketplaceItem_marketplace_categorySlug_periodEnd_itemRef_key"
    ON "MarketplaceItem"("marketplace", "categorySlug", "periodEnd", "itemRef");
CREATE INDEX "Analysis_eventId_idx" ON "Analysis"("eventId");

-- AddForeignKey
ALTER TABLE "EventImpact" ADD CONSTRAINT "EventImpact_eventId_fkey"
    FOREIGN KEY ("eventId") REFERENCES "Event"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "EventImpact" ADD CONSTRAINT "EventImpact_assetId_fkey"
    FOREIGN KEY ("assetId") REFERENCES "Asset"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "Analysis" ADD CONSTRAINT "Analysis_eventId_fkey"
    FOREIGN KEY ("eventId") REFERENCES "Event"("id") ON DELETE CASCADE ON UPDATE CASCADE;
