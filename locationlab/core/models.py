"""
Modelos de dominio compartidos por la API y el simulador.
"""
from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, field_validator


class LocationEvent(BaseModel):
    """Evento de localización emitido por un dispositivo."""

    device_id: str
    latitude: float
    longitude: float
    timestamp_utc: datetime
    accuracy_meters: float = 5.0
    speed_meters_per_second: float = 0.0
    bearing_degrees: float = 0.0

    @field_validator("device_id")
    @classmethod
    def device_id_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("device_id es obligatorio.")
        return v.strip()

    @field_validator("latitude")
    @classmethod
    def latitude_range(cls, v: float) -> float:
        if not (-90 <= v <= 90):
            raise ValueError("La latitud debe estar entre -90 y 90.")
        return v

    @field_validator("longitude")
    @classmethod
    def longitude_range(cls, v: float) -> float:
        if not (-180 <= v <= 180):
            raise ValueError("La longitud debe estar entre -180 y 180.")
        return v


class LocationEventBatch(BaseModel):
    """Lote de eventos para reducir overhead HTTP."""

    events: list[LocationEvent]


class GroupInfo(BaseModel):
    """Grupo de dispositivos detectados viajando juntos."""

    group_id: str
    device_ids: list[str]
    detected_at: datetime
    member_count: int


class DeviceInfo(BaseModel):
    """Estado resumido de un dispositivo."""

    device_id: str
    last_seen: datetime
    last_latitude: float
    last_longitude: float
    event_count: int
