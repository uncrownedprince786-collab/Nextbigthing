-- What the learning loop reads: which confirmations backed a decision, and which side a refusal
-- was refusing.
--
-- Two nullable columns on "DecisionLog", no table touched and no backfill. Rows written before
-- this migration keep NULL in both, which is the honest value: the legs were never recorded, and
-- recomputing them now would read today's rewritten factor, setup and analog rows and attach them
-- to a past call.
--
-- Why they exist. The log recorded the grade and the gate and not the legs, so nothing could ever
-- be learned about whether a confirmation earns its place -- the fifth, the entry trigger, was
-- added with no way to tell afterwards whether names it backed did any better than names it did
-- not. And a refusal such as `stop-crossed` did not record the side it refused, so it could not be
-- scored: principle 7 says every claim is checked against what followed, and "this was not worth
-- doing" is a claim.
--
-- Text rather than an array or an enum, for the reason "entryTrigger" is: the set of legs is a
-- research result that will change, and the column is read by name in exactly one place.
ALTER TABLE "DecisionLog"
  ADD COLUMN "legs"   TEXT,
  ADD COLUMN "intent" TEXT;
