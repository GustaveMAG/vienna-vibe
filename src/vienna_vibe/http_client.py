"""Client HTTP avec politique de reprise.

Une API publique échoue régulièrement pour des raisons passagères : limite
de débit, coupure réseau, 502 d'un répartiteur de charge. Un pipeline qui
tourne sans surveillance doit encaisser ces erreurs tout seul, sinon chaque
incident réseau devient une alerte à traiter à la main.

Politique retenue :
  - on retente les erreurs passagères (429, 5xx, timeouts, erreurs réseau) ;
  - on ne retente jamais les erreurs définitives (400, 401, 403, 404) :
    réessayer un jeton invalide ne fera que répéter l'échec ;
  - attente exponentielle, et respect de l'en-tête Retry-After quand l'API
    en fournit un.
"""

from __future__ import annotations

import logging
import random
import time
from typing import Any

import httpx

log = logging.getLogger(__name__)

RETRYABLE_STATUS = {408, 425, 429, 500, 502, 503, 504}
FATAL_STATUS = {400, 401, 403, 404, 422}


class HttpError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def _sleep_for(attempt: int, retry_after: str | None) -> float:
    if retry_after:
        try:
            return min(float(retry_after), 60.0)
        except ValueError:
            pass
    # Attente exponentielle avec bruit, pour éviter que plusieurs tâches
    # relancées en même temps ne retapent l'API en rythme synchronisé.
    return min(2.0**attempt + random.uniform(0, 0.5), 30.0)


def request_json(
    method: str,
    url: str,
    *,
    timeout_s: float,
    max_retries: int,
    **kwargs: Any,
) -> tuple[int, dict[str, Any]]:
    """Exécute une requête et renvoie (code HTTP, corps JSON décodé)."""
    last_error: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            with httpx.Client(timeout=timeout_s, follow_redirects=True) as client:
                response = client.request(method, url, **kwargs)

            if response.status_code in FATAL_STATUS:
                raise HttpError(
                    f"{method} {url} a renvoyé {response.status_code} "
                    f"(erreur définitive, pas de reprise) : {response.text[:300]}",
                    status_code=response.status_code,
                )

            if response.status_code in RETRYABLE_STATUS:
                raise httpx.HTTPStatusError(
                    f"statut passager {response.status_code}",
                    request=response.request,
                    response=response,
                )

            response.raise_for_status()
            return response.status_code, response.json()

        except HttpError:
            raise

        except (httpx.HTTPStatusError, httpx.RequestError) as exc:
            last_error = exc
            if attempt >= max_retries:
                break
            retry_after = None
            if isinstance(exc, httpx.HTTPStatusError):
                retry_after = exc.response.headers.get("Retry-After")
            delay = _sleep_for(attempt, retry_after)
            log.warning(
                "Tentative %d/%d échouée sur %s (%s) ; nouvelle tentative dans %.1fs",
                attempt + 1,
                max_retries + 1,
                url,
                exc,
                delay,
            )
            time.sleep(delay)

    raise HttpError(
        f"{method} {url} a échoué après {max_retries + 1} tentatives : {last_error}"
    )
