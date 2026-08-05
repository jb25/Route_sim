from datetime import timezone
from pathlib import Path

from locationlab.simulator.gpx_reader import load_gpx


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
