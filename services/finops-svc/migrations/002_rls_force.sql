-- FORCE RLS on finops tables.
DO $$
DECLARE
    t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY['token_usage', 'budgets', 'billing_periods'] LOOP
        IF EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_schema='finops' AND table_name=t AND column_name='tenant_id') THEN
            EXECUTE format('ALTER TABLE finops.%I ENABLE ROW LEVEL SECURITY', t);
            EXECUTE format('ALTER TABLE finops.%I FORCE ROW LEVEL SECURITY', t);
            EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON finops.%I', t);
            EXECUTE format($sql$
                CREATE POLICY tenant_isolation ON finops.%I
                USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
            $sql$, t);
        END IF;
    END LOOP;
END $$;
