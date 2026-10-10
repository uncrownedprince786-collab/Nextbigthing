-- The 14-session average true range per asset and session (jobs/factors.py), the distance a
-- resolved call's stop is measured from (lib/resolve.ts). Nullable: rows written before this column,
-- and assets with too few closes, carry no reading.
ALTER TABLE "AssetFactor" ADD COLUMN "atr14" DOUBLE PRECISION;
