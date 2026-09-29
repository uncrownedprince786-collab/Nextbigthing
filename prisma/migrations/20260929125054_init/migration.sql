-- CreateEnum
CREATE TYPE "AssetType" AS ENUM ('stock', 'etf', 'crypto', 'commodity');

-- CreateEnum
CREATE TYPE "CapBasis" AS ENUM ('marketCap', 'fundAssets', 'none');

-- CreateEnum
CREATE TYPE "SignalSource" AS ENUM ('googleTrends', 'wikipedia', 'reddit', 'hackerNews', 'googleNews', 'market');

-- CreateEnum
CREATE TYPE "RankingBasis" AS ENUM ('size', 'sizeNow', 'totalReturn', 'rising');

-- CreateEnum
CREATE TYPE "AnalysisKind" AS ENUM ('industryShift', 'assetPosition', 'assetRising', 'forwardLook', 'productDemand', 'siteLead');

-- CreateTable
CREATE TABLE "Industry" (
    "id" TEXT NOT NULL,
    "slug" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "summary" TEXT NOT NULL,
    "sort" INTEGER NOT NULL DEFAULT 0,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "Industry_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "Asset" (
    "id" TEXT NOT NULL,
    "industryId" TEXT NOT NULL,
    "symbol" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "assetType" "AssetType" NOT NULL,
    "capBasis" "CapBasis" NOT NULL DEFAULT 'marketCap',
    "source" TEXT NOT NULL,
    "sourceRef" TEXT NOT NULL,
    "description" TEXT,
    "note" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "Asset_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "PriceSnapshot" (
    "id" TEXT NOT NULL,
    "assetId" TEXT NOT NULL,
    "date" DATE NOT NULL,
    "close" DOUBLE PRECISION NOT NULL,
    "volume" DOUBLE PRECISION,
    "marketCap" DOUBLE PRECISION,
    "source" TEXT NOT NULL,

    CONSTRAINT "PriceSnapshot_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "Ranking" (
    "id" TEXT NOT NULL,
    "industryId" TEXT NOT NULL,
    "assetId" TEXT NOT NULL,
    "basis" "RankingBasis" NOT NULL,
    "periodStart" DATE,
    "periodEnd" DATE NOT NULL,
    "rank" INTEGER NOT NULL,
    "sizeRank" INTEGER,
    "value" DOUBLE PRECISION NOT NULL,
    "source" TEXT NOT NULL,
    "note" TEXT,

    CONSTRAINT "Ranking_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "Analysis" (
    "id" TEXT NOT NULL,
    "kind" "AnalysisKind" NOT NULL,
    "industryId" TEXT,
    "assetId" TEXT,
    "productId" TEXT,
    "headline" TEXT NOT NULL,
    "body" TEXT NOT NULL,
    "dataNote" TEXT,
    "source" TEXT NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "Analysis_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "News" (
    "id" TEXT NOT NULL,
    "industryId" TEXT,
    "assetId" TEXT,
    "title" TEXT NOT NULL,
    "url" TEXT NOT NULL,
    "publisher" TEXT NOT NULL,
    "publishedAt" TIMESTAMP(3) NOT NULL,
    "source" TEXT NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "News_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "Product" (
    "id" TEXT NOT NULL,
    "slug" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "category" TEXT NOT NULL,
    "summary" TEXT NOT NULL,
    "wikiTitle" TEXT NOT NULL,
    "trendsTerm" TEXT NOT NULL,
    "subreddits" TEXT NOT NULL,
    "relatedTickers" TEXT NOT NULL,
    "status" TEXT NOT NULL DEFAULT 'unknown',
    "demandScore" DOUBLE PRECISION,
    "demandNote" TEXT,
    "computedAt" TIMESTAMP(3),
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "Product_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "ProductSignal" (
    "id" TEXT NOT NULL,
    "productId" TEXT NOT NULL,
    "source" "SignalSource" NOT NULL,
    "metric" TEXT NOT NULL,
    "value" DOUBLE PRECISION,
    "evidence" TEXT,
    "periodEnd" DATE NOT NULL,
    "note" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "ProductSignal_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "ProductAssetLink" (
    "id" TEXT NOT NULL,
    "productId" TEXT NOT NULL,
    "assetId" TEXT NOT NULL,
    "relation" TEXT NOT NULL,
    "note" TEXT,

    CONSTRAINT "ProductAssetLink_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "Industry_slug_key" ON "Industry"("slug");

-- CreateIndex
CREATE INDEX "Asset_symbol_idx" ON "Asset"("symbol");

-- CreateIndex
CREATE UNIQUE INDEX "Asset_industryId_symbol_key" ON "Asset"("industryId", "symbol");

-- CreateIndex
CREATE INDEX "PriceSnapshot_date_idx" ON "PriceSnapshot"("date");

-- CreateIndex
CREATE UNIQUE INDEX "PriceSnapshot_assetId_date_key" ON "PriceSnapshot"("assetId", "date");

-- CreateIndex
CREATE INDEX "Ranking_periodEnd_idx" ON "Ranking"("periodEnd");

-- CreateIndex
CREATE UNIQUE INDEX "Ranking_industryId_basis_periodEnd_assetId_key" ON "Ranking"("industryId", "basis", "periodEnd", "assetId");

-- CreateIndex
CREATE INDEX "Analysis_kind_idx" ON "Analysis"("kind");

-- CreateIndex
CREATE INDEX "Analysis_industryId_idx" ON "Analysis"("industryId");

-- CreateIndex
CREATE INDEX "Analysis_assetId_idx" ON "Analysis"("assetId");

-- CreateIndex
CREATE INDEX "Analysis_productId_idx" ON "Analysis"("productId");

-- CreateIndex
CREATE INDEX "News_publishedAt_idx" ON "News"("publishedAt");

-- CreateIndex
CREATE UNIQUE INDEX "News_url_key" ON "News"("url");

-- CreateIndex
CREATE UNIQUE INDEX "Product_slug_key" ON "Product"("slug");

-- CreateIndex
CREATE INDEX "ProductSignal_productId_periodEnd_idx" ON "ProductSignal"("productId", "periodEnd");

-- CreateIndex
CREATE UNIQUE INDEX "ProductSignal_productId_source_metric_periodEnd_key" ON "ProductSignal"("productId", "source", "metric", "periodEnd");

-- CreateIndex
CREATE UNIQUE INDEX "ProductAssetLink_productId_assetId_key" ON "ProductAssetLink"("productId", "assetId");

-- AddForeignKey
ALTER TABLE "Asset" ADD CONSTRAINT "Asset_industryId_fkey" FOREIGN KEY ("industryId") REFERENCES "Industry"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "PriceSnapshot" ADD CONSTRAINT "PriceSnapshot_assetId_fkey" FOREIGN KEY ("assetId") REFERENCES "Asset"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "Ranking" ADD CONSTRAINT "Ranking_industryId_fkey" FOREIGN KEY ("industryId") REFERENCES "Industry"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "Ranking" ADD CONSTRAINT "Ranking_assetId_fkey" FOREIGN KEY ("assetId") REFERENCES "Asset"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "Analysis" ADD CONSTRAINT "Analysis_industryId_fkey" FOREIGN KEY ("industryId") REFERENCES "Industry"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "Analysis" ADD CONSTRAINT "Analysis_assetId_fkey" FOREIGN KEY ("assetId") REFERENCES "Asset"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "Analysis" ADD CONSTRAINT "Analysis_productId_fkey" FOREIGN KEY ("productId") REFERENCES "Product"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "News" ADD CONSTRAINT "News_industryId_fkey" FOREIGN KEY ("industryId") REFERENCES "Industry"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "News" ADD CONSTRAINT "News_assetId_fkey" FOREIGN KEY ("assetId") REFERENCES "Asset"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ProductSignal" ADD CONSTRAINT "ProductSignal_productId_fkey" FOREIGN KEY ("productId") REFERENCES "Product"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ProductAssetLink" ADD CONSTRAINT "ProductAssetLink_productId_fkey" FOREIGN KEY ("productId") REFERENCES "Product"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ProductAssetLink" ADD CONSTRAINT "ProductAssetLink_assetId_fkey" FOREIGN KEY ("assetId") REFERENCES "Asset"("id") ON DELETE CASCADE ON UPDATE CASCADE;
