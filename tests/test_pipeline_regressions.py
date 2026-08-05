from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from locationlab.api import database as db
from locationlab.api.main import app
from locationlab.simulator.publisher import ApiPublisher
from locationlab.simulator.scenario_main import validate_scenario


@pytest.fixture
def temporary_database(tmp_path: Path):
    original = db.get_db_path()
    db.set_db_path(tmp_path / "locationlab.db")
    db.init_db()
    yield
    db.set_db_path(original)


def test_database_uses_simulated_time_and_stable_groups(temporary_database):
    simulated = datetime(2026, 7, 14, 7, 0, tzinfo=timezone.utc)
    for device_id, latitude in (("driver", 43.0), ("passenger", 43.0001)):
        db.insert_event(device_id, latitude, -2.0, simulated, 5, 10, 0)

    assert len(db.get_recent_samples()) == 2
    db.insert_group("stable", ["driver", "passenger"], simulated)
    db.insert_group("stable", ["passenger", "driver"], simulated.replace(second=1))
    assert len(db.get_current_groups()) == 1


def test_scenario_validation_rejects_invalid_values(tmp_path: Path):
    config = {
        "api_base_url": "http://localhost:8080",
        "tick_seconds": 0,
        "batch_size": 1,
        "log_every_n_ticks": 1,
        "max_duration_seconds": 0,
        "devices": [{"device_id": "d", "route_file": str(tmp_path / "route.gpx")}],
    }
    with pytest.raises(ValueError, match="tick_seconds"):
        validate_scenario(config)


def test_scenario_validation_rejects_invalid_wall_tick(tmp_path: Path):
    config = {
        "api_base_url": "http://localhost:8080",
        "tick_seconds": 1,
        "wall_tick_seconds": 0,
        "batch_size": 1,
        "log_every_n_ticks": 1,
        "max_duration_seconds": 0,
        "devices": [{"device_id": "d", "route_file": str(tmp_path / "route.gpx")}],
    }
    with pytest.raises(ValueError, match="wall_tick_seconds"):
        validate_scenario(config)


def test_publisher_does_not_retry_permanent_client_errors():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(400)

    publisher = ApiPublisher("https://example.test", max_retries=3, backoff_seconds=0)
    publisher._client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        assert publisher._post("https://example.test/api/locations", {}) is False
        assert calls == 1
    finally:
        publisher.close()


def test_publisher_retries_transient_errors():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503 if calls < 2 else 202)

    publisher = ApiPublisher("https://example.test", max_retries=2, backoff_seconds=0)
    publisher._client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        assert publisher._post("https://example.test/api/locations", {}) is True
        assert calls == 2
    finally:
        publisher.close()


def test_fastapi_batch_flow_detects_current_group(tmp_path: Path):
    original = db.get_db_path()
    db.set_db_path(tmp_path / "api.db")
    device_ids = [f"api-test-{index}" for index in range(4)]
    base_time = datetime.now(timezone.utc).replace(microsecond=0)
    try:
        with TestClient(app) as client:
            for tick in range(3):
                timestamp = (base_time + timedelta(seconds=tick)).isoformat()
                response = client.post(
                    "/api/locations/batch",
                    json={
                        "events": [
                            {
                                "device_id": device_id,
                                "latitude": 43.2 + index * 0.00001,
                                "longitude": -2.75,
                                "timestamp_utc": timestamp,
                                "accuracy_meters": 4.0,
                                "speed_meters_per_second": 12.0,
                                "bearing_degrees": 90.0,
                            }
                            for index, device_id in enumerate(device_ids)
                        ]
                    },
                )
                assert response.status_code == 202
                assert response.json()["count"] == 4

            devices = client.get("/api/devices").json()
            groups = client.get("/api/groups/current").json()
            history = client.get(f"/api/devices/{device_ids[0]}/locations").json()

        assert {device["device_id"] for device in devices} == set(device_ids)
        assert len(history) == 3
        assert any(set(group["device_ids"]) == set(device_ids) for group in groups)
    finally:
        db.set_db_path(original)
