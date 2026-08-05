"""
API REST – punto de entrada FastAPI.

Ejecutar:
    uvicorn locationlab.api.main:app --reload --port 8080

Swagger UI disponible en:
    http://localhost:8080/docs
"""
from __future__ import annotations

import uuid
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse

from locationlab.api import database as db
from locationlab.core.group_detector import GroupDetector, GroupDetectorConfig, Sample
from locationlab.core.models import (
    DeviceInfo,
    GroupInfo,
    LocationEvent,
    LocationEventBatch,
)

@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init_db()
    yield


app = FastAPI(
    title="LocationLab API",
    description=(
        "API de ingesta de eventos de localización para la PoC de simulación "
        "de usuarios. Permite probar si un sistema distingue tráfico real de sintético."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# Detector de grupos compartido (estado en memoria, complementado con SQLite)
_detector = GroupDetector(
    GroupDetectorConfig(
        max_distance_meters=30.0,
        max_time_skew_seconds=10.0,
        min_persistence_ticks=3,
        max_speed_diff_mps=2.0,
    )
)
_detection_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health", tags=["Meta"])
def health():
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


# ---------------------------------------------------------------------------
# Eventos de localización
# ---------------------------------------------------------------------------

@app.post(
    "/api/locations",
    status_code=202,
    summary="Ingesta de un único evento de localización",
    tags=["Locations"],
)
def post_location(event: LocationEvent):
    """
    Recibe un evento de localización de un dispositivo y lo persiste.
    Devuelve 202 Accepted con la URL del historial del dispositivo.
    """
    row_id = db.insert_event(
        device_id=event.device_id,
        latitude=event.latitude,
        longitude=event.longitude,
        timestamp_utc=event.timestamp_utc,
        accuracy_meters=event.accuracy_meters,
        speed_mps=event.speed_meters_per_second,
        bearing_degrees=event.bearing_degrees,
    )
    _run_group_detection(event.timestamp_utc)
    return JSONResponse(
        status_code=202,
        content={"accepted": True, "id": row_id, "device_id": event.device_id},
        headers={"Location": f"/api/devices/{event.device_id}/locations"},
    )


@app.post(
    "/api/locations/batch",
    status_code=202,
    summary="Ingesta por lotes para reducir overhead HTTP",
    tags=["Locations"],
)
def post_locations_batch(batch: LocationEventBatch):
    """
    Ingesta de múltiples eventos en una sola llamada HTTP.
    Recomendado a partir de 20+ dispositivos para reducir latencia.
    """
    if not batch.events:
        raise HTTPException(status_code=422, detail="El lote está vacío.")

    rows = [
        {
            "device_id": e.device_id,
            "latitude": e.latitude,
            "longitude": e.longitude,
            "timestamp_utc": e.timestamp_utc.isoformat(),
            "accuracy_meters": e.accuracy_meters,
            "speed_mps": e.speed_meters_per_second,
            "bearing_degrees": e.bearing_degrees,
        }
        for e in batch.events
    ]
    count = db.insert_events_batch(rows)
    reference_timestamp = max(event.timestamp_utc for event in batch.events)
    _run_group_detection(reference_timestamp)
    return {"accepted": True, "count": count}


# ---------------------------------------------------------------------------
# Dispositivos
# ---------------------------------------------------------------------------

@app.get(
    "/api/devices",
    response_model=list[DeviceInfo],
    summary="Listado de dispositivos conocidos",
    tags=["Devices"],
)
def get_devices():
    rows = db.get_known_devices()
    return [
        DeviceInfo(
            device_id=r["device_id"],
            last_seen=r["last_seen"],
            last_latitude=r["last_latitude"],
            last_longitude=r["last_longitude"],
            event_count=r["event_count"],
        )
        for r in rows
    ]


@app.get(
    "/api/devices/{device_id}/locations",
    summary="Historial de localización de un dispositivo",
    tags=["Devices"],
)
def get_device_locations(
    device_id: str,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
):
    rows = db.get_device_history(device_id, limit)
    if not rows:
        raise HTTPException(status_code=404, detail=f"Dispositivo '{device_id}' no encontrado.")
    return rows


# ---------------------------------------------------------------------------
# Grupos
# ---------------------------------------------------------------------------

@app.get(
    "/api/groups/current",
    response_model=list[GroupInfo],
    summary="Grupos detectados en la ventana activa",
    tags=["Groups"],
)
def get_current_groups():
    rows = db.get_current_groups()
    return [
        GroupInfo(
            group_id=r["group_id"],
            device_ids=r["device_ids"].split(","),
            detected_at=r["detected_at"],
            member_count=r["member_count"],
        )
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

def _run_group_detection(reference_timestamp: datetime) -> None:
    """
    Obtiene muestras recientes y ejecuta un tick del detector.
    Persiste grupos nuevos en SQLite.
    """
    with _detection_lock:
        raw = db.get_recent_samples(
            window_seconds=15,
            reference_timestamp=reference_timestamp,
        )
        if len(raw) < 2:
            return

        samples = [
            Sample(
                device_id=r["device_id"],
                latitude=r["latitude"],
                longitude=r["longitude"],
                timestamp_utc=datetime.fromisoformat(r["timestamp_utc"]),
                speed_meters_per_second=r["speed_mps"],
                bearing_degrees=r["bearing_degrees"],
            )
            for r in raw
        ]

        consolidated = _detector.tick(samples)
        for group in consolidated:
            members = ",".join(sorted(group))
            group_id = uuid.uuid5(uuid.NAMESPACE_URL, f"locationlab:{members}").hex[:8]
            db.insert_group(
                group_id,
                list(group),
                detected_at=reference_timestamp,
                last_seen_utc=reference_timestamp,
            )
