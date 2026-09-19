"""Source : Open-Meteo (météo horaire, gratuite, sans clé d'API)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from ..config import get_settings
from ..http_client import request_json
from ..models import WeatherObservation

log = logging.getLogger(__name__)

SOURCE_NAME = "open_meteo"


def fetch_raw(latitude: float, longitude: float) -> tuple[int, dict[str, Any]]:
    """Interroge l'API et renvoie le payload brut.

    `timeformat=unixtime` est un choix délibéré : l'API peut sinon renvoyer
    des horodatages sans décalage explicite, ce qui est la porte ouverte aux
    erreurs d'une heure au changement d'heure. Un entier en secondes UTC ne
    laisse aucune place à l'interprétation.
    """
    settings = get_settings()
    params = {
        "latitude": f"{latitude}",
        "longitude": f"{longitude}",
        "hourly": ",".join(settings.open_meteo.hourly_variables),
        "timeformat": "unixtime",
        "timezone": "UTC",
        "past_days": str(settings.open_meteo.past_days),
        "forecast_days": "1",
    }
    return request_json(
        "GET",
        settings.open_meteo.api_base,
        params=params,
        timeout_s=settings.http_timeout_s,
        max_retries=settings.http_max_retries,
    )


def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return round(float(value))
    except (TypeError, ValueError):
        return None


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse(payload: dict[str, Any], location_code: str) -> list[WeatherObservation]:
    """Transforme le payload en observations validées.

    Open-Meteo renvoie des *colonnes* parallèles (une liste par variable) et
    non des lignes. On les repivote, en se protégeant contre des listes de
    longueurs différentes, ce qui décalerait silencieusement les valeurs.
    """
    hourly = payload.get("hourly") or {}
    times = hourly.get("time") or []
    if not times:
        log.warning("Payload Open-Meteo sans série horaire pour %s", location_code)
        return []

    columns = {
        "temperature_2m": hourly.get("temperature_2m") or [],
        "relative_humidity_2m": hourly.get("relative_humidity_2m") or [],
        "precipitation": hourly.get("precipitation") or [],
        "cloud_cover": hourly.get("cloud_cover") or [],
        "wind_speed_10m": hourly.get("wind_speed_10m") or [],
        "weather_code": hourly.get("weather_code") or [],
        "is_day": hourly.get("is_day") or [],
    }

    # Toute colonne plus courte que l'axe temps est une anomalie de source :
    # on tronque sur la longueur commune plutôt que d'aligner à l'aveugle.
    usable = min([len(times)] + [len(v) for v in columns.values() if v])
    if usable < len(times):
        log.warning(
            "Colonnes Open-Meteo de longueurs inégales pour %s : %d heures exploitables sur %d",
            location_code,
            usable,
            len(times),
        )

    def col(name: str, index: int) -> Any:
        values = columns[name]
        return values[index] if index < len(values) else None

    observations: list[WeatherObservation] = []
    for i in range(usable):
        is_day = _as_int(col("is_day", i))
        observations.append(
            WeatherObservation(
                location_code=location_code,
                observed_at=datetime.fromtimestamp(int(times[i]), tz=UTC),
                weather_code=_as_int(col("weather_code", i)),
                temperature_c=_as_float(col("temperature_2m", i)),
                humidity_pct=_as_int(col("relative_humidity_2m", i)),
                precipitation_mm=_as_float(col("precipitation", i)),
                cloud_cover_pct=_as_int(col("cloud_cover", i)),
                wind_speed_kmh=_as_float(col("wind_speed_10m", i)),
                is_daylight=None if is_day is None else bool(is_day),
            )
        )
    return observations
