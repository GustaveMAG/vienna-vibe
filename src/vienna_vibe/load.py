"""Chargement en base, idempotent par construction.

Tous les écrits passent par un `INSERT ... ON CONFLICT` appuyé sur la clé
naturelle de la table. Conséquence : rejouer un créneau, ou deux exécutions
qui se recouvrent, aboutissent exactement au même état final. C'est la
propriété qui permet de relancer une journée entière sans redouter les
doublons, et c'est aussi ce qui rend le backfill sûr.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

import psycopg

from .models import ListeningEvent, WeatherObservation

log = logging.getLogger(__name__)


def save_raw_payload(
    conn: psycopg.Connection,
    source: str,
    window_start: datetime,
    http_status: int,
    body: dict[str, Any],
) -> None:
    """Archive le payload brut, avant toute transformation."""
    conn.execute(
        """
        INSERT INTO raw.api_payload (source, window_start, http_status, body)
        VALUES (%(source)s, %(window_start)s, %(http_status)s, %(body)s)
        """,
        {
            "source": source,
            "window_start": window_start,
            "http_status": http_status,
            "body": json.dumps(body),
        },
    )


def upsert_weather(
    conn: psycopg.Connection,
    observations: list[WeatherObservation],
    location_ids: dict[str, int],
) -> int:
    """Insère ou met à jour les observations météo.

    On met à jour (et non on ignore) : Open-Meteo affine ses valeurs
    récentes dans les heures qui suivent, donc la dernière version reçue
    est la plus juste.
    """
    if not observations:
        return 0

    rows = [
        (
            location_ids[obs.location_code],
            obs.observed_at,
            obs.weather_code,
            obs.temperature_c,
            obs.humidity_pct,
            obs.precipitation_mm,
            obs.cloud_cover_pct,
            obs.wind_speed_kmh,
            obs.is_daylight,
        )
        for obs in observations
        if obs.location_code in location_ids
    ]
    if not rows:
        return 0

    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO core.fact_weather_hourly (
                location_id, observed_at, weather_code, temperature_c,
                humidity_pct, precipitation_mm, cloud_cover_pct,
                wind_speed_kmh, is_daylight
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (location_id, observed_at) DO UPDATE SET
                weather_code     = EXCLUDED.weather_code,
                temperature_c    = EXCLUDED.temperature_c,
                humidity_pct     = EXCLUDED.humidity_pct,
                precipitation_mm = EXCLUDED.precipitation_mm,
                cloud_cover_pct  = EXCLUDED.cloud_cover_pct,
                wind_speed_kmh   = EXCLUDED.wind_speed_kmh,
                is_daylight      = EXCLUDED.is_daylight,
                loaded_at        = now()
            """,
            rows,
        )
    return len(rows)


def upsert_dimensions(conn: psycopg.Connection, events: list[ListeningEvent]) -> None:
    """Alimente dim_artist et dim_track avant les faits.

    L'ordre compte : la table de faits porte une clé étrangère vers
    dim_track, donc les dimensions doivent exister d'abord. C'est aussi ce
    qui garantit qu'aucun fait ne référence un titre inconnu.
    """
    artists = {
        e.track.primary_artist.artist_id: e.track.primary_artist
        for e in events
        if e.track.primary_artist is not None
    }
    if artists:
        with conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO core.dim_artist (artist_id, artist_name)
                VALUES (%s, %s)
                ON CONFLICT (artist_id) DO UPDATE SET
                    artist_name  = EXCLUDED.artist_name,
                    last_seen_at = now()
                """,
                [(a.artist_id, a.artist_name) for a in artists.values()],
            )

    tracks = {e.track.track_id: e.track for e in events}
    if tracks:
        with conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO core.dim_track (
                    track_id, track_name, primary_artist_id, album_name,
                    album_release_date, duration_ms, is_explicit, popularity
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (track_id) DO UPDATE SET
                    track_name         = EXCLUDED.track_name,
                    primary_artist_id  = COALESCE(EXCLUDED.primary_artist_id,
                                                  core.dim_track.primary_artist_id),
                    album_name         = EXCLUDED.album_name,
                    album_release_date = EXCLUDED.album_release_date,
                    duration_ms        = EXCLUDED.duration_ms,
                    is_explicit        = EXCLUDED.is_explicit,
                    popularity         = EXCLUDED.popularity,
                    updated_at         = now()
                """,
                [
                    (
                        t.track_id,
                        t.track_name,
                        t.primary_artist.artist_id if t.primary_artist else None,
                        t.album_name,
                        t.album_release_date,
                        t.duration_ms,
                        t.is_explicit,
                        t.popularity,
                    )
                    for t in tracks.values()
                ],
            )


def insert_listening_events(
    conn: psycopg.Connection, events: list[ListeningEvent]
) -> tuple[int, int]:
    """Insère les écoutes nouvelles. Renvoie (insérées, ignorées).

    `DO NOTHING` et non `DO UPDATE` : une écoute est un fait immuable.
    Le décompte des lignes ignorées est une mesure utile du recouvrement
    entre exécutions — s'il tombe à zéro, la collecte est trop espacée et
    des écoutes ont probablement été perdues.
    """
    if not events:
        return 0, 0

    inserted = 0
    with conn.cursor() as cur:
        for event in events:
            cur.execute(
                """
                INSERT INTO core.fact_listening_event (played_at, track_id, context_type)
                VALUES (%(played_at)s, %(track_id)s, %(context_type)s)
                ON CONFLICT (played_at, track_id) DO NOTHING
                """,
                {
                    "played_at": event.played_at,
                    "track_id": event.track.track_id,
                    "context_type": event.context_type,
                },
            )
            inserted += cur.rowcount or 0

    return inserted, len(events) - inserted


def last_listening_timestamp(conn: psycopg.Connection) -> datetime | None:
    """Dernière écoute connue, point de départ de la prochaine collecte."""
    cur = conn.execute("SELECT MAX(played_at) AS last_played FROM core.fact_listening_event")
    row = cur.fetchone()
    return row["last_played"] if row else None


def log_step(
    conn: psycopg.Connection,
    window_start: datetime,
    step: str,
    status: str,
    rows_read: int = 0,
    rows_written: int = 0,
    rows_skipped: int = 0,
    duration_ms: int = 0,
    message: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO core.pipeline_run (
            window_start, step, status, rows_read, rows_written,
            rows_skipped, duration_ms, message
        )
        VALUES (%(window_start)s, %(step)s, %(status)s, %(rows_read)s,
                %(rows_written)s, %(rows_skipped)s, %(duration_ms)s, %(message)s)
        """,
        {
            "window_start": window_start,
            "step": step,
            "status": status,
            "rows_read": rows_read,
            "rows_written": rows_written,
            "rows_skipped": rows_skipped,
            "duration_ms": duration_ms,
            "message": message,
        },
    )
