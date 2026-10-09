-- Which entry rule fired on a session, and which way.
--
-- Two nullable columns on "AssetFactor", no table touched and no backfill. Every row written
-- before this migration keeps NULL in both, which is the honest value: the reading was not
-- taken on those sessions, and a backfill would be inventing one. The factor job rewrites the
-- newest session on every run, so the live row carries the reading from the first run after
-- this lands and the history stays null, which is what a reader of `bars` already expects.
--
-- Why they exist. brain.md rule 54 measured four candidate entry rules against the
-- moving-average stack on identical terms -- same stop, same target, same forward window --
-- and found three earlier and slightly better, and all three far rarer. `squeeze_break` fires
-- on 11,361 sessions against the stack's 223,667 and beats it 0.153R to 0.128R, which is about
-- two standard errors on that sample. Swapping the entry rule would have cut the pool from 467
-- directions to a few dozen for an improvement the sample can barely see, so the two that beat
-- the stack are stored beside it as a fifth confirmation instead.
--
-- Text rather than an enum. The set of rules is a research result and will change when the next
-- sweep says it should; an enum would make every such change a migration, and the column is
-- read by name in exactly one place.
ALTER TABLE "AssetFactor"
  ADD COLUMN "entryTrigger"     TEXT,
  ADD COLUMN "triggerDirection" TEXT;
