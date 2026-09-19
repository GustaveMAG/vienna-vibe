"""Source : Spotify Web API, historique d'écoute récent.

Choix d'endpoint. En novembre 2024, Spotify a restreint aux applications
historiques les endpoints `audio-features`, `audio-analysis` et
`recommendations`. Les descripteurs musicaux (énergie, tempo, valence) ne
sont donc plus accessibles à une application créée aujourd'hui.

Ce pipeline s'appuie sur `/me/player/recently-played`, toujours disponible,
qui renvoie les écoutes réelles. C'est une meilleure base : au lieu de
descripteurs calculés par un tiers, on accumule un historique de
comportement, qu'on croise ensuite avec la météo.

Conséquence opérationnelle majeure : l'endpoint ne renvoie que les
50 dernières écoutes. Passé ce volume, les plus anciennes sont perdues
définitivement. C'est ce qui impose une collecte horaire — la planification
n'est pas décorative ici, elle est la condition de l'existence du jeu de
données.
"""

from __future__ import annotations

import base64
import logging
from datetime import UTC, datetime
from typing import Any

from ..config import get_settings
from ..http_client import request_json
from ..models import Artist, ListeningEvent, Track

log = logging.getLogger(__name__)

SOURCE_NAME = "spotify_recently_played"
MAX_PAGES = 10  # garde-fou : évite une boucle infinie si l'API renvoie un curseur constant


def get_access_token() -> str:
    """Échange le jeton de rafraîchissement contre un jeton d'accès.

    Les jetons d'accès Spotify expirent au bout d'une heure ; on en demande
    donc un neuf à chaque exécution plutôt que d'en stocker un périmé.
    """
    settings = get_settings()
    basic = base64.b64encode(
        f"{settings.spotify.client_id}:{settings.spotify.client_secret}".encode()
    ).decode()

    _, body = request_json(
        "POST",
        settings.spotify.token_url,
        headers={
            "Authorization": f"Basic {basic}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={
            "grant_type": "refresh_token",
            "refresh_token": settings.spotify.refresh_token,
        },
        timeout_s=settings.http_timeout_s,
        max_retries=settings.http_max_retries,
    )
    token = body.get("access_token")
    if not token:
        raise RuntimeError(
            "Spotify n'a pas renvoyé d'access_token. Vérifie SPOTIFY_REFRESH_TOKEN "
            "et le scope user-read-recently-played."
        )
    return str(token)


def fetch_raw(after_ms: int | None = None) -> tuple[int, dict[str, Any]]:
    """Récupère les écoutes récentes, en suivant la pagination par curseur.

    `after_ms` borne la collecte aux écoutes postérieures à cet instant.
    On le positionne volontairement en retrait de la dernière écoute connue :
    ce recouvrement garantit qu'aucune écoute ne tombe entre deux runs, et
    les doublons sont absorbés par la clé naturelle à l'insertion.
    """
    settings = get_settings()
    token = get_access_token()
    headers = {"Authorization": f"Bearer {token}"}

    url = f"{settings.spotify.api_base}/me/player/recently-played"
    params: dict[str, str] = {"limit": str(settings.spotify.recently_played_limit)}
    if after_ms is not None:
        params["after"] = str(after_ms)

    all_items: list[dict[str, Any]] = []
    status = 200
    next_url: str | None = None

    for page in range(MAX_PAGES):
        if next_url:
            status, body = request_json(
                "GET",
                next_url,
                headers=headers,
                timeout_s=settings.http_timeout_s,
                max_retries=settings.http_max_retries,
            )
        else:
            status, body = request_json(
                "GET",
                url,
                headers=headers,
                params=params,
                timeout_s=settings.http_timeout_s,
                max_retries=settings.http_max_retries,
            )

        items = body.get("items") or []
        all_items.extend(items)
        next_url = body.get("next")
        if not next_url or not items:
            break
        log.info("Page Spotify %d : %d écoutes, suite disponible", page + 1, len(items))

    return status, {"items": all_items}


def _parse_played_at(value: str) -> datetime:
    """Spotify renvoie un ISO 8601 en UTC, suffixé par Z."""
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def parse(payload: dict[str, Any]) -> list[ListeningEvent]:
    """Transforme le payload en événements validés.

    Les éléments illisibles sont ignorés et journalisés : une écoute
    malformée ne doit pas faire tomber la collecte des quarante-neuf autres.
    """
    events: list[ListeningEvent] = []
    for item in payload.get("items") or []:
        try:
            track_raw = item.get("track") or {}
            artists_raw = track_raw.get("artists") or []
            album_raw = track_raw.get("album") or {}
            context_raw = item.get("context") or {}

            primary_artist = None
            if artists_raw:
                first = artists_raw[0]
                if first.get("id") and first.get("name"):
                    primary_artist = Artist(
                        artist_id=str(first["id"]),
                        artist_name=str(first["name"]),
                    )

            events.append(
                ListeningEvent(
                    played_at=_parse_played_at(str(item["played_at"])),
                    track=Track(
                        track_id=str(track_raw["id"]),
                        track_name=str(track_raw["name"]),
                        primary_artist=primary_artist,
                        album_name=album_raw.get("name"),
                        album_release_date=album_raw.get("release_date"),
                        duration_ms=track_raw.get("duration_ms"),
                        is_explicit=track_raw.get("explicit"),
                        popularity=track_raw.get("popularity"),
                    ),
                    context_type=context_raw.get("type"),
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            log.warning("Écoute ignorée, payload inexploitable : %s", exc)

    # Les doublons internes à un même payload (une écoute renvoyée sur deux
    # pages qui se recouvrent) sont éliminés ici, avant d'atteindre la base.
    unique: dict[tuple[datetime, str], ListeningEvent] = {}
    for event in events:
        unique[(event.played_at, event.track.track_id)] = event
    return sorted(unique.values(), key=lambda e: e.played_at)
