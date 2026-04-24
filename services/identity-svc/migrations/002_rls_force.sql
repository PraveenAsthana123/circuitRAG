-- FORCE RLS on tenant-scoped tables (Design Area 5).
-- Without FORCE, the table owner bypasses RLS even when ENABLE is set.
-- The app role (documind_app) is not the owner + not a superuser, so it's
-- subject to RLS regardless — but FORCE keeps ops staff honest when
-- they use the owner role for diagnostic reads.

-- identity: only `users` is tenant-scoped by our design (tenants is the
-- tenant table itself + managed by platform admins via ops role).
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables
               WHERE table_schema='identity' AND table_name='users') THEN
        EXECUTE 'ALTER TABLE identity.users ENABLE ROW LEVEL SECURITY';
        EXECUTE 'ALTER TABLE identity.users FORCE ROW LEVEL SECURITY';
        EXECUTE 'DROP POLICY IF EXISTS tenant_isolation ON identity.users';
        EXECUTE $sql$
            CREATE POLICY tenant_isolation ON identity.users
            USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
        $sql$;
    END IF;
END $$;
