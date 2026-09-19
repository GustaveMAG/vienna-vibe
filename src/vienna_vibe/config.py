"""Configuration du pipeline, lue exclusivement depuis l'environnement.

Aucun secret n'est écrit dans le code ni dans le dépôt. Le fichier
`.env.example` liste les variables attendues ; `.env` est dans le .gitignore.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache


class ConfigError(RuntimeError):
    """Une variable d'environnement obligatoire est absente ou invalide."""


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ConfigError(
            f"La variable d'environnement {name} est absente. "
            f"Copie .env.example vers .env et renseigne-la."
        )
    return value


def _optional(name: str, default: str) -> str:
    return os.environ.get(name, "").strip() or default


@dataclass(frozen=True)
class SpotifyConfig:
    client_id: str
    client_secret: str
    refresh_token: str
    token_url: str = "https://accounts.spotify.com/api/token"
    api_base: str = "https://api.spotify.com/v1"
    # L'API ne renvoie que les 50 dernières écoutes : c'est cette limite
    # qui impose une collecte horaire plutôt que quotidienne.
    recently_played_limit: int = 50


@dataclass(frozen=True)
class OpenMeteoConfig:
    api_base: str = "https://api.open-meteo.com/v1/forecast"
    # Variables horaires demandées à l'API, dans cet ordre.
    hourly_variables: tuple[str, ...] = (
        "temperature_2m",
        "relative_humidity_2m",
        "precipitation",
        "cloud_cover",
        "wind_speed_10m",
        "weather_code",
        "is_day",
    )
    # Marge d'historique récupérée à chaque appel. Elle crée un recouvrement
    # volontaire entre exécutions : si un run est tombé, le suivant rattrape
    # les heures manquantes sans intervention.
    past_days: int = 2


@dataclass(frozen=True)
class Settings:
    database_url: str
    spotify: SpotifyConfig
    open_meteo: OpenMeteoConfig = field(default_factory=OpenMeteoConfig)
    http_timeout_s: float = 20.0
    http_max_retries: int = 4
    # Seuil du contrôle de fraîcheur : au-delà, la donnée est considérée périmée.
    freshness_max_age_hours: int = 3


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Charge la configuration une seule fois par processus."""
    return Settings(
        database_url=_required("DATABASE_URL"),
        spotify=SpotifyConfig(
            client_id=_required("SPOTIFY_CLIENT_ID"),
            client_secret=_required("SPOTIFY_CLIENT_SECRET"),
            refresh_token=_required("SPOTIFY_REFRESH_TOKEN"),
        ),
        http_timeout_s=float(_optional("HTTP_TIMEOUT_S", "20")),
        http_max_retries=int(_optional("HTTP_MAX_RETRIES", "4")),
        freshness_max_age_hours=int(_optional("FRESHNESS_MAX_AGE_HOURS", "3")),
    )
