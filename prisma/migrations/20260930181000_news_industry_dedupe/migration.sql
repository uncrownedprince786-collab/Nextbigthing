-- The previous migration set out to dedupe news per target rather than globally, and did
-- that for assets and for products. The industry partition was left keyed on url alone:
--
--   CREATE UNIQUE INDEX "News_industry_url_key" ON "News" (url)
--     WHERE "assetId" IS NULL AND "productId" IS NULL;
--
-- so the very problem it fixed for assets survived for industries. Energy and Mega Cap Tech
-- can both genuinely be the subject of one story about a data centre power contract, and
-- under that index whichever industry feed ran first took the article and the other showed
-- nothing. The target here is the industry, so the key has to name it.
--
-- Rows already stored keep their industry, so nothing is lost by widening the key; the
-- next run simply fills in the copies the old index refused.
DROP INDEX IF EXISTS "News_industry_url_key";

CREATE UNIQUE INDEX IF NOT EXISTS "News_industry_url_key"
    ON "News" ("industryId", url)
    WHERE "assetId" IS NULL AND "productId" IS NULL AND "industryId" IS NOT NULL;

-- A row with no industry, no asset and no product has no target to dedupe within, and
-- nothing writes one. Keeping url unique among those is the same rule as before for a set
-- that should stay empty.
CREATE UNIQUE INDEX IF NOT EXISTS "News_untargeted_url_key"
    ON "News" (url)
    WHERE "assetId" IS NULL AND "productId" IS NULL AND "industryId" IS NULL;
