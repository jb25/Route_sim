"""
Tests unitarios del detector de grupos.
Cubre los casos de la tabla del informe de investigación.
"""
from datetime import datetime, timezone, timedelta
import pytest

from locationlab.core.group_detector import GroupDetector, GroupDetectorConfig, Sample


def _utc(seconds_offset: float = 0) -> datetime:
    base = datetime(2026, 7, 12, 10, 0, 0, tzinfo=timezone.utc)
    return base + timedelta(seconds=seconds_offset)


def _make_detector(
    max_dist=30.0,
    max_dt=10.0,
    min_persist=3,
    max_speed_diff=0.0,
) -> GroupDetector:
    return GroupDetector(
        GroupDetectorConfig(
            max_distance_meters=max_dist,
            max_time_skew_seconds=max_dt,
            min_persistence_ticks=min_persist,
            max_speed_diff_mps=max_speed_diff,
        )
    )


def _run_n_ticks(detector: GroupDetector, samples: list[Sample], n: int):
    result = []
    for _ in range(n):
        result = detector.tick(samples)
    return result


class TestGroupDetectionBasic:

    def test_two_devices_10m_apart_form_group(self):
        """Dos dispositivos a ~10 m deben agruparse tras persistencia mínima."""
        det = _make_detector(max_dist=30, max_dt=10, min_persist=1)
        samples = [
            Sample("A", 43.2630, -2.9350, _utc(0)),
            # ~11 m al norte
            Sample("B", 43.2631, -2.9350, _utc(1)),
        ]
        groups = _run_n_ticks(det, samples, 1)
        assert any({"A", "B"} == set(g) for g in groups)

    def test_two_devices_80m_apart_no_group(self):
        """Dos dispositivos a >80 m NO deben agruparse."""
        det = _make_detector(max_dist=30, min_persist=1)
        samples = [
            Sample("A", 43.2630, -2.9350, _utc(0)),
            # ~89 m al norte
            Sample("B", 43.2638, -2.9350, _utc(0)),
        ]
        groups = _run_n_ticks(det, samples, 5)
        assert not groups

    def test_large_time_skew_no_group(self):
        """Dos dispositivos a 20 m pero con 40 s de desfase NO deben agruparse."""
        det = _make_detector(max_dist=30, max_dt=10, min_persist=1)
        samples = [
            Sample("A", 43.2630, -2.9350, _utc(0)),
            Sample("B", 43.2632, -2.9350, _utc(40)),
        ]
        groups = _run_n_ticks(det, samples, 5)
        assert not groups

    def test_three_together_one_isolated(self):
        """Tres dispositivos juntos + uno aislado → grupo de 3, outlier excluido."""
        det = _make_detector(max_dist=30, max_dt=10, min_persist=1)
        samples = [
            Sample("A", 43.2630, -2.9350, _utc(0)),
            Sample("B", 43.2631, -2.9350, _utc(0)),
            Sample("C", 43.2630, -2.9351, _utc(0)),
            Sample("X", 43.2700, -2.9350, _utc(0)),  # muy lejos
        ]
        groups = _run_n_ticks(det, samples, 1)
        main_group = next((g for g in groups if len(g) == 3), None)
        assert main_group is not None
        assert {"A", "B", "C"} == set(main_group)
        assert all("X" not in g for g in groups)


class TestPersistence:

    def test_group_needs_min_ticks_to_consolidate(self):
        """Con min_persist=3, el grupo no debe aparecer antes del tick 3."""
        det = _make_detector(max_dist=30, max_dt=10, min_persist=3)
        samples = [
            Sample("A", 43.2630, -2.9350, _utc(0)),
            Sample("B", 43.2631, -2.9350, _utc(0)),
        ]
        # Tick 1: no consolidado
        assert not det.tick(samples)
        # Tick 2: no consolidado
        assert not det.tick(samples)
        # Tick 3: consolidado
        groups = det.tick(samples)
        assert any({"A", "B"} == set(g) for g in groups)

    def test_group_disappears_after_separation(self):
        """El grupo debe desaparecer si los dispositivos se separan."""
        det = _make_detector(max_dist=30, max_dt=10, min_persist=1)
        close = [
            Sample("A", 43.2630, -2.9350, _utc(0)),
            Sample("B", 43.2631, -2.9350, _utc(0)),
        ]
        far = [
            Sample("A", 43.2630, -2.9350, _utc(0)),
            Sample("B", 43.2700, -2.9350, _utc(0)),  # muy lejos
        ]
        # Establecer grupo
        det.tick(close)
        det.tick(close)
        # Separar
        det.tick(far)
        groups = det.tick(far)
        assert not groups

    def test_transient_crossing_not_consolidated(self):
        """Un cruce puntual (1 tick) no debe consolidar grupo si min_persist=3."""
        det = _make_detector(max_dist=30, max_dt=10, min_persist=3)
        close = [
            Sample("A", 43.2630, -2.9350, _utc(0)),
            Sample("B", 43.2631, -2.9350, _utc(0)),
        ]
        far = [
            Sample("A", 43.2630, -2.9350, _utc(0)),
            Sample("B", 43.2700, -2.9350, _utc(0)),
        ]
        det.tick(close)   # tick 1 close
        det.tick(far)     # tick 2 far  → reset
        det.tick(close)   # tick 3 close → vuelve desde 1
        groups = det.tick(close)  # tick 4: solo 2 ticks seguidos → no consolidado
        assert not groups


class TestGaussianNoise:

    def test_group_stable_with_small_noise(self):
        """Grupo con ruido gaussiano pequeño debe mantenerse agrupado."""
        from locationlab.core.geo import add_noise_meters
        import random
        random.seed(42)

        det = _make_detector(max_dist=30, max_dt=10, min_persist=3)
        base_lat, base_lon = 43.2630, -2.9350

        for tick in range(10):
            samples = []
            for dev_id in ["A", "B", "C"]:
                nlat, nlon = add_noise_meters(base_lat, base_lon, noise_m=4.0)
                samples.append(Sample(dev_id, nlat, nlon, _utc(float(tick))))
            groups = det.tick(samples)

        # Después de 10 ticks con ruido pequeño, el grupo debe estar consolidado
        assert any({"A", "B", "C"} == set(g) for g in groups)
