-- Cache a representative photo URL per business (fetched from Google Place photos),
-- so every ranked business — not just the top few — carries an image to the site.
--
--   psql "$DWH_DATABASE_URL" -f sql/003_photos.sql

alter table businesses add column if not exists photo_url text;
