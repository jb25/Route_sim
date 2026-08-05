"""
Cálculos geoespaciales básicos para la PoC.
"""
from __future__ import annotations

import math

EARTH_RADIUS_METERS = 6_371_000.0


def haversine_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Distancia de gran círculo (Haversine) entre dos puntos lat/lon, en metros.
    Válida para distancias urbanas cortas sin corrección elipsoidal.
    """
    to_rad = math.pi / 180.0

    d_lat = (lat2 - lat1) * to_rad
    d_lon = (lon2 - lon1) * to_rad

    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(lat1 * to_rad) * math.cos(lat2 * to_rad) * math.sin(d_lon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return EARTH_RADIUS_METERS * c


def bearing_degrees(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Rumbo inicial (bearing) desde el punto 1 al punto 2, en grados [0, 360).
    """
    to_rad = math.pi / 180.0
    d_lon = (lon2 - lon1) * to_rad

    x = math.sin(d_lon) * math.cos(lat2 * to_rad)
    y = math.cos(lat1 * to_rad) * math.sin(lat2 * to_rad) - math.sin(
        lat1 * to_rad
    ) * math.cos(lat2 * to_rad) * math.cos(d_lon)

    bearing = math.atan2(x, y) * 180.0 / math.pi
    return (bearing + 360) % 360


def add_noise_meters(lat: float, lon: float, noise_m: float) -> tuple[float, float]:
    """
    Desplaza lat/lon un máximo de *noise_m* metros en dirección aleatoria usando
    distribución gaussiana (sigma = noise_m / 3 ≈ 99,7 % dentro del radio).
    """
    import random

    sigma = noise_m / 3.0
    delta_lat = random.gauss(0, sigma) / EARTH_RADIUS_METERS * (180.0 / math.pi)
    delta_lon = (
        random.gauss(0, sigma)
        / (EARTH_RADIUS_METERS * math.cos(math.radians(lat)))
        * (180.0 / math.pi)
    )
    return lat + delta_lat, lon + delta_lon
