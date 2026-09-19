"""Accès à PostgreSQL et application des migrations."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row

from .config import get_settings

log = logging.getLogger(__name__)

SQL_DIR = Path(__file__).resolve().parents[2] / "sql"


@contextmanager
def connect() -> Iterator[psycopg.Connection]:
    """Ouvre une connexion transactionnelle.

    Le bloc `with` valide en sortie normale et annule sur exception : une
    étape qui échoue à mi-parcours ne laisse jamais la base dans un état
    partiel.
    """
    settings = get_settings()
    with psycopg.connect(settings.database_url, row_factory=dict_row) as conn:
        yield conn


def apply_migrations() -> list[str]:
    """Exécute les fichiers de sql/ dans l'ordre alphabétique.

    Les scripts sont écrits pour être rejouables (CREATE ... IF NOT EXISTS,
    CREATE OR REPLACE VIEW, ON CONFLICT DO NOTHING), donc les relancer est
    sans effet de bord. Suffisant à cette échelle ; au-delà, un vrai outil
    de migration versionnée serait justifié.
    """
    applied: list[str] = []
    files = sorted(SQL_DIR.glob("*.sql"))
    if not files:
        raise FileNotFoundError(f"Aucun fichier SQL trouvé dans {SQL_DIR}")

    with connect() as conn:
        for path in files:
            log.info("Application de la migration %s", path.name)
            conn.execute(path.read_text(encoding="utf-8"))
            applied.append(path.name)
    return applied


def fetch_all(sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    with connect() as conn:
        cur = conn.execute(sql, params or {})
        return list(cur.fetchall())


def fetch_one(sql: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
    with connect() as conn:
        cur = conn.execute(sql, params or {})
        return cur.fetchone()


def location_ids() -> dict[str, int]:
    """Retourne la correspondance code de lieu -> identifiant technique."""
    rows = fetch_all("SELECT location_code, location_id FROM core.dim_location")
    return {row["location_code"]: row["location_id"] for row in rows}


def locations() -> list[dict[str, Any]]:
    return fetch_all(
        """
        SELECT location_id, location_code, label, latitude, longitude, timezone
        FROM core.dim_location
        ORDER BY location_code
        """
    )
