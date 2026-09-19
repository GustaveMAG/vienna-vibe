"""Test d'intégration : l'idempotence, contre un vrai PostgreSQL.

C'est le test le plus important du projet. Il vérifie la propriété sur
laquelle tout repose : charger deux fois les mêmes données laisse la base
dans le même état. Sans elle, chaque rejeu et chaque recouvrement entre
exécutions produirait des doublons, et tous les agrégats seraient faux.

Ce test est ignoré si DATABASE_URL n'est pas défini, pour que la suite
unitaire reste exécutable sans service externe.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

import pytest

from vienna_vibe import db, load, quality
from vienna_vibe.models import Artist, ListeningEvent, Track, WeatherObservation

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL absent : test d'intégration ignoré.",
)

BASE = datetime(2026, 9, 19, 12, tzinfo=UTC)


def _weather(hours: int = 48) -> list[WeatherObservation]:
    return [
        WeatherObservation(
            location_code="vienna",
            observed_at=BASE - timedelta(hours=h),
            weather_code=[0, 2, 61, 95][h % 4],
            temperature_c=15.0 + (h % 10),
            humidity_pct=50 + (h % 40),
            precipitation_mm=float(h % 3),
            cloud_cover_pct=(h * 7) % 101,
            wind_speed_kmh=5.0 + (h % 20),
            is_daylight=(h % 24) < 12,
        )
        for h in range(hours)
    ]


def _listening(count: int = 30) -> list[ListeningEvent]:
    artist = Artist(artist_id="artist-001", artist_name="Artiste de test")
    return [
        ListeningEvent(
            played_at=BASE - timedelta(minutes=13 * i),
            track=Track(
                track_id=f"track-{i % 12:03d}",
                track_name=f"Titre {i % 12}",
                primary_artist=artist,
                album_name="Album de test",
                album_release_date="2025-01-01",
                duration_ms=180_000 + i * 1_000,
                is_explicit=i % 5 == 0,
                popularity=40 + (i % 50),
            ),
            context_type="playlist" if i % 2 else None,
        )
        for i in range(count)
    ]


@pytest.fixture(scope="module", autouse=True)
def schema() -> None:
    db.apply_migrations()


def _counts() -> dict[str, int]:
    row = db.fetch_one(
        """
        SELECT
            (SELECT COUNT(*) FROM core.fact_weather_hourly)  AS weather,
            (SELECT COUNT(*) FROM core.fact_listening_event) AS listening,
            (SELECT COUNT(*) FROM core.dim_track)            AS tracks,
            (SELECT COUNT(*) FROM core.dim_artist)           AS artists
        """
    )
    assert row is not None
    return {k: int(v) for k, v in row.items()}


def _load_everything() -> None:
    location_ids = db.location_ids()
    with db.connect() as conn:
        load.upsert_weather(conn, _weather(), location_ids)
        events = _listening()
        load.upsert_dimensions(conn, events)
        load.insert_listening_events(conn, events)


def test_loading_twice_leaves_identical_state() -> None:
    """La propriété centrale : f(f(x)) == f(x)."""
    _load_everything()
    after_first = _counts()

    _load_everything()
    after_second = _counts()

    assert after_first == after_second, (
        "Le second chargement a modifié les volumes : l'idempotence est cassée. "
        f"Premier passage {after_first}, second {after_second}."
    )


def test_expected_volumes() -> None:
    _load_everything()
    counts = _counts()

    assert counts["weather"] == 48
    # 30 écoutes, toutes à des instants distincts, sur 12 titres seulement.
    assert counts["listening"] == 30
    assert counts["tracks"] == 12
    assert counts["artists"] == 1


def test_natural_keys_prevent_duplicates() -> None:
    _load_everything()

    duplicates = db.fetch_all(
        """
        SELECT location_id, observed_at, COUNT(*) AS n
        FROM core.fact_weather_hourly
        GROUP BY location_id, observed_at
        HAVING COUNT(*) > 1
        """
    )

    assert duplicates == []


def test_quality_checks_pass_on_loaded_data() -> None:
    _load_everything()

    with db.connect() as conn:
        results = quality.run_checks(conn)

    failed = [r.check.name for r in results if not r.passed]
    # La fraîcheur peut échouer si les données de test sont anciennes :
    # c'est attendu, et c'est le seul contrôle qu'on tolère en échec ici.
    assert [name for name in failed if name != "weather_freshness"] == []


@pytest.mark.parametrize(
    "view",
    [
        "v_listening_with_weather",
        "v_listening_by_weather_family",
        "v_listening_by_hour",
        "v_top_artists_by_weather",
        "v_weather_coverage",
        "v_pipeline_health",
        "v_project_stats",
    ],
)
def test_marts_views_are_queryable(view: str) -> None:
    """Une vue qui ne compile pas est invisible aux tests unitaires."""
    db.fetch_all(f"SELECT * FROM marts.{view} LIMIT 5")


def test_listening_joins_to_weather() -> None:
    """La jointure horaire doit effectivement rattacher la météo.

    Si elle renvoie systématiquement NULL, c'est le signe d'un décalage de
    fuseau entre les deux sources — le défaut le plus courant, et le plus
    silencieux, de ce genre de pipeline.
    """
    _load_everything()

    row = db.fetch_one(
        """
        SELECT COUNT(*) FILTER (WHERE weather_family IS NOT NULL) AS matched,
               COUNT(*)                                           AS total
        FROM marts.v_listening_with_weather
        """
    )

    assert row is not None
    assert int(row["total"]) > 0
    assert int(row["matched"]) > 0, (
        "Aucune écoute rattachée à la météo : vérifie les fuseaux horaires des deux sources."
    )
