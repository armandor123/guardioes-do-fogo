CREATE EXTENSION IF NOT EXISTS postgis WITH SCHEMA public;
CREATE TABLE cooperatives(id TEXT PRIMARY KEY, name TEXT NOT NULL);
CREATE TABLE users(
 id TEXT PRIMARY KEY, coop_id TEXT NOT NULL REFERENCES cooperatives(id),
 name TEXT NOT NULL, username TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL,
 role TEXT NOT NULL CHECK(role IN ('farmer','cooperative')),
 must_change BOOLEAN NOT NULL DEFAULT TRUE);
CREATE TABLE properties(
 id TEXT PRIMARY KEY, farmer_id TEXT NOT NULL REFERENCES users(id), name TEXT,
 municipality TEXT NOT NULL, state TEXT NOT NULL,
 latitude DOUBLE PRECISION NOT NULL CHECK(latitude BETWEEN -90 AND 90),
 longitude DOUBLE PRECISION NOT NULL CHECK(longitude BETWEEN -180 AND 180),
 area_ha DOUBLE PRECISION CHECK(area_ha>=0 AND area_ha < 'Infinity'::float8),
 location geography(Point,4326) GENERATED ALWAYS AS
   (ST_SetSRID(ST_MakePoint(longitude,latitude),4326)::geography) STORED);
CREATE INDEX idx_properties_location ON properties USING GIST(location);
CREATE TABLE sessions(
 id TEXT PRIMARY KEY, token_hash TEXT NOT NULL UNIQUE,
 user_id TEXT NOT NULL REFERENCES users(id), expires DOUBLE PRECISION NOT NULL,
 refresh_hash TEXT NOT NULL UNIQUE, refresh_expires DOUBLE PRECISION NOT NULL);
CREATE INDEX idx_sessions_user ON sessions(user_id);
CREATE TABLE refresh_history(
 token_hash TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE);
CREATE TABLE incidents(
 id TEXT PRIMARY KEY, property_id TEXT NOT NULL REFERENCES properties(id),
 farmer_id TEXT NOT NULL REFERENCES users(id), description TEXT NOT NULL,
 latitude DOUBLE PRECISION CHECK(latitude BETWEEN -90 AND 90),
 longitude DOUBLE PRECISION CHECK(longitude BETWEEN -180 AND 180),
 location_source TEXT NOT NULL CHECK(location_source IN ('gps','manual','unavailable')),
 location_authorized BOOLEAN NOT NULL,
 created_at TIMESTAMPTZ NOT NULL, status TEXT NOT NULL DEFAULT 'submitted'
 CHECK(status IN ('submitted','under_review','verified','rejected','escalated')),
 photo_key TEXT NOT NULL, photo_type TEXT NOT NULL, ai_json JSONB NOT NULL,
 client_request_id UUID NOT NULL, request_hash TEXT NOT NULL,
 UNIQUE(farmer_id,client_request_id),
 CHECK((location_source='unavailable' AND latitude IS NULL AND longitude IS NULL)
 OR (location_source IN ('gps','manual') AND latitude IS NOT NULL AND longitude IS NOT NULL AND location_authorized)));
CREATE TABLE reviews(
 id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY, incident_id TEXT NOT NULL REFERENCES incidents(id),
 reviewer_id TEXT NOT NULL REFERENCES users(id), old_status TEXT NOT NULL, new_status TEXT NOT NULL,
 notes TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL);
CREATE INDEX idx_incidents_property ON incidents(property_id);
CREATE INDEX idx_incidents_farmer_created ON incidents(farmer_id,created_at DESC);
CREATE INDEX idx_users_coop ON users(coop_id);
