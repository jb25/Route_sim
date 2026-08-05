"""
Lector de archivos GPX.
Extrae trackpoints ordenados cronológicamente y asigna timestamps
sintéticos cuando el archivo no los incluye.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import gpxpy
import gpxpy.gpx


@dataclass
class TrackPoint:
    latitude: float
    longitude: float
    timestamp_utc: datetime
    elevation: float | None = None


def load_gpx(path: str | Path) -> list[TrackPoint]:
    """
    Carga un archivo GPX y devuelve una lista de TrackPoints ordenada por tiempo.

    - Si los puntos tienen timestamps reales, se usan directamente (convertidos a UTC).
    - Si no, se asigna t0 = ahora + 1 segundo por punto, igual que hace Genymotion.
    """
    gpx_path = Path(path)
    if not gpx_path.exists():
        raise FileNotFoundError(f"GPX no encontrado: {gpx_path}")

    with gpx_path.open("r", encoding="utf-8") as f:
        gpx = gpxpy.parse(f)

    points: list[TrackPoint] = []

    for track in gpx.tracks:
        for segment in track.segments:
            for pt in segment.points:
                points.append(
                    TrackPoint(
                        latitude=pt.latitude,
                        longitude=pt.longitude,
                        timestamp_utc=pt.time,  # puede ser None
                        elevation=pt.elevation,
                    )
                )

    # También soportar waypoints sueltos
    for wpt in gpx.waypoints:
        points.append(
            TrackPoint(
                latitude=wpt.latitude,
                longitude=wpt.longitude,
                timestamp_utc=wpt.time,
                elevation=wpt.elevation,
            )
        )

    # Si falta algun timestamp, usar una linea temporal sintetica coherente para
    # toda la ruta en lugar de mezclar instantes reales y artificiales.
    if not points:
        raise ValueError("El archivo GPX no contiene puntos.")

    if any(p.timestamp_utc is None for p in points):
        existing = next((p.timestamp_utc for p in points if p.timestamp_utc), None)
        if existing is not None:
            t0 = (
                existing.astimezone(timezone.utc)
                if existing.tzinfo
                else existing.replace(tzinfo=timezone.utc)
            )
        else:
            t0 = datetime.now(timezone.utc)
        points = [
            TrackPoint(
                latitude=p.latitude,
                longitude=p.longitude,
                timestamp_utc=t0 + timedelta(seconds=i),
                elevation=p.elevation,
            )
            for i, p in enumerate(points)
        ]
    else:
        # Normalizar a UTC
        points = [
            TrackPoint(
                latitude=p.latitude,
                longitude=p.longitude,
                timestamp_utc=(
                    p.timestamp_utc.astimezone(timezone.utc)
                    if p.timestamp_utc.tzinfo
                    else p.timestamp_utc.replace(tzinfo=timezone.utc)
                ),
                elevation=p.elevation,
            )
            for p in points
        ]

    points.sort(key=lambda p: p.timestamp_utc)

    return points
