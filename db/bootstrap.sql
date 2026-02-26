-- db/bootstrap.sql
--
-- One-time cluster-level setup. Run as a superuser against the maintenance database,
-- passing the minkops app-user password via psql variable substitution:
--
--   psql postgres -v minkops_password=YOUR_PASSWORD -f db/bootstrap.sql
--
-- The password must match DATABASE_URL in .env (e.g. MINKOPS_DB_PASSWORD there).
-- This script is idempotent and safe to re-run.
-- After running this once, use `seed-db` (schema.sql) for all subsequent resets.

-- ─── 1. Application role ─────────────────────────────────────────────────────
-- `minkops` is the least-privilege runtime user. It can connect and perform DML
-- but cannot create/drop objects, create databases, or connect to any other database.
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'minkops') THEN
        CREATE ROLE minkops LOGIN PASSWORD :'minkops_password';
        RAISE NOTICE 'Role minkops created.';
    ELSE
        RAISE NOTICE 'Role minkops already exists — skipping creation.';
    END IF;
END $$;

-- ─── 2. Database ─────────────────────────────────────────────────────────────
-- Creates minkops_app owned by the current superuser if it does not already exist.
-- \gexec runs each returned row as a SQL command — zero rows means no-op.
SELECT 'CREATE DATABASE minkops_app'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'minkops_app')
\gexec

-- minkops may connect to minkops_app only. No other databases are granted.
GRANT CONNECT ON DATABASE minkops_app TO minkops;

\c minkops_app

-- ─── 3. Extensions ───────────────────────────────────────────────────────────
-- uuid-ossp provides uuid_generate_v4() used as the default for UUID primary keys.
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- `vector` requires superuser on some local installs (e.g., managed Postgres).
-- The DO block degrades gracefully rather than aborting the entire bootstrap.
DO $$
BEGIN
    CREATE EXTENSION IF NOT EXISTS vector;
EXCEPTION
    WHEN insufficient_privilege THEN
        RAISE WARNING 'Insufficient privilege to create extension "vector". schema.sql will use JSONB embedding fallback.';
END $$;

-- ─── 4. Schema-level privileges ──────────────────────────────────────────────
-- minkops can see and use objects in the public schema but cannot create new ones.
GRANT USAGE ON SCHEMA public TO minkops;

-- Allow minkops to call functions already present in public (e.g., uuid_generate_v4).
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO minkops;

-- ─── 5. Default privileges ───────────────────────────────────────────────────
-- Tables and functions created by the current superuser in this schema are
-- automatically granted DML access to minkops. This covers every table that
-- schema.sql will create on each reset without requiring a re-grant afterwards.
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO minkops;

ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT EXECUTE ON FUNCTIONS TO minkops;
