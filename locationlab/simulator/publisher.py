"""
Publicador HTTP.
Envía eventos a la API (propia o de terceros) usando httpx con reintentos.
Soporta endpoint unitario y por lotes.
"""
from __future__ import annotations

import logging
from datetime import datetime

import httpx

from locationlab.core.models import LocationEvent

logger = logging.getLogger(__name__)

# Cabeceras que simulan un cliente móvil Android real.
# Ajústalas según las cabeceras reales que usa Tribbu.
_DEFAULT_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "User-Agent": "Tribbu/3.2.1 (Android 13; SDK 33; arm64-v8a)",
    "X-App-Version": "3.2.1",
    "X-Platform": "android",
}


class ApiPublisher:
    """
    Publica eventos de localización hacia la API objetivo.

    Parámetros:
    - base_url:      URL base de la API (ej. "http://localhost:8080" o URL de Tribbu)
    - use_batch:     si True usa /api/locations/batch; si False /api/locations
    - timeout:       timeout por petición en segundos
    - max_retries:   número máximo de reintentos en fallo transitorio
    - extra_headers: cabeceras adicionales (tokens, cookies de sesión, etc.)
    """

    def __init__(
        self,
        base_url: str,
        use_batch: bool = True,
        timeout: float = 10.0,
        max_retries: int = 2,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._use_batch = use_batch
        self._timeout = timeout
        self._max_retries = max_retries
        headers = {**_DEFAULT_HEADERS, **(extra_headers or {})}
        self._client = httpx.Client(headers=headers, timeout=timeout)

    # ------------------------------------------------------------------

    def send(self, event: LocationEvent) -> bool:
        payload = _event_to_dict(event)
        return self._post(f"{self._base_url}/api/locations", payload)

    def send_batch(self, events: list[LocationEvent]) -> bool:
        payload = {"events": [_event_to_dict(e) for e in events]}
        return self._post(f"{self._base_url}/api/locations/batch", payload)

    def send_events(self, events: list[LocationEvent], batch_size: int = 20) -> dict:
        """
        Envía *events* en lotes de *batch_size*.
        Devuelve un resumen: {sent, failed, batches}.
        """
        sent = 0
        failed = 0
        batches = 0

        for i in range(0, len(events), batch_size):
            chunk = events[i : i + batch_size]
            if self._use_batch:
                ok = self.send_batch(chunk)
            else:
                ok = all(self.send(e) for e in chunk)

            batches += 1
            if ok:
                sent += len(chunk)
            else:
                failed += len(chunk)

        return {"sent": sent, "failed": failed, "batches": batches}

    def close(self) -> None:
        self._client.close()

    # ------------------------------------------------------------------

    def _post(self, url: str, payload: dict) -> bool:
        for attempt in range(self._max_retries + 1):
            try:
                r = self._client.post(url, json=payload)
                if r.status_code in (200, 201, 202):
                    return True
                logger.warning(
                    "POST %s → HTTP %s (intento %d/%d)",
                    url,
                    r.status_code,
                    attempt + 1,
                    self._max_retries + 1,
                )
            except httpx.RequestError as exc:
                logger.warning(
                    "Error de conexión %s (intento %d/%d): %s",
                    url,
                    attempt + 1,
                    self._max_retries + 1,
                    exc,
                )
        return False


def _event_to_dict(event: LocationEvent) -> dict:
    return {
        "device_id": event.device_id,
        "latitude": event.latitude,
        "longitude": event.longitude,
        "timestamp_utc": event.timestamp_utc.isoformat(),
        "accuracy_meters": event.accuracy_meters,
        "speed_meters_per_second": event.speed_meters_per_second,
        "bearing_degrees": event.bearing_degrees,
    }
