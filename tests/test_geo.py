"""
Tests unitarios de las funciones geoespaciales.
"""
import math
import pytest
from locationlab.core.geo import haversine_meters, bearing_degrees, add_noise_meters


class TestHaversineMeters:
    def test_same_point_is_zero(self):
        assert haversine_meters(43.263, -2.935, 43.263, -2.935) == pytest.approx(0.0, abs=1e-6)

    def test_known_distance_bilbao(self):
        # Distancia aproximada entre Ayuntamiento de Bilbao y Casco Viejo
        # (~600 m en línea recta, margen ±50 m)
        d = haversine_meters(43.2569, -2.9236, 43.2525, -2.9248)
        assert 400 < d < 750

    def test_symmetry(self):
        d1 = haversine_meters(43.263, -2.935, 43.270, -2.940)
        d2 = haversine_meters(43.270, -2.940, 43.263, -2.935)
        assert d1 == pytest.approx(d2, rel=1e-9)

    def test_short_distance_accuracy(self):
        # 10 metros aprox moviendo 0.00009° lat
        d = haversine_meters(43.263, -2.935, 43.2631, -2.935)
        assert 8 < d < 15

    def test_long_distance(self):
        # Madrid – Bilbao ≈ 323 km en línea recta (≠ distancia por carretera)
        d = haversine_meters(40.4168, -3.7038, 43.263, -2.935)
        assert 310_000 < d < 340_000


class TestBearingDegrees:
    def test_north(self):
        b = bearing_degrees(0.0, 0.0, 1.0, 0.0)
        assert b == pytest.approx(0.0, abs=1.0)

    def test_east(self):
        b = bearing_degrees(0.0, 0.0, 0.0, 1.0)
        assert b == pytest.approx(90.0, abs=1.0)

    def test_south(self):
        b = bearing_degrees(1.0, 0.0, 0.0, 0.0)
        assert b == pytest.approx(180.0, abs=1.0)

    def test_west(self):
        b = bearing_degrees(0.0, 1.0, 0.0, 0.0)
        assert b == pytest.approx(270.0, abs=1.0)

    def test_range(self):
        b = bearing_degrees(43.263, -2.935, 43.270, -2.920)
        assert 0.0 <= b < 360.0


class TestAddNoiseMeters:
    def test_noise_within_bound(self):
        """El punto perturbado no debería alejarse más de ~3x el sigma solicitado."""
        lat, lon = 43.263, -2.935
        noise_m = 5.0
        for _ in range(200):
            nlat, nlon = add_noise_meters(lat, lon, noise_m)
            d = haversine_meters(lat, lon, nlat, nlon)
            # 3 sigma = noise_m, prácticamente todos los valores deben estar aquí
            assert d < noise_m * 4, f"Ruido excesivo: {d:.2f} m"

    def test_noise_is_random(self):
        """Dos llamadas consecutivas deben dar resultados distintos (casi siempre)."""
        lat, lon = 43.263, -2.935
        results = {add_noise_meters(lat, lon, 10.0) for _ in range(20)}
        assert len(results) > 1
