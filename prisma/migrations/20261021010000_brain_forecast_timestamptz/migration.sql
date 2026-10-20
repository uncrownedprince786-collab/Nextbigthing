-- The forecast instants become `timestamptz`, because the web layer writes them.
--
-- THE FAULT. Prisma's default mapping for `DateTime` is `timestamp(3)` -- *without* time zone --
-- and the Node driver serialises a JS `Date` with its local offset. Postgres then drops the offset
-- and keeps the wall-clock part, so a forecast made at 22:45 UTC on a machine five hours ahead was
-- stored as 17:45. Measured on the first two rows this table ever held, both off by exactly the
-- host's offset.
--
-- It had never bitten before because nothing in the web layer wrote a `DateTime`: every other
-- timestamp in this schema is written by the Python jobs through psycopg, which sends an aware
-- datetime, or is a `@db.Date` where a wall-clock day is the intended meaning. This table is the
-- first one the request path inserts into, and an instant is exactly the case where the wall clock
-- is not the meaning -- `maturesAt` decides when a claim may be graded, and five hours of drift
-- would have graded five-minute forecasts against prices from a different afternoon.
--
-- THE FIX. `timestamptz` stores an instant and the driver's offset is honoured rather than
-- discarded. Nothing else in the schema changes: these two tables are new, hold only the rows
-- written while the fault was live, and those rows are removed below rather than converted --
-- converting them would preserve a wrong instant in a correct type, which is worse than losing two
-- test rows, and `BrainForecastOutcome` is still empty.
DELETE FROM "BrainForecastOutcome";
DELETE FROM "BrainForecast";

ALTER TABLE "BrainForecast"
    ALTER COLUMN "asOf" TYPE TIMESTAMPTZ(3) USING "asOf" AT TIME ZONE 'UTC',
    ALTER COLUMN "maturesAt" TYPE TIMESTAMPTZ(3) USING "maturesAt" AT TIME ZONE 'UTC',
    ALTER COLUMN "createdAt" TYPE TIMESTAMPTZ(3) USING "createdAt" AT TIME ZONE 'UTC';

ALTER TABLE "BrainForecastOutcome"
    ALTER COLUMN "observedAt" TYPE TIMESTAMPTZ(3) USING "observedAt" AT TIME ZONE 'UTC',
    ALTER COLUMN "createdAt" TYPE TIMESTAMPTZ(3) USING "createdAt" AT TIME ZONE 'UTC';
