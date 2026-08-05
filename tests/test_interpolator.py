"""
Tests de la interpolación de rutas GPX.
"""
from datetime import datetime, timezone, timedelta
import pytest

from locationlab.simulator.gpx_reader import TrackPoint
from locationlab.simulator.interpolator import interpolate_position, build_time_offset_route


def _utc(h: int, m: int, s: int) -> datetime:
    return datetime(2026, 7, 12, h, m, s, tzinfo=timezone.utc)


# Ruta de prueba: 3 puntos simples
ROUTE = [
    TrackPoint(latitude=43.2630, longitude=-2.9350, timestamp_utc=_utc(10, 0, 0)),
    TrackPoint(latitude=43.2640, longitude=-2.9340, timestamp_utc=_utc(10, 0, 10)),  # +10s
    TrackPoint(latitude=43.2650, longitude=-2.9330, timestamp_utc=_utc(10, 0, 20)),  # +10s
]


class TestInterpolatePosition:

    def test_at_first_point(self):
        lat, lon, speed, bear = interpolate_position(ROUTE, _utc(10, 0, 0))
        assert lat == pytest.approx(43.2630, abs=1e-6)
        assert lon == pytest.approx(-2.9350, abs=1e-6)

    def test_at_last_point(self):
        lat, lon, speed, bear = interpolate_position(ROUTE, _utc(10, 0, 20))
        assert lat == pytest.approx(43.2650, abs=1e-6)
        assert lon == pytest.approx(-2.9330, abs=1e-6)

    def test_midpoint_first_segment(self):
        """A mitad del primer segmento las coords deben ser el promedio."""
        lat, lon, speed, bear = interpolate_position(ROUTE, _utc(10, 0, 5))
        assert lat == pytest.approx(43.2635, abs=1e-5)
        assert lon == pytest.approx(-2.9345, abs=1e-5)

    def test_before_route_returns_first(self):
        lat, lon, speed, bear = interpolate_position(ROUTE, _utc(9, 59, 0))
        assert lat == pytest.approx(43.2630, abs=1e-6)

    def test_after_route_returns_last(self):
        lat, lon, speed, bear = interpolate_position(ROUTE, _utc(10, 5, 0))
        assert lat == pytest.approx(43.2650, abs=1e-6)

    def test_speed_nonzero_in_segment(self):
        lat, lon, speed, bear = interpolate_position(ROUTE, _utc(10, 0, 5))
        assert speed > 0

    def test_bearing_northeast(self):
        """La ruta va hacia el noreste, bearing debe estar en [0, 90]."""
        lat, lon, speed, bear = interpolate_position(ROUTE, _utc(10, 0, 5))
        assert 0 < bear < 90


class TestBuildTimeOffsetRoute:

    def test_positive_offset(self):
        offset_route = build_time_offset_route(ROUTE, start_offset_seconds=30)
        for orig, shifted in zip(ROUTE, offset_route):
            diff = (shifted.timestamp_utc - orig.timestamp_utc).total_seconds()
            assert diff == pytest.approx(30.0)

    def test_negative_offset(self):
        offset_route = build_time_offset_route(ROUTE, start_offset_seconds=-5)
        for orig, shifted in zip(ROUTE, offset_route):
            diff = (shifted.timestamp_utc - orig.timestamp_utc).total_seconds()
            assert diff == pytest.approx(-5.0)

    def test_positions_unchanged(self):
        offset_route = build_time_offset_route(ROUTE, start_offset_seconds=100)
        for orig, shifted in zip(ROUTE, offset_route):
            assert orig.latitude == shifted.latitude
            assert orig.longitude == shifted.longitude
