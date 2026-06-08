-- Run this after creating the lawinus user-data tables.
-- It lets authenticated users insert rows into bigserial tables.
grant usage, select on all sequences in schema public to authenticated;

-- Keep the same permission for future public-schema sequences.
alter default privileges in schema public
grant usage, select on sequences to authenticated;
