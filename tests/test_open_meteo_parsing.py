"""Tests de la transformation Open-Meteo.

Ces tests ne touchent ni le réseau ni la base : ils valident la logique de
repivotage et les garde-fous. C'est ce qui permet de les exécuter en
intégration continue, sans secret ni service externe.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from vienna_vibe.models import WeatherObservation
from vienna_vibe.sources import open_meteo


def _payload(**overrides: list) -> dict:
    base = {
        "time": [1758304800, 1758308400, 1758312000],
        "temperature_2m": [18.4, 17.9, 17.1],
        "relative_humidity_2m": [62, 66, 70],
        "precipitation": [0.0, 0.2, 1.4],
        "cloud_cover": [10, 45, 90],
        "wind_speed_10m": [11.2, 12.8, 15.0],
        "weather_code": [0, 2, 61],
        "is_day": [1, 1, 0],
    }
    base.update(overrides)
    return {"hourly": base}


def test_parse_pivots_columns_into_rows() -> None:
    observations = open_meteo.parse(_payload(), "vienna")

    assert len(observations) == 3
    first = observations[0]
    assert first.location_code == "vienna"
    assert first.temperature_c == pytest.approx(18.4)
    assert first.humidity_pct == 62
    assert first.weather_code == 0
    assert first.is_daylight is True
    assert observations[2].is_daylight is False


def test_parse_produces_timezone_aware_timestamps() -> None:
    """Une date naïve décalerait toutes les jointures horaires en aval."""
    observations = open_meteo.parse(_payload(), "lille")

    for obs in observations:
        assert obs.observed_at.tzinfo is not None
        assert obs.observed_at.utcoffset().total_seconds() == 0


def test_parse_truncates_on_ragged_columns() -> None:
    """Colonnes de longueurs inégales : on tronque au lieu de décaler.

    C'est le défaut de source le plus sournois : sans cette protection, les
    températures de l'heure N seraient associées à l'heure N+1.
    """
    payload = _payload(temperature_2m=[18.4, 17.9])  # une valeur manquante

    observations = open_meteo.parse(payload, "vienna")

    assert len(observations) == 2
    assert observations[0].temperature_c == pytest.approx(18.4)
    assert observations[1].temperature_c == pytest.approx(17.9)


def test_parse_handles_empty_payload() -> None:
    assert open_meteo.parse({}, "vienna") == []
    assert open_meteo.parse({"hourly": {"time": []}}, "vienna") == []


def test_parse_tolerates_null_measurements() -> None:
    """Open-Meteo renvoie parfois null sur une variable ponctuellement."""
    payload = _payload(temperature_2m=[None, 17.9, 17.1])

    observations = open_meteo.parse(payload, "vienna")

    assert observations[0].temperature_c is None
    assert observations[1].temperature_c == pytest.approx(17.9)


def test_model_rejects_impossible_humidity() -> None:
    with pytest.raises(ValidationError):
        WeatherObservation(
            location_code="vienna",
            observed_at=datetime(2026, 9, 19, 18, tzinfo=UTC),
            humidity_pct=140,
        )


def test_model_rejects_naive_timestamp() -> None:
    with pytest.raises(ValidationError):
        WeatherObservation(
            location_code="vienna",
            observed_at=datetime(2026, 9, 19, 18),  # sans fuseau
        )
