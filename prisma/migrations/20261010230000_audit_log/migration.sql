-- The logbook shown on /logbook: one entry per day and one review per week, written at the end of the
-- decision workflow by tools/audit_log.py. A new table and nothing else. Never pruned.
CREATE TABLE "AuditLog" (
  "id"        TEXT         NOT NULL DEFAULT gen_random_uuid()::text,
  "day"       DATE         NOT NULL,
  "kind"      TEXT         NOT NULL,
  "title"     TEXT         NOT NULL,
  "lines"     JSONB        NOT NULL,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "AuditLog_pkey" PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX "AuditLog_day_kind_key" ON "AuditLog"("day", "kind");
