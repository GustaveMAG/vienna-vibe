"""Contrôles de qualité de données.

Un pipeline qui tourne sans erreur ne garantit rien : il peut charger
fidèlement des données fausses. Ces contrôles s'exécutent après chaque
chargement et font échouer le DAG s'ils ne passent pas. Un échec bruyant
vaut mieux qu'un tableau de bord silencieusement faux.

Cinq familles de contrôles, qui couvrent les défauts réellement observés
en production :
  fraîcheur     — la donnée arrive-t-elle encore ?
  unicité       — la clé naturelle tient-elle ?
  complétude    — les colonnes critiques sont-elles renseignées ?
  plages        — les valeurs sont-elles physiquement plausibles ?
  intégrité     — chaque fait pointe-t-il vers une dimension existante ?
  volumétrie    — le volume du jour est-il cohérent avec l'historique ?
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import psycopg

from .config import get_settings

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Check:
    name: str
    family: str
    sql: str
    # Le SQL renvoie une colonne `violations` : 0 signifie contrôle réussi.
    description: str


@dataclass(frozen=True)
class CheckResult:
    check: Check
    violations: int

    @property
    def passed(self) -> bool:
        return self.violations == 0


def build_checks(freshness_max_age_hours: int) -> list[Check]:
    return [
        Check(
            name="weather_freshness",
            family="fraîcheur",
            description=(
                f"Une observation météo de moins de {freshness_max_age_hours} h doit exister."
            ),
            sql=f"""
                SELECT CASE
                    WHEN MAX(observed_at) IS NULL THEN 1
                    WHEN MAX(observed_at) < now() - INTERVAL '{freshness_max_age_hours} hours'
                        THEN 1
                    ELSE 0
                END AS violations
                FROM core.fact_weather_hourly
            """,
        ),
        Check(
            name="weather_uniqueness",
            family="unicité",
            description="Aucun doublon sur la clé naturelle (lieu, heure).",
            sql="""
                SELECT COUNT(*) AS violations FROM (
                    SELECT location_id, observed_at
                    FROM core.fact_weather_hourly
                    GROUP BY location_id, observed_at
                    HAVING COUNT(*) > 1
                ) d
            """,
        ),
        Check(
            name="listening_uniqueness",
            family="unicité",
            description="Aucun doublon sur la clé naturelle (instant, titre).",
            sql="""
                SELECT COUNT(*) AS violations FROM (
                    SELECT played_at, track_id
                    FROM core.fact_listening_event
                    GROUP BY played_at, track_id
                    HAVING COUNT(*) > 1
                ) d
            """,
        ),
        Check(
            name="weather_completeness",
            family="complétude",
            description="La température est renseignée sur les 48 dernières heures.",
            sql="""
                SELECT COUNT(*) AS violations
                FROM core.fact_weather_hourly
                WHERE observed_at >= now() - INTERVAL '48 hours'
                  AND temperature_c IS NULL
            """,
        ),
        Check(
            name="weather_plausible_ranges",
            family="plages",
            description=(
                "Température entre -50 et 55 °C, humidité et couverture "
                "nuageuse entre 0 et 100 %."
            ),
            sql="""
                SELECT COUNT(*) AS violations
                FROM core.fact_weather_hourly
                WHERE (temperature_c   IS NOT NULL AND temperature_c   NOT BETWEEN -50 AND 55)
                   OR (humidity_pct    IS NOT NULL AND humidity_pct    NOT BETWEEN 0 AND 100)
                   OR (cloud_cover_pct IS NOT NULL AND cloud_cover_pct NOT BETWEEN 0 AND 100)
                   OR (precipitation_mm IS NOT NULL AND precipitation_mm < 0)
            """,
        ),
        Check(
            name="listening_not_in_future",
            family="plages",
            description="Aucune écoute datée dans le futur.",
            sql="""
                SELECT COUNT(*) AS violations
                FROM core.fact_listening_event
                WHERE played_at > now() + INTERVAL '5 minutes'
            """,
        ),
        Check(
            name="listening_referential_integrity",
            family="intégrité",
            description="Chaque écoute référence un titre présent en dimension.",
            sql="""
                SELECT COUNT(*) AS violations
                FROM core.fact_listening_event e
                LEFT JOIN core.dim_track t ON t.track_id = e.track_id
                WHERE t.track_id IS NULL
            """,
        ),
        Check(
            name="weather_code_referential_integrity",
            family="intégrité",
            description="Chaque code météo existe dans la dimension WMO.",
            sql="""
                SELECT COUNT(*) AS violations
                FROM core.fact_weather_hourly w
                LEFT JOIN core.dim_weather_condition c ON c.weather_code = w.weather_code
                WHERE w.weather_code IS NOT NULL AND c.weather_code IS NULL
            """,
        ),
        Check(
            name="weather_volume_anomaly",
            family="volumétrie",
            description=(
                "Le volume des dernières 24 h ne s'effondre pas sous la moitié "
                "de la moyenne des sept jours précédents."
            ),
            sql="""
                WITH recent AS (
                    SELECT COUNT(*)::NUMERIC AS n
                    FROM core.fact_weather_hourly
                    WHERE observed_at >= now() - INTERVAL '24 hours'
                ),
                baseline AS (
                    SELECT COUNT(*)::NUMERIC / 7 AS n
                    FROM core.fact_weather_hourly
                    WHERE observed_at >= now() - INTERVAL '8 days'
                      AND observed_at <  now() - INTERVAL '24 hours'
                )
                SELECT CASE
                    -- Historique trop court pour conclure : on ne crie pas au loup.
                    WHEN (SELECT n FROM baseline) < 24 THEN 0
                    WHEN (SELECT n FROM recent) < 0.5 * (SELECT n FROM baseline) THEN 1
                    ELSE 0
                END AS violations
            """,
        ),
    ]


def run_checks(conn: psycopg.Connection) -> list[CheckResult]:
    settings = get_settings()
    results: list[CheckResult] = []

    for check in build_checks(settings.freshness_max_age_hours):
        row = conn.execute(check.sql).fetchone()
        violations = int(row["violations"]) if row else 1
        result = CheckResult(check=check, violations=violations)
        results.append(result)

        if result.passed:
            log.info("[OK]     %-34s %s", check.name, check.family)
        else:
            log.error(
                "[ÉCHEC]  %-34s %s — %d violation(s) : %s",
                check.name,
                check.family,
                violations,
                check.description,
            )
    return results


class DataQualityError(RuntimeError):
    """Au moins un contrôle de qualité a échoué."""


def assert_quality(conn: psycopg.Connection) -> list[CheckResult]:
    """Exécute les contrôles et lève une exception si l'un échoue."""
    results = run_checks(conn)
    failed = [r for r in results if not r.passed]
    if failed:
        raise DataQualityError(
            "Contrôles de qualité en échec : "
            + ", ".join(f"{r.check.name} ({r.violations})" for r in failed)
        )
    return results
