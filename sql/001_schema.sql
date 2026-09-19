-- =====================================================================
-- Vienna Vibe : schéma du entrepôt
--
-- Trois couches :
--   raw   : payloads bruts, tels que reçus des API. Jamais modifiés.
--   core  : modèle dimensionnel (dimensions + faits), grain explicite.
--   marts : vues d'analyse, consommées par les dashboards et les requêtes.
--
-- Toutes les tables de faits ont une CLÉ NATURELLE contrainte UNIQUE.
-- C'est elle qui rend le pipeline idempotent : un rejeu du même créneau
-- produit exactement le même état final, via ON CONFLICT.
-- =====================================================================

CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS marts;

-- =====================================================================
-- COUCHE RAW
-- =====================================================================

-- Un enregistrement par appel d'API. Sert d'archive et de filet :
-- si la transformation est buguée, on peut tout rejouer sans réinterroger
-- les API (dont les fenêtres d'historique sont limitées).
CREATE TABLE IF NOT EXISTS raw.api_payload (
    payload_id      BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source          TEXT        NOT NULL,          -- 'open_meteo' | 'spotify_recently_played'
    window_start    TIMESTAMPTZ NOT NULL,          -- créneau logique du run
    fetched_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    http_status     INTEGER     NOT NULL,
    body            JSONB       NOT NULL,
    CONSTRAINT api_payload_natural_key UNIQUE (source, window_start, fetched_at)
);

CREATE INDEX IF NOT EXISTS ix_api_payload_source_window
    ON raw.api_payload (source, window_start DESC);

-- =====================================================================
-- COUCHE CORE : DIMENSIONS
-- =====================================================================

-- Lieux suivis. Clé naturelle : le code.
CREATE TABLE IF NOT EXISTS core.dim_location (
    location_id   SERIAL PRIMARY KEY,
    location_code TEXT NOT NULL UNIQUE,
    label         TEXT NOT NULL,
    latitude      NUMERIC(8,5) NOT NULL,
    longitude     NUMERIC(8,5) NOT NULL,
    timezone      TEXT NOT NULL DEFAULT 'UTC'
);

-- Codes météo WMO, tels que renvoyés par Open-Meteo.
-- Dimension conforme : partagée par tous les faits météo.
CREATE TABLE IF NOT EXISTS core.dim_weather_condition (
    weather_code  SMALLINT PRIMARY KEY,
    family        TEXT NOT NULL,   -- clear | cloud | fog | drizzle | rain | snow | shower | thunderstorm
    label_fr      TEXT NOT NULL,
    severity      SMALLINT NOT NULL CHECK (severity BETWEEN 0 AND 5)
);

-- Artistes. Clé naturelle : l'identifiant Spotify.
CREATE TABLE IF NOT EXISTS core.dim_artist (
    artist_id    TEXT PRIMARY KEY,          -- id Spotify
    artist_name  TEXT NOT NULL,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Titres. Dimension à évolution lente de type 1 :
-- la popularité change dans le temps, on garde la dernière valeur connue
-- et on trace la date de rafraîchissement.
CREATE TABLE IF NOT EXISTS core.dim_track (
    track_id        TEXT PRIMARY KEY,       -- id Spotify
    track_name      TEXT NOT NULL,
    primary_artist_id TEXT REFERENCES core.dim_artist (artist_id),
    album_name      TEXT,
    album_release_date TEXT,                -- Spotify renvoie parfois 'YYYY' ou 'YYYY-MM'
    duration_ms     INTEGER CHECK (duration_ms > 0),
    is_explicit     BOOLEAN,
    popularity      SMALLINT CHECK (popularity BETWEEN 0 AND 100),
    first_seen_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_dim_track_artist
    ON core.dim_track (primary_artist_id);

-- =====================================================================
-- COUCHE CORE : FAITS
-- =====================================================================

-- Grain : une observation météo par lieu et par heure.
-- Clé naturelle : (location_id, observed_at).
CREATE TABLE IF NOT EXISTS core.fact_weather_hourly (
    weather_fact_id   BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    location_id       INTEGER     NOT NULL REFERENCES core.dim_location (location_id),
    observed_at       TIMESTAMPTZ NOT NULL,
    weather_code      SMALLINT    REFERENCES core.dim_weather_condition (weather_code),
    temperature_c     NUMERIC(5,2) CHECK (temperature_c BETWEEN -80 AND 65),
    humidity_pct      SMALLINT     CHECK (humidity_pct BETWEEN 0 AND 100),
    precipitation_mm  NUMERIC(6,2) CHECK (precipitation_mm >= 0),
    cloud_cover_pct   SMALLINT     CHECK (cloud_cover_pct BETWEEN 0 AND 100),
    wind_speed_kmh    NUMERIC(6,2) CHECK (wind_speed_kmh >= 0),
    is_daylight       BOOLEAN,
    loaded_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT fact_weather_natural_key UNIQUE (location_id, observed_at)
);

CREATE INDEX IF NOT EXISTS ix_fact_weather_observed_at
    ON core.fact_weather_hourly (observed_at DESC);

-- Grain : une écoute, c'est-à-dire un titre joué à un instant donné.
-- Clé naturelle : (played_at, track_id).
--
-- Pourquoi cette clé : l'API /me/player/recently-played ne renvoie que les
-- 50 dernières écoutes. On l'interroge donc toutes les heures, et les appels
-- se recouvrent volontairement. Sans clé naturelle, chaque recouvrement
-- créerait des doublons. Un événement d'écoute est immuable : on l'insère
-- une fois, jamais on ne le met à jour.
CREATE TABLE IF NOT EXISTS core.fact_listening_event (
    listening_event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    played_at          TIMESTAMPTZ NOT NULL,
    track_id           TEXT        NOT NULL REFERENCES core.dim_track (track_id),
    context_type       TEXT,                     -- playlist | album | artist | NULL
    loaded_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT fact_listening_natural_key UNIQUE (played_at, track_id),
    CONSTRAINT played_at_not_in_future CHECK (played_at <= now() + INTERVAL '1 hour')
);

CREATE INDEX IF NOT EXISTS ix_fact_listening_played_at
    ON core.fact_listening_event (played_at DESC);

-- =====================================================================
-- JOURNAL DES EXÉCUTIONS
-- Sert aux contrôles de fraîcheur et à l'observabilité : combien de lignes
-- chaque run a inséré, combien il a ignoré, combien de temps il a pris.
-- =====================================================================

CREATE TABLE IF NOT EXISTS core.pipeline_run (
    run_id        BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    window_start  TIMESTAMPTZ NOT NULL,
    step          TEXT        NOT NULL,
    status        TEXT        NOT NULL CHECK (status IN ('success', 'failed')),
    rows_read     INTEGER     NOT NULL DEFAULT 0,
    rows_written  INTEGER     NOT NULL DEFAULT 0,
    rows_skipped  INTEGER     NOT NULL DEFAULT 0,
    duration_ms   INTEGER     NOT NULL DEFAULT 0,
    message       TEXT,
    started_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_pipeline_run_window
    ON core.pipeline_run (window_start DESC, step);

-- =====================================================================
-- AMORÇAGE DES DIMENSIONS STATIQUES
-- =====================================================================

INSERT INTO core.dim_location (location_code, label, latitude, longitude, timezone) VALUES
    ('vienna', 'Vienne, Autriche', 48.20849, 16.37208, 'Europe/Vienna'),
    ('lille',  'Lille, France',    50.62925,  3.05726, 'Europe/Paris')
ON CONFLICT (location_code) DO NOTHING;

-- Codes WMO utilisés par Open-Meteo.
INSERT INTO core.dim_weather_condition (weather_code, family, label_fr, severity) VALUES
    (0,  'clear',        'Ciel dégagé',                      0),
    (1,  'cloud',        'Globalement dégagé',               0),
    (2,  'cloud',        'Partiellement nuageux',            1),
    (3,  'cloud',        'Couvert',                          1),
    (45, 'fog',          'Brouillard',                       2),
    (48, 'fog',          'Brouillard givrant',               3),
    (51, 'drizzle',      'Bruine légère',                    1),
    (53, 'drizzle',      'Bruine modérée',                   2),
    (55, 'drizzle',      'Bruine dense',                     2),
    (56, 'drizzle',      'Bruine verglaçante légère',        3),
    (57, 'drizzle',      'Bruine verglaçante dense',         3),
    (61, 'rain',         'Pluie faible',                     2),
    (63, 'rain',         'Pluie modérée',                    2),
    (65, 'rain',         'Pluie forte',                      3),
    (66, 'rain',         'Pluie verglaçante faible',         3),
    (67, 'rain',         'Pluie verglaçante forte',          4),
    (71, 'snow',         'Neige faible',                     2),
    (73, 'snow',         'Neige modérée',                    3),
    (75, 'snow',         'Neige forte',                      4),
    (77, 'snow',         'Grains de neige',                  2),
    (80, 'shower',       'Averses faibles',                  2),
    (81, 'shower',       'Averses modérées',                 2),
    (82, 'shower',       'Averses violentes',                4),
    (85, 'shower',       'Averses de neige faibles',         3),
    (86, 'shower',       'Averses de neige fortes',          4),
    (95, 'thunderstorm', 'Orage',                            4),
    (96, 'thunderstorm', 'Orage avec grêle faible',          5),
    (99, 'thunderstorm', 'Orage avec grêle forte',           5)
ON CONFLICT (weather_code) DO NOTHING;
