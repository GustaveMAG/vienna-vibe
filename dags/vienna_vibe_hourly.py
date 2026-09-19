"""DAG Airflow : collecte horaire météo et écoutes, puis contrôles qualité.

Deux partis pris importants.

1. Le DAG n'appelle pas de logique métier : il exécute la CLI du paquet en
   lui passant la date logique de l'exécution. Le pipeline reste donc
   testable et exécutable sans Airflow, et l'orchestrateur est remplaçable.

2. `catchup=True` et `max_active_runs=1`. Le rattrapage est activé parce que
   la météo est historisable : si le planificateur est resté éteint trois
   jours, Airflow rejouera les créneaux manquants, et l'idempotence garantit
   qu'aucun doublon n'en résultera. Une seule exécution à la fois, pour que
   deux runs ne se disputent pas les mêmes lignes.
"""

from __future__ import annotations

import pendulum
from airflow.models.dag import DAG
from airflow.operators.bash import BashOperator

DEFAULT_ARGS = {
    "owner": "gustave",
    "retries": 3,
    "retry_delay": pendulum.duration(minutes=5),
    "retry_exponential_backoff": True,
    "max_retry_delay": pendulum.duration(minutes=30),
    # Les APIs publiques tombent ponctuellement : on retente, et on n'alerte
    # que si toutes les tentatives échouent.
    "depends_on_past": False,
}

with DAG(
    dag_id="vienna_vibe_hourly",
    description="Météo horaire (Open-Meteo) et écoutes Spotify, avec contrôles qualité",
    default_args=DEFAULT_ARGS,
    schedule="0 * * * *",
    start_date=pendulum.datetime(2026, 9, 1, tz="UTC"),
    catchup=True,
    max_active_runs=1,
    dagrun_timeout=pendulum.duration(minutes=20),
    tags=["data-engineering", "portfolio"],
    doc_md=__doc__,
) as dag:
    # `data_interval_start` est la date LOGIQUE du créneau, pas l'heure
    # d'exécution réelle. C'est elle qu'on passe au pipeline : c'est ce qui
    # rend un rejeu identique à l'original.
    window = "{{ data_interval_start.in_timezone('UTC').isoformat() }}"

    ingest_weather = BashOperator(
        task_id="ingest_weather",
        bash_command=f"vienna-vibe weather --window '{window}'",
        doc_md=(
            "Collecte les observations horaires pour chaque lieu suivi. "
            "L'appel remonte deux jours d'historique : ce recouvrement "
            "rattrape automatiquement les créneaux manqués."
        ),
    )

    ingest_listening = BashOperator(
        task_id="ingest_listening",
        bash_command=f"vienna-vibe listening --window '{window}'",
        doc_md=(
            "Collecte les écoutes récentes. L'API n'en conserve que 50 : "
            "sans cette tâche horaire, les écoutes seraient définitivement "
            "perdues. C'est la contrainte qui justifie la planification."
        ),
    )

    quality_checks = BashOperator(
        task_id="quality_checks",
        bash_command=f"vienna-vibe quality --window '{window}'",
        doc_md=(
            "Neuf contrôles : fraîcheur, unicité, complétude, plages de "
            "valeurs, intégrité référentielle et volumétrie. Un échec fait "
            "tomber le DAG — mieux vaut une alerte qu'un tableau de bord faux."
        ),
    )

    # Les deux collectes sont indépendantes et tournent en parallèle ;
    # les contrôles portent sur l'état consolidé, donc ils attendent les deux.
    [ingest_weather, ingest_listening] >> quality_checks
