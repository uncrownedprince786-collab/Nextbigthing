-- Row-level security as a backstop, not as the fix.
--
-- WHAT IS ALREADY TRUE, MEASURED 2026-10-19 ON THE PRIMARY.
-- `anon` and `authenticated` hold **no grants at all** on any table in `public`
-- (information_schema.role_table_grants returns zero rows for them), and the Data API answers an
-- unauthenticated request with 401. The broad DML-and-TRUNCATE exposure recorded earlier was
-- corrected in an earlier session and is not present. This migration does not repair that.
--
-- WHAT IS NOT TRUE, AND IS WHY THIS EXISTS.
-- There is no second line. All 46 tables had `relrowsecurity = false` and **zero policies**, so the
-- only thing standing between the Data API and every row is the absence of a grant. Two paths can
-- restore one without anybody deciding to:
--
--   * `pg_default_acl` still carries a `supabase_admin`-owned entry for `public` granting
--     `anon=arwdDxtm` and `authenticated=arwdDxtm` on tables **that role** creates. Every table
--     today is `postgres`-owned and inherits the corrected `postgres` defaults, so nothing is
--     exposed now -- but that is a property of who has created tables so far, not a guarantee. The
--     entry cannot be altered from `postgres`; it needs an account this project does not have.
--   * A `GRANT` typed into the dashboard's SQL editor is one statement away at any time.
--
-- With RLS enabled and no policy, either of those grants a role the right to ask and still returns
-- no rows. That is the difference between one mistake being an incident and one mistake being
-- nothing.
--
-- WHY THIS DOES NOT BREAK THE BACKEND.
-- `postgres` -- the role the web app, every job and `prisma migrate deploy` connect as -- has
-- `rolbypassrls`, and so do `service_role`, `supabase_admin`, `supabase_etl_admin` and
-- `supabase_read_only_user`. RLS is invisible to all of them. The one role it would have cut off is
-- `nbt_phase2_reader_20261013`, a standing login with SELECT on 44 tables, no `VALID UNTIL` and no
-- bypass, which brain.md rule 118 left for the owner to decide on. Revoking it silently here would
-- take that decision for them, so it is given an explicit read-only policy instead: its access is
-- exactly what it was, and it is now written down in the schema rather than only in a grant.
DO $$
DECLARE
  t text;
  -- Guarded, because this migration also has to apply to a database that has never heard of that
  -- role: a restore rehearsal, a fresh environment, anywhere the grant was never made. `CREATE
  -- POLICY ... TO <role>` is an error when the role is absent, and a migration that only works on
  -- one machine is a migration that fails the first time it actually matters.
  reader_exists boolean := EXISTS (
    SELECT 1 FROM pg_roles WHERE rolname = 'nbt_phase2_reader_20261013');
BEGIN
  FOR t IN
    SELECT c.relname
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public'
      AND c.relkind = 'r'
      -- Prisma's own bookkeeping is read by `migrate deploy` as `postgres`, which bypasses RLS;
      -- it is covered anyway, and naming it here keeps the intent obvious.
      AND c.relname <> '_prisma_migrations'
  LOOP
    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t);

    -- Preserves exactly the SELECT the role already held. `FOR SELECT ... USING (true)` adds no
    -- right it did not have: without a grant the policy is unreachable, and with one it returns
    -- what the grant always allowed.
    IF reader_exists THEN
      EXECUTE format(
        'DROP POLICY IF EXISTS %I ON public.%I',
        'phase2_reader_select', t);
      EXECUTE format(
        'CREATE POLICY %I ON public.%I FOR SELECT TO %I USING (true)',
        'phase2_reader_select', t, 'nbt_phase2_reader_20261013');
    END IF;
  END LOOP;
END
$$;
