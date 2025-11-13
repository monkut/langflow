-- PostgreSQL initialization script for multi-tenant Langflow
-- This script sets up the database with recommended settings

-- Create extensions (if needed)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";  -- For text search performance

-- The tenant_schemas table will be created automatically by SQLModel
-- during first startup via Alembic migrations

-- Performance tuning for multi-tenant workload
ALTER DATABASE langflow SET random_page_cost = 1.1;
ALTER DATABASE langflow SET effective_io_concurrency = 200;

-- Set default timezone to UTC
ALTER DATABASE langflow SET timezone = 'UTC';

-- Create a function to help monitor schema sizes
CREATE OR REPLACE FUNCTION public.get_schema_sizes()
RETURNS TABLE(schema_name text, size_bytes bigint, size_pretty text) AS $$
BEGIN
    RETURN QUERY
    SELECT
        s.schema_name::text,
        SUM(pg_total_relation_size(quote_ident(s.schema_name) || '.' || quote_ident(t.tablename)))::bigint as size_bytes,
        pg_size_pretty(SUM(pg_total_relation_size(quote_ident(s.schema_name) || '.' || quote_ident(t.tablename)))::bigint) as size_pretty
    FROM information_schema.schemata s
    LEFT JOIN pg_tables t ON t.schemaname = s.schema_name
    WHERE s.schema_name NOT IN ('pg_catalog', 'information_schema')
    GROUP BY s.schema_name
    ORDER BY size_bytes DESC NULLS LAST;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION public.get_schema_sizes() IS 'Get the size of all schemas in the database';
