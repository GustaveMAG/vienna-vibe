-- =====================================================================
-- Vienna Vibe : couche d'analyse
--
-- Les vues ci-dessous sont la raison d'être du pipeline : elles répondent
-- à la question « est-ce que la météo influence ce que j'écoute ? ».
-- Elles sont recalculées à la lecture, donc toujours cohérentes avec core.
-- =====================================================================

-- ---------------------------------------------------------------------
-- Jointure centrale : chaque écoute rattachée à la météo de son heure.
-- Le grain reste l'écoute ; la météo est dénormalisée pour l'analyse.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW marts.v_listening_with_weather AS
SELECT
    e.listening_event_id,
    e.played_at,
    date_trunc('hour', e.played_at)               AS played_hour,
    EXTRACT(HOUR FROM e.played_at)::SMALLINT      AS hour_of_day,
    to_char(e.played_at, 'ID')::SMALLINT          AS day_of_week,
    t.track_id,
    t.track_name,
    a.artist_name,
    t.popularity,
    t.duration_ms,
    t.is_explicit,
    l.location_code,
    w.temperature_c,
    w.humidity_pct,
    w.precipitation_mm,
    w.cloud_cover_pct,
    w.wind_speed_kmh,
    w.is_daylight,
    c.family                                      AS weather_family,
    c.label_fr                                    AS weather_label,
    c.severity                                    AS weather_severity
FROM core.fact_listening_event      e
JOIN core.dim_track                 t ON t.track_id = e.track_id
LEFT JOIN core.dim_artist           a ON a.artist_id = t.primary_artist_id
LEFT JOIN core.fact_weather_hourly  w ON w.observed_at = date_trunc('hour', e.played_at)
LEFT JOIN core.dim_location         l ON l.location_id = w.location_id
LEFT JOIN core.dim_weather_condition c ON c.weather_code = w.weather_code;

-- ---------------------------------------------------------------------
-- Le résultat qu'on cherche : profil d'écoute par famille météo.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW marts.v_listening_by_weather_family AS
SELECT
    location_code,
    weather_family,
    COUNT(*)                                          AS plays,
    COUNT(DISTINCT track_id)                          AS distinct_tracks,
    COUNT(DISTINCT artist_name)                       AS distinct_artists,
    ROUND(AVG(popularity), 1)                         AS avg_popularity,
    ROUND(AVG(duration_ms) / 1000.0, 1)               AS avg_duration_s,
    ROUND(AVG(temperature_c), 1)                      AS avg_temperature_c,
    ROUND(100.0 * AVG(CASE WHEN is_explicit THEN 1 ELSE 0 END), 1) AS pct_explicit
FROM marts.v_listening_with_weather
WHERE weather_family IS NOT NULL
GROUP BY location_code, weather_family
ORDER BY location_code, plays DESC;

-- ---------------------------------------------------------------------
-- Profil d'écoute par heure de la journée, croisé avec la clarté du jour.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW marts.v_listening_by_hour AS
SELECT
    hour_of_day,
    COUNT(*)                            AS plays,
    COUNT(DISTINCT track_id)            AS distinct_tracks,
    ROUND(AVG(popularity), 1)           AS avg_popularity,
    ROUND(AVG(temperature_c), 1)        AS avg_temperature_c,
    ROUND(100.0 * AVG(CASE WHEN is_daylight THEN 1 ELSE 0 END), 1) AS pct_daylight
FROM marts.v_listening_with_weather
GROUP BY hour_of_day
ORDER BY hour_of_day;

-- ---------------------------------------------------------------------
-- Top artistes par famille météo : la sortie « lisible » du projet.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW marts.v_top_artists_by_weather AS
WITH ranked AS (
    SELECT
        weather_family,
        artist_name,
        COUNT(*) AS plays,
        ROW_NUMBER() OVER (PARTITION BY weather_family ORDER BY COUNT(*) DESC, artist_name) AS rk
    FROM marts.v_listening_with_weather
    WHERE weather_family IS NOT NULL
      AND artist_name IS NOT NULL
    GROUP BY weather_family, artist_name
)
SELECT weather_family, artist_name, plays, rk
FROM ranked
WHERE rk <= 5
ORDER BY weather_family, rk;

-- ---------------------------------------------------------------------
-- Complétude : combien d'heures de météo sont réellement présentes
-- par jour et par lieu. 24 attendues. Sert à repérer les trous.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW marts.v_weather_coverage AS
SELECT
    l.location_code,
    (w.observed_at AT TIME ZONE 'UTC')::DATE  AS observation_date,
    COUNT(*)                                  AS hours_present,
    24 - COUNT(*)                             AS hours_missing,
    ROUND(100.0 * COUNT(*) / 24, 1)           AS coverage_pct
FROM core.fact_weather_hourly w
JOIN core.dim_location        l ON l.location_id = w.location_id
GROUP BY l.location_code, (w.observed_at AT TIME ZONE 'UTC')::DATE
ORDER BY observation_date DESC, l.location_code;

-- ---------------------------------------------------------------------
-- Santé du pipeline : dernière exécution de chaque étape et fraîcheur.
-- C'est la vue qu'on regarde en premier quand quelque chose ne va pas.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW marts.v_pipeline_health AS
WITH last_run AS (
    SELECT
        step,
        status,
        window_start,
        rows_written,
        duration_ms,
        started_at,
        ROW_NUMBER() OVER (PARTITION BY step ORDER BY started_at DESC) AS rk
    FROM core.pipeline_run
)
SELECT
    step,
    status                                              AS last_status,
    window_start                                        AS last_window,
    rows_written                                        AS last_rows_written,
    duration_ms                                         AS last_duration_ms,
    started_at                                          AS last_started_at,
    ROUND(EXTRACT(EPOCH FROM (now() - started_at)) / 60.0, 1) AS minutes_since_last_run
FROM last_run
WHERE rk = 1
ORDER BY step;

-- ---------------------------------------------------------------------
-- Les chiffres à citer : une seule ligne, tout l'essentiel du projet.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW marts.v_project_stats AS
SELECT
    (SELECT COUNT(*) FROM core.fact_weather_hourly)     AS weather_observations,
    (SELECT COUNT(*) FROM core.fact_listening_event)    AS listening_events,
    (SELECT COUNT(*) FROM core.dim_track)               AS distinct_tracks,
    (SELECT COUNT(*) FROM core.dim_artist)              AS distinct_artists,
    (SELECT MIN(observed_at) FROM core.fact_weather_hourly) AS history_starts_at,
    (SELECT MAX(observed_at) FROM core.fact_weather_hourly) AS history_ends_at,
    (SELECT COUNT(DISTINCT (observed_at AT TIME ZONE 'UTC')::DATE)
       FROM core.fact_weather_hourly)                   AS days_covered,
    (SELECT COUNT(*) FROM core.pipeline_run WHERE status = 'success') AS successful_steps,
    (SELECT COUNT(*) FROM core.pipeline_run WHERE status = 'failed')  AS failed_steps;
