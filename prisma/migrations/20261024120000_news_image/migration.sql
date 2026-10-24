-- A headline with a picture is read; a list of blue links is skimmed past.
--
-- The stored rows carry a title, a url and a publisher and no image, so the crypto coin page was
-- drawing the coin's own logo beside every item -- honest, and the same picture nine times. The
-- article's own image is what a reader recognises.
--
-- `imageUrl` is nullable and `imageCheckedAt` records that we looked, which is the column that
-- makes this affordable: an article whose page publishes no `og:image` must be remembered as
-- having none, or every run re-fetches every article that will never have one. A row with a
-- checked-at and a null url is a settled answer, not an unattempted one.
ALTER TABLE "News"
    ADD COLUMN IF NOT EXISTS "imageUrl" TEXT,
    ADD COLUMN IF NOT EXISTS "imageCheckedAt" TIMESTAMPTZ(3);

-- The job asks for recent items nobody has looked at yet, which is exactly this index.
CREATE INDEX IF NOT EXISTS "News_imageCheckedAt_publishedAt_idx"
    ON "News" ("imageCheckedAt", "publishedAt" DESC);
