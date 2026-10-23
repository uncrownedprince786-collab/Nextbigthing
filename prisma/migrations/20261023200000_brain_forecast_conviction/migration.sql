-- A forecast can now be a silence, and a silence has to be stored as one.
--
-- Until this migration every row in `BrainForecast` was a direction the page printed. The lanes
-- now carry a conviction floor -- the distance from even below which the model's own probability
-- says it is near-indifferent -- and a window that lands inside it is shown as "no clear pattern"
-- rather than as a call. Those rows still have to be written: a brain that only records the
-- moments it spoke cannot be asked afterwards whether staying quiet was the right choice, and
-- that question is the whole justification for the floor.
--
-- `called` defaults to TRUE, so every row written before this reads as what it actually was. The
-- scorer grades uncalled rows alongside called ones and `jobs/forecast_score.py` reports the two
-- separately; nothing on the site computes a rate across both.
--
-- `convictionFloor` is per row and not read from the lane at display time, because a floor that
-- is re-tuned later must not reinterpret a page that was already shown.
ALTER TABLE "BrainForecast"
    ADD COLUMN IF NOT EXISTS "called" BOOLEAN NOT NULL DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS "convictionFloor" DOUBLE PRECISION;

-- The record page's counts are per horizon and split on `called`; every one of them is this index.
CREATE INDEX IF NOT EXISTS "BrainForecast_called_horizonKey_idx"
    ON "BrainForecast" ("called", "horizonKey");
