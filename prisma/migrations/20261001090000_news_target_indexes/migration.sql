-- schema.prisma has declared @@index([assetId]) and @@index([productId]) on News since the
-- table was created, and no migration ever created them: the init migration wrote only
-- News_publishedAt_idx, and the two dedupe migrations since then added unique indexes only.
-- So the schema file and the database have disagreed from the start. Nothing was wrong in
-- the data, because these are lookup indexes rather than constraints, but the next person to
-- run `prisma migrate dev` would have had this drift generated underneath their own change.
--
-- They are also the right indexes to have. Every asset page and every product page reads its
-- own news by exactly these columns, and the partial unique indexes cannot serve that read:
-- theirs lead with url, and News_asset_url_key is restricted to rows whose product is null.
--
-- IF NOT EXISTS because a database that was ever pointed at `migrate dev` may already have
-- them under these names.
CREATE INDEX IF NOT EXISTS "News_assetId_idx" ON "News"("assetId");
CREATE INDEX IF NOT EXISTS "News_productId_idx" ON "News"("productId");
