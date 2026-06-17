-- ============================================================
-- schema.sql — Reference only. Your `schemes` table already exists.
-- ============================================================
-- This file does NOT create your table — it already exists and is
-- referenced by saved_schemes via a foreign key. This file documents
-- it for reference and provides ONE optional migration.
--
-- Your actual table (from \d schemes):
--
--   id                  | bigint                  | PK, identity
--   application_url     | character varying(255)  |
--   benefit_amount       | character varying(255)  |
--   benefit_type         | character varying(255)  |
--   category             | character varying(255)  |
--   deadline             | date                     |
--   description          | text                     |
--   documents_required   | text                     |
--   eligibility_json     | jsonb                    |
--   eligibility_summary  | character varying(255)  |
--   how_to_apply         | text                     |
--   is_active            | boolean                  |
--   last_updated         | timestamp(6)             |
--   ministry             | character varying(255)  |
--   name                 | character varying(255)  |
--   state                | character varying(255)  |
--   subcategory          | character varying(255)  |
--
-- ============================================================
-- OPTIONAL — run this once if you want fast SQL-level upserts
-- ============================================================
-- Without this constraint, db/loader.py does the existence check
-- in Python (SELECT by name, then INSERT or UPDATE). That works fine
-- and requires no changes to your table. If you want a single
-- ON CONFLICT upsert instead (slightly faster, atomic), run:
--
--   ALTER TABLE schemes ADD CONSTRAINT uq_schemes_name UNIQUE (name);
--
-- Then swap to the ON CONFLICT version of the queries in db/loader.py
-- (commented inline in that file).

-- ============================================================
-- OPTIONAL — recommended indexes for query performance
-- ============================================================
-- Safe to run any time; CREATE INDEX IF NOT EXISTS is a no-op if already present.

CREATE INDEX IF NOT EXISTS idx_schemes_state    ON schemes (state);
CREATE INDEX IF NOT EXISTS idx_schemes_ministry ON schemes (ministry);
CREATE INDEX IF NOT EXISTS idx_schemes_category ON schemes (category);
CREATE INDEX IF NOT EXISTS idx_schemes_active   ON schemes (is_active);

-- Full text search across name + description (used by an eventual search endpoint)
CREATE INDEX IF NOT EXISTS idx_schemes_fts ON schemes
    USING GIN (to_tsvector('english', coalesce(name, '') || ' ' || coalesce(description, '')));

-- ============================================================
-- OPTIONAL — convert eligibility_json from TEXT to JSONB later
-- ============================================================
-- Only do this if you decide you want native JSON querying (@>, ->, etc.)
-- in Postgres instead of parsing the string in application code.
-- db/loader.py now performs this migration automatically when it finds a
-- legacy TEXT column.
--
-- ALTER TABLE schemes
--   ALTER COLUMN eligibility_json TYPE jsonb
--   USING eligibility_json::jsonb;
--
-- CREATE INDEX IF NOT EXISTS idx_schemes_eligibility
--     ON schemes USING GIN (eligibility_json);

-- ============================================================
-- EXAMPLE QUERIES against the TEXT column (works right now, no migration)
-- ============================================================

-- Schemes mentioning female eligibility (string match, since column is TEXT)
-- SELECT name, eligibility_summary FROM schemes
-- WHERE eligibility_json LIKE '%"gender": "female"%';

-- Active schemes in a given state
-- SELECT name, state FROM schemes
-- WHERE is_active = true AND state = 'Tamil Nadu';

-- Full text search
-- SELECT name FROM schemes
-- WHERE to_tsvector('english', name || ' ' || description) @@ plainto_tsquery('farmer crop');
