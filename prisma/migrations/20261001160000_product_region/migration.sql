-- Where attention for a product sits geographically, from Google Trends' own regional
-- breakdown. One table, because the three resolutions differ only by what was asked for:
-- countries worldwide, and states or provinces inside one country.
--
-- City resolution is absent by verification, not by omission. Asked for directly, Trends
-- returned an empty frame for a term that has 51 US states of data, so no city rows exist
-- and the UI states that free sources do not publish it.
--
-- The unique key includes geo because a value only means something relative to the list it
-- came from: "United States 100" among countries and "Wyoming 100" among US states are both
-- a 100 and they are not the same measurement.

-- CreateTable
CREATE TABLE "ProductRegion" (
    "id" TEXT NOT NULL DEFAULT gen_random_uuid()::text,
    "productId" TEXT NOT NULL,
    "scope" TEXT NOT NULL,
    "geo" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "value" DOUBLE PRECISION NOT NULL,
    "rank" INTEGER NOT NULL,
    "periodEnd" DATE NOT NULL,
    "timeframe" TEXT NOT NULL,
    "source" TEXT NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "ProductRegion_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "ProductRegion_productId_scope_geo_name_periodEnd_key"
    ON "ProductRegion"("productId", "scope", "geo", "name", "periodEnd");
CREATE INDEX "ProductRegion_productId_periodEnd_idx"
    ON "ProductRegion"("productId", "periodEnd");
CREATE INDEX "ProductRegion_scope_geo_periodEnd_idx"
    ON "ProductRegion"("scope", "geo", "periodEnd");

-- AddForeignKey
ALTER TABLE "ProductRegion" ADD CONSTRAINT "ProductRegion_productId_fkey"
    FOREIGN KEY ("productId") REFERENCES "Product"("id") ON DELETE CASCADE ON UPDATE CASCADE;
