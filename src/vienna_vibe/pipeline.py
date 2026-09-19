"""Orchestration interne et interface en ligne de commande.

Le pipeline est paramétré par un créneau logique (`--window`), pas par
« maintenant ». C'est ce qui rend le rejeu possible : relancer le créneau
de mardi 14 h retraite exactement les mêmes données et aboutit au même
état final. Airflow ne fait que passer sa date d'exécution à cette CLI —
l'orchestrateur est donc interchangeable, et le pipeline reste testable
sans lui.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import UTC, datetime, timedelta

from . import db, load, quality
from .models import StepResult
from .sources import open_meteo, spotify

log = logging.getLogger("vienna_vibe")

# Recouvrement appliqué à la collecte Spotify : on redemande une marge
# avant la dernière écoute connue, pour qu'un run manqué soit rattrapé.
SPOTIFY_OVERLAP = timedelta(hours=3)


def _configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s : %(message)s",
        stream=sys.stdout,
    )


def _floor_to_hour(moment: datetime) -> datetime:
    return moment.astimezone(UTC).replace(minute=0, second=0, microsecond=0)


def ingest_weather(window_start: datetime) -> StepResult:
    """Collecte et charge la météo horaire, pour tous les lieux suivis."""
    started = time.monotonic()
    total_read = 0
    total_written = 0

    with db.connect() as conn:
        location_ids = {row["location_code"]: row["location_id"] for row in db.locations()}
        for location in db.locations():
            status, payload = open_meteo.fetch_raw(
                latitude=float(location["latitude"]),
                longitude=float(location["longitude"]),
            )
            load.save_raw_payload(
                conn,
                source=open_meteo.SOURCE_NAME,
                window_start=window_start,
                http_status=status,
                body=payload,
            )
            observations = open_meteo.parse(payload, location["location_code"])
            total_read += len(observations)
            total_written += load.upsert_weather(conn, observations, location_ids)
            log.info(
                "Météo %-8s : %d heures reçues et chargées",
                location["location_code"],
                len(observations),
            )

        duration_ms = int((time.monotonic() - started) * 1000)
        result = StepResult(
            step="ingest_weather",
            rows_read=total_read,
            rows_written=total_written,
            duration_ms=duration_ms,
        )
        load.log_step(
            conn,
            window_start,
            result.step,
            result.status,
            rows_read=result.rows_read,
            rows_written=result.rows_written,
            duration_ms=result.duration_ms,
        )
    return result


def ingest_listening(window_start: datetime) -> StepResult:
    """Collecte et charge les écoutes récentes."""
    started = time.monotonic()

    with db.connect() as conn:
        last_known = load.last_listening_timestamp(conn)
        after_ms: int | None = None
        if last_known is not None:
            # Recouvrement volontaire : on remonte avant la dernière écoute
            # connue plutôt que de repartir pile à sa seconde.
            after_ms = int((last_known - SPOTIFY_OVERLAP).timestamp() * 1000)
            log.info(
                "Dernière écoute connue : %s ; collecte à partir de %s",
                last_known.isoformat(),
                (last_known - SPOTIFY_OVERLAP).isoformat(),
            )
        else:
            log.info("Aucune écoute en base : première collecte, sans borne basse.")

        status, payload = spotify.fetch_raw(after_ms=after_ms)
        load.save_raw_payload(
            conn,
            source=spotify.SOURCE_NAME,
            window_start=window_start,
            http_status=status,
            body=payload,
        )

        events = spotify.parse(payload)
        load.upsert_dimensions(conn, events)
        inserted, skipped = load.insert_listening_events(conn, events)

        log.info(
            "Écoutes : %d reçues, %d nouvelles, %d déjà connues",
            len(events),
            inserted,
            skipped,
        )
        if events and inserted == len(events):
            log.warning(
                "Aucun recouvrement détecté : toutes les écoutes reçues étaient "
                "nouvelles. La collecte est peut-être trop espacée, et des "
                "écoutes ont pu être perdues (l'API n'en garde que 50)."
            )

        duration_ms = int((time.monotonic() - started) * 1000)
        result = StepResult(
            step="ingest_listening",
            rows_read=len(events),
            rows_written=inserted,
            rows_skipped=skipped,
            duration_ms=duration_ms,
        )
        load.log_step(
            conn,
            window_start,
            result.step,
            result.status,
            rows_read=result.rows_read,
            rows_written=result.rows_written,
            rows_skipped=result.rows_skipped,
            duration_ms=result.duration_ms,
        )
    return result


def run_quality(window_start: datetime) -> StepResult:
    """Exécute les contrôles de qualité et échoue si l'un ne passe pas."""
    started = time.monotonic()

    with db.connect() as conn:
        try:
            results = quality.assert_quality(conn)
            duration_ms = int((time.monotonic() - started) * 1000)
            result = StepResult(
                step="quality_checks",
                rows_read=len(results),
                rows_written=0,
                duration_ms=duration_ms,
                message=f"{len(results)} contrôles passés",
            )
        except quality.DataQualityError as exc:
            duration_ms = int((time.monotonic() - started) * 1000)
            result = StepResult(
                step="quality_checks",
                status="failed",
                duration_ms=duration_ms,
                message=str(exc),
            )
            load.log_step(
                conn,
                window_start,
                result.step,
                result.status,
                duration_ms=result.duration_ms,
                message=result.message,
            )
            raise

        load.log_step(
            conn,
            window_start,
            result.step,
            result.status,
            rows_read=result.rows_read,
            duration_ms=result.duration_ms,
            message=result.message,
        )
    return result


def run_all(window_start: datetime) -> list[StepResult]:
    return [
        ingest_weather(window_start),
        ingest_listening(window_start),
        run_quality(window_start),
    ]


def print_stats() -> None:
    row = db.fetch_one("SELECT * FROM marts.v_project_stats")
    if not row:
        print("Aucune statistique disponible.")
        return
    print("\n--- Vienna Vibe : état du jeu de données ---")
    labels = {
        "weather_observations": "Observations météo",
        "listening_events": "Écoutes enregistrées",
        "distinct_tracks": "Titres distincts",
        "distinct_artists": "Artistes distincts",
        "days_covered": "Jours couverts",
        "history_starts_at": "Début de l'historique",
        "history_ends_at": "Fin de l'historique",
        "successful_steps": "Étapes réussies",
        "failed_steps": "Étapes en échec",
    }
    for key, label in labels.items():
        print(f"{label:<26} {row.get(key)}")
    print()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="vienna-vibe",
        description="Pipeline météo et écoutes musicales.",
    )
    parser.add_argument(
        "command",
        choices=["migrate", "weather", "listening", "quality", "run", "stats"],
        help=(
            "migrate : applique le schéma · weather/listening : une seule source · "
            "quality : contrôles seuls · run : tout le pipeline · stats : chiffres du projet"
        ),
    )
    parser.add_argument(
        "--window",
        help=(
            "Créneau logique au format ISO 8601, par exemple 2026-09-19T18:00:00Z. "
            "Par défaut : l'heure courante arrondie à l'heure."
        ),
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    _configure_logging(args.verbose)

    window_start = (
        _floor_to_hour(datetime.fromisoformat(args.window.replace("Z", "+00:00")))
        if args.window
        else _floor_to_hour(datetime.now(UTC))
    )

    try:
        if args.command == "migrate":
            applied = db.apply_migrations()
            log.info("Migrations appliquées : %s", ", ".join(applied))
        elif args.command == "weather":
            ingest_weather(window_start)
        elif args.command == "listening":
            ingest_listening(window_start)
        elif args.command == "quality":
            run_quality(window_start)
        elif args.command == "run":
            log.info("Exécution du pipeline pour le créneau %s", window_start.isoformat())
            run_all(window_start)
            log.info("Pipeline terminé avec succès.")
        elif args.command == "stats":
            print_stats()
    except Exception as exc:
        log.error("Échec : %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
