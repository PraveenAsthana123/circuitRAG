-- FORCE RLS on eval tables that carry tenant_id (feedback).
-- Datasets + datapoints + runs are PLATFORM-LEVEL (shared across tenants),
-- so no RLS on those; access controlled at the service layer.

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_schema='eval' AND table_name='feedback' AND column_name='tenant_id') THEN
        EXECUTE 'ALTER TABLE eval.feedback ENABLE ROW LEVEL SECURITY';
        EXECUTE 'ALTER TABLE eval.feedback FORCE ROW LEVEL SECURITY';
        EXECUTE 'DROP POLICY IF EXISTS tenant_isolation ON eval.feedback';
        EXECUTE $sql$
            CREATE POLICY tenant_isolation ON eval.feedback
            USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
        $sql$;
    END IF;
END $$;
