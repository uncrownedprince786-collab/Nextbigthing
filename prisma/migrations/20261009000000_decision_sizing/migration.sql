-- What the trade was worth at the moment it was decided.
--
-- Three nullable columns on "DecisionLog", no table touched and no backfill. Every row written
-- before this migration keeps NULL in all three, which is the honest value: nothing measured
-- them, and a backfill would have to read today's "SetupTarget" and call it last month's.
--
-- Why they exist. Two rules now act on a stored reward against risk -- gate 5 bypasses a
-- disagreeing longer view at ASYMMETRY_CLEARS, and gate 8 carries a withheld trend at the same
-- bar -- and `jobs/horizons.py` rewrites "SetupTarget" on every run. So the figure a decision
-- rested on survives only if the decision records it. Without these columns the threshold could
-- never be checked against what followed, which principle 7 forbids: every signal is checked
-- against what actually happened afterwards.
--
-- baseRateShare and baseRateCount are two columns rather than one for the reason the pages never
-- print a share without its denominator: 62% over 9 matched days and over 600 are different
-- findings, and a log that kept only the first could not tell them apart.
ALTER TABLE "DecisionLog"
  ADD COLUMN "rewardRisk"    DOUBLE PRECISION,
  ADD COLUMN "baseRateShare" DOUBLE PRECISION,
  ADD COLUMN "baseRateCount" INTEGER;
