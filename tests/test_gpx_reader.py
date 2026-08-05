from datetime import datetime, timezone
from pathlib import Path

from locationlab.simulator.gpx_reader import load_gpx
from locationlab.simulator.scenario import DeviceScenarioConfig, ScenarioEngine


def _write_gpx(path: Path, points: str) -> None:
    path.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="tests" xmlns="http://www.topografix.com/GPX/1/1">
  <trk><name>test</name><trkseg>
"""
        + points
        + """  </trkseg></trk>
</gpx>
""",
        encoding="utf-8",
    )


def test_load_gpx_normalizes_timestamps_to_utc(tmp_path: Path):
    path = tmp_path / "timezone.gpx"
    _write_gpx(
        path,
        """
    <trkpt lat="43.0" lon="-2.0"><time>2026-08-05T10:00:00+02:00</time></trkpt>
    <trkpt lat="43.1" lon="-2.1"><time>2026-08-05T08:01:00Z</time></trkpt>
""",
    )

    points = load_gpx(path)

    assert all(point.timestamp_utc.tzinfo == timezone.utc for point in points)
    assert points[0].timestamp_utc.isoformat() == "2026-08-05T08:00:00+00:00"
    assert points[0].latitude == 43.0


def test_load_gpx_assigns_sequential_timestamps_when_missing(tmp_path: Path):
    path = tmp_path / "untimed.gpx"
    _write_gpx(
        path,
        """
    <trkpt lat="43.0" lon="-2.0" />
    <trkpt lat="43.1" lon="-2.1" />
    <trkpt lat="43.2" lon="-2.2" />
""",
    )

    points = load_gpx(path)

    assert len(points) == 3
    assert all(point.timestamp_utc.tzinfo == timezone.utc for point in points)
    assert [
        (points[index + 1].timestamp_utc - points[index].timestamp_utc).total_seconds()
        for index in range(2)
    ] == [1.0, 1.0]


def test_load_gpx_mixed_timestamps_is_coherent_and_ordered(tmp_path: Path):
    path = tmp_path / "mixed.gpx"
    _write_gpx(
        path,
        """
    <trkpt lat="43.0" lon="-2.0"><time>2026-08-05T08:00:00Z</time></trkpt>
    <trkpt lat="43.1" lon="-2.1" />
    <trkpt lat="43.2" lon="-2.2"><time>2026-08-05T08:00:02Z</time></trkpt>
""",
    )

    points = load_gpx(path)

    timestamps = [point.timestamp_utc for point in points]
    assert timestamps == sorted(timestamps)
    assert len({timestamp.tzinfo for timestamp in timestamps}) == 1
    assert (timestamps[-1] - timestamps[0]).total_seconds() == 2


def test_scenario_engine_keeps_independent_routes(tmp_path: Path):
    first_route = tmp_path / "first.gpx"
    second_route = tmp_path / "second.gpx"
    points = """
    <trkpt lat="43.0" lon="-2.0"><time>2026-08-05T08:00:00Z</time></trkpt>
    <trkpt lat="43.0" lon="-2.1"><time>2026-08-05T08:00:10Z</time></trkpt>
"""
    _write_gpx(first_route, points)
    _write_gpx(
        second_route,
        points.replace('lat="43.0"', 'lat="43.5"'),
    )

    engine = ScenarioEngine(
        [
            DeviceScenarioConfig("first", str(first_route), noise_meters=0),
            DeviceScenarioConfig("second", str(second_route), noise_meters=0),
        ]
    )
    engine.initialize()

    events = engine.get_events(engine.route_start)

    assert {event.device_id for event in events} == {"first", "second"}
    positions = {event.device_id: event.latitude for event in events}
    assert positions["first"] == 43.0
    assert positions["second"] == 43.5


def test_scenario_engine_exposes_trip_phases(tmp_path: Path):
    route = tmp_path / "phases.gpx"
    _write_gpx(
        route,
        """
    <trkpt lat="43.0" lon="-2.0"><time>2026-08-05T08:00:00Z</time></trkpt>
    <trkpt lat="43.0" lon="-2.1"><time>2026-08-05T08:00:20Z</time></trkpt>
    <trkpt lat="43.0" lon="-2.2"><time>2026-08-05T08:00:40Z</time></trkpt>
""",
    )
    engine = ScenarioEngine(
        [
            DeviceScenarioConfig(
                "passenger",
                str(route),
                noise_meters=0,
                trip_start_utc=datetime(2026, 8, 5, 8, 0, 20, tzinfo=timezone.utc),
            )
        ]
    )
    engine.initialize()

    assert engine.phase_at("passenger", datetime(2026, 8, 5, 7, 59, tzinfo=timezone.utc)) == "waiting"
    assert engine.phase_at("passenger", datetime(2026, 8, 5, 8, 0, 10, tzinfo=timezone.utc)) == "walking"
    assert engine.phase_at("passenger", datetime(2026, 8, 5, 8, 0, 20, tzinfo=timezone.utc)) == "on_trip"
    assert engine.phase_at("passenger", datetime(2026, 8, 5, 8, 1, tzinfo=timezone.utc)) == "arrived"
