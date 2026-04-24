-- FORCE RLS on governance tables that carry tenant_id.
-- audit_log intentionally uses a DIFFERENT pattern: platform-admin readable,
-- tenant-admin readable only for their own rows.

DO $$
DECLARE
    t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY['hitl_queue', 'audit_log', 'feature_flags'] LOOP
        IF EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_schema='governance' AND table_name=t AND column_name='tenant_id') THEN
            EXECUTE format('ALTER TABLE governance.%I ENABLE ROW LEVEL SECURITY', t);
            EXECUTE format('ALTER TABLE governance.%I FORCE ROW LEVEL SECURITY', t);
            EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON governance.%I', t);
            EXECUTE format($sql$
                CREATE POLICY tenant_isolation ON governance.%I
                USING (
                    tenant_id IS NULL
                    OR tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid
                )
            $sql$, t);
        END IF;
    END LOOP;
END $$;
