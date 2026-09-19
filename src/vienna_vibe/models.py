"""Modèles de données validés.

Les payloads d'API sont du JSON non fiable : champs absents, types
inattendus, valeurs hors bornes. On les valide ici, une fois, à l'entrée du
pipeline. Tout ce qui circule en aval est donc garanti conforme, et les
erreurs de source sont détectées au plus tôt plutôt qu'au moment du INSERT.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class WeatherObservation(BaseModel):
    """Une observation météo, pour un lieu et une heure."""

    model_config = ConfigDict(frozen=True)

    location_code: str
    observed_at: datetime
    weather_code: int | None = Field(default=None, ge=0, le=99)
    temperature_c: float | None = Field(default=None, ge=-80, le=65)
    humidity_pct: int | None = Field(default=None, ge=0, le=100)
    precipitation_mm: float | None = Field(default=None, ge=0)
    cloud_cover_pct: int | None = Field(default=None, ge=0, le=100)
    wind_speed_kmh: float | None = Field(default=None, ge=0)
    is_daylight: bool | None = None

    @field_validator("observed_at")
    @classmethod
    def must_be_timezone_aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError(
                "observed_at doit porter un fuseau horaire. Une date naïve "
                "décale silencieusement toutes les jointures horaires."
            )
        return v


class Artist(BaseModel):
    model_config = ConfigDict(frozen=True)

    artist_id: str = Field(min_length=1)
    artist_name: str = Field(min_length=1)


class Track(BaseModel):
    model_config = ConfigDict(frozen=True)

    track_id: str = Field(min_length=1)
    track_name: str = Field(min_length=1)
    primary_artist: Artist | None = None
    album_name: str | None = None
    album_release_date: str | None = None
    duration_ms: int | None = Field(default=None, gt=0)
    is_explicit: bool | None = None
    popularity: int | None = Field(default=None, ge=0, le=100)


class ListeningEvent(BaseModel):
    """Une écoute : un titre joué à un instant précis.

    Le couple (played_at, track_id) est la clé naturelle. Un événement
    d'écoute est immuable, d'où le `frozen=True`.
    """

    model_config = ConfigDict(frozen=True)

    played_at: datetime
    track: Track
    context_type: str | None = None

    @field_validator("played_at")
    @classmethod
    def must_be_timezone_aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("played_at doit porter un fuseau horaire.")
        return v


class StepResult(BaseModel):
    """Compte rendu d'une étape, écrit dans core.pipeline_run."""

    step: str
    rows_read: int = 0
    rows_written: int = 0
    rows_skipped: int = 0
    duration_ms: int = 0
    status: str = "success"
    message: str | None = None
