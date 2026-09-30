-- News was unique on url across the whole table, so once an article was stored against any
-- one row it could not be stored again for any other. That made coverage a race the first
-- target won: the seven broad industry feeds claimed shared articles before the seventy
-- asset feeds ran, and two metal ETFs tracking the same metal could never both hold the
-- same coverage story.
--
-- The same article is genuinely relevant to more than one target, so dedupe within a target
-- and allow it to appear on more than one. These three partial indexes partition the table:
-- a row has an asset, or a product, or neither.
--
-- Prisma built @@unique([url]) as a bare unique index, not a table constraint, so it has to
-- go with DROP INDEX. DROP CONSTRAINT here would match nothing and quietly do nothing.
DROP INDEX IF EXISTS "News_url_key";

CREATE UNIQUE INDEX IF NOT EXISTS "News_asset_url_key"
    ON "News" ("assetId", url) WHERE "assetId" IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS "News_product_url_key"
    ON "News" ("productId", url)
    WHERE "productId" IS NOT NULL AND "assetId" IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS "News_industry_url_key"
    ON "News" (url) WHERE "assetId" IS NULL AND "productId" IS NULL;
