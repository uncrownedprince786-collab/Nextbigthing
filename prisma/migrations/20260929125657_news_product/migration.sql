-- AlterTable
ALTER TABLE "News" ADD COLUMN     "productId" TEXT;

-- AddForeignKey
ALTER TABLE "News" ADD CONSTRAINT "News_productId_fkey" FOREIGN KEY ("productId") REFERENCES "Product"("id") ON DELETE CASCADE ON UPDATE CASCADE;
