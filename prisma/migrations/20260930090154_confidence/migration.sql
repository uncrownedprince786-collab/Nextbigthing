-- CreateEnum
CREATE TYPE "Confidence" AS ENUM ('high', 'medium', 'low', 'none');

-- AlterTable
ALTER TABLE "Analysis" ADD COLUMN     "confidence" "Confidence" NOT NULL DEFAULT 'none',
ALTER COLUMN "id" SET DEFAULT gen_random_uuid()::text;

-- AlterTable
ALTER TABLE "Asset" ALTER COLUMN "id" SET DEFAULT gen_random_uuid()::text;

-- AlterTable
ALTER TABLE "Industry" ALTER COLUMN "id" SET DEFAULT gen_random_uuid()::text;

-- AlterTable
ALTER TABLE "News" ALTER COLUMN "id" SET DEFAULT gen_random_uuid()::text;

-- AlterTable
ALTER TABLE "PriceSnapshot" ALTER COLUMN "id" SET DEFAULT gen_random_uuid()::text;

-- AlterTable
ALTER TABLE "Product" ADD COLUMN     "confidence" "Confidence" NOT NULL DEFAULT 'none',
ADD COLUMN     "confidenceNote" TEXT,
ADD COLUMN     "sourcesAgree" INTEGER NOT NULL DEFAULT 0,
ADD COLUMN     "sourcesAnswered" INTEGER NOT NULL DEFAULT 0,
ALTER COLUMN "id" SET DEFAULT gen_random_uuid()::text;

-- AlterTable
ALTER TABLE "ProductAssetLink" ALTER COLUMN "id" SET DEFAULT gen_random_uuid()::text;

-- AlterTable
ALTER TABLE "ProductSignal" ALTER COLUMN "id" SET DEFAULT gen_random_uuid()::text;

-- AlterTable
ALTER TABLE "Ranking" ADD COLUMN     "confidence" "Confidence" NOT NULL DEFAULT 'none',
ADD COLUMN     "confidenceNote" TEXT,
ALTER COLUMN "id" SET DEFAULT gen_random_uuid()::text;
