"""Adaptadores autorizados para iniciar una app durante un escenario."""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class AppStartConfig:
    mode: str = "noop"
    serial: str = ""
    package: str = ""
    activity: str = ""
    action: str = ""


class AppLauncher:
    """Inicia apps mediante un mecanismo explícito configurado por escenario."""

    def __init__(self, adb_path: str = "adb") -> None:
        self._adb_path = adb_path

    def start(self, device_id: str, config: AppStartConfig | None, at: datetime) -> bool:
        if config is None or config.mode == "noop":
            return True
        if config.mode != "adb_intent":
            raise ValueError(f"Modo de arranque no soportado: {config.mode}")
        if not config.serial or not config.package:
            raise ValueError(
                f"El arranque ADB de '{device_id}' requiere serial y package."
            )
        if not config.activity and not config.action:
            raise ValueError(
                f"El arranque ADB de '{device_id}' requiere activity o action."
            )

        args = [self._adb_path, "-s", config.serial, "shell", "am", "start"]
        if config.activity:
            args.extend(["-n", f"{config.package}/{config.activity}"])
        else:
            args.extend(["-a", config.action])
            args.extend(["-p", config.package])

        result = subprocess.run(args, capture_output=True, text=True, timeout=10)
        return result.returncode == 0