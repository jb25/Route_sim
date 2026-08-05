"""
Interpolación de ruta GPX.
Dado un conjunto de TrackPoints y un instante t, devuelve la posición
interpolada linealmente entre los dos puntos más cercanos.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

from locationlab.simulator.gpx_reader import TrackPoint
from locationlab.core.geo import bearing_degrees


def interpolate_position(
    points: list[TrackPoint], t: datetime
) -> tuple[float, float, float, float] | None:
    """
    Interpola la posición en el instante *t*.

    Devuelve (latitude, longitude, speed_mps, bearing_deg) o None si *t*
    está fuera del rango de la ruta.
    """
    if not points:
        return None

    # Antes del primer punto
    if t <= points[0].timestamp_utc:
        p = points[0]
        return p.latitude, p.longitude, 0.0, 0.0

    # Después del último punto
    if t >= points[-1].timestamp_utc:
        p = points[-1]
        return p.latitude, p.longitude, 0.0, 0.0

    # Buscar el segmento
    for i in range(len(points) - 1):
        a = points[i]
        b = points[i + 1]
        if a.timestamp_utc <= t <= b.timestamp_utc:
            seg_seconds = (b.timestamp_utc - a.timestamp_utc).total_seconds()
            if seg_seconds == 0:
                return a.latitude, a.longitude, 0.0, 0.0

            alpha = (t - a.timestamp_utc).total_seconds() / seg_seconds

            lat = a.latitude + alpha * (b.latitude - a.latitude)
            lon = a.longitude + alpha * (b.longitude - a.longitude)

            # velocidad media del segmento
            from locationlab.core.geo import haversine_meters
            dist_m = haversine_meters(a.latitude, a.longitude, b.latitude, b.longitude)
            speed = dist_m / seg_seconds

            # rumbo del segmento
            bear = bearing_degrees(a.latitude, a.longitude, b.latitude, b.longitude)

            return lat, lon, speed, bear

    return None  # no debería llegar aquí


def build_time_offset_route(
    points: list[TrackPoint], start_offset_seconds: float
) -> list[TrackPoint]:
    """
    Devuelve una copia de *points* desplazada en el tiempo *start_offset_seconds*.
    Útil para que cada dispositivo empiece ligeramente antes o después.
    """
    delta = timedelta(seconds=start_offset_seconds)
    return [
        TrackPoint(
            latitude=p.latitude,
            longitude=p.longitude,
            timestamp_utc=p.timestamp_utc + delta,
            elevation=p.elevation,
        )
        for p in points
    ]
