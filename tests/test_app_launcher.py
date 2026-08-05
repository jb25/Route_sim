from datetime import datetime, timezone

import pytest

from locationlab.simulator.app_launcher import AppLauncher, AppStartConfig


def test_noop_launcher_does_not_call_adb():
    launcher = AppLauncher(adb_path="missing-adb")

    assert launcher.start(
        "passenger",
        AppStartConfig(),
        datetime.now(timezone.utc),
    ) is True


def test_adb_intent_uses_explicit_component(monkeypatch):
    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        return type("Result", (), {"returncode": 0})()

    monkeypatch.setattr("locationlab.simulator.app_launcher.subprocess.run", fake_run)
    launcher = AppLauncher(adb_path="adb-test")

    assert launcher.start(
        "passenger",
        AppStartConfig(
            mode="adb_intent",
            serial="emulator-5554",
            package="com.example.test",
            activity=".MainActivity",
        ),
        datetime.now(timezone.utc),
    ) is True
    assert calls[0][0] == [
        "adb-test",
        "-s",
        "emulator-5554",
        "shell",
        "am",
        "start",
        "-n",
        "com.example.test/.MainActivity",
    ]


def test_adb_intent_requires_component():
    with pytest.raises(ValueError, match="activity o action"):
        AppLauncher().start(
            "passenger",
            AppStartConfig(
                mode="adb_intent",
                serial="emulator-5554",
                package="com.example.test",
            ),
            datetime.now(timezone.utc),
        )