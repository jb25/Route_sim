"""
CLI del simulador de escenarios con rutas por dispositivo.

Uso:
    python -m locationlab.simulator.scenario_main \\
        --scenario scenarios/commute_bilbao.json

Formato del JSON de escenario:

    {
      "api_base_url": "http://localhost:8080",
      "tick_seconds": 2.0,
    "wall_tick_seconds": 2.0,
      "batch_size": 10,
      "use_batch_endpoint": true,
      "log_every_n_ticks": 30,
      "max_duration_seconds": 0,
      "extra_headers": {},
      "devices": [
        {
          "device_id": "conductor",
          "route_file": "routes/commute_driver.gpx",
          "noise_meters": 3.5,
          "speed_variation_pct": 1.5,
          "label": "Conductor – Lemoa"
        },
        ...
      ]
    }
"""
from __future__ import annotations

import argparse
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

from locationlab.simulator.publisher import ApiPublisher
from locationlab.simulator.scenario import DeviceScenarioConfig, ScenarioEngine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("scenario")

DEFAULT_SCENARIO: dict = {
    "api_base_url": "http://localhost:8080",
    "tick_seconds": 2.0,
    "wall_tick_seconds": 2.0,
    "batch_size": 10,
    "use_batch_endpoint": True,
    "log_every_n_ticks": 30,
    "max_duration_seconds": 0,
    "extra_headers": {},
    "devices": [],
}


def load_scenario(path: str) -> dict:
    cfg = dict(DEFAULT_SCENARIO)
    scenario_path = Path(path)
    if not scenario_path.exists():
        raise FileNotFoundError(f"Archivo de escenario no encontrado: {path}")
    with scenario_path.open("r", encoding="utf-8") as f:
        loaded = json.load(f)
    if not isinstance(loaded, dict):
        raise ValueError("El escenario debe ser un objeto JSON.")
    cfg.update(loaded)
    validate_scenario(cfg)
    return cfg


def validate_scenario(cfg: dict) -> None:
    """Valida toda la configuracion antes de cargar rutas o iniciar HTTP."""
    parsed_url = urlparse(str(cfg.get("api_base_url", "")))
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        raise ValueError("'api_base_url' debe ser una URL HTTP/HTTPS valida.")
    for name in ("tick_seconds", "batch_size", "log_every_n_ticks"):
        value = cfg.get(name)
        if isinstance(value, bool) or float(value) <= 0:
            raise ValueError(f"'{name}' debe ser positivo.")
    wall_tick_seconds = cfg.get("wall_tick_seconds", cfg.get("tick_seconds"))
    if isinstance(wall_tick_seconds, bool) or float(wall_tick_seconds) <= 0:
        raise ValueError("'wall_tick_seconds' debe ser positivo.")
    if float(cfg.get("max_duration_seconds", 0)) < 0:
        raise ValueError("'max_duration_seconds' no puede ser negativo.")
    devices = cfg.get("devices")
    if not isinstance(devices, list) or not devices:
        raise ValueError("El escenario no define ningun dispositivo en 'devices'.")
    device_ids: set[str] = set()
    for device in devices:
        if not isinstance(device, dict):
            raise ValueError("Cada dispositivo debe ser un objeto JSON.")
        device_id = str(device.get("device_id", "")).strip()
        route_file = str(device.get("route_file", "")).strip()
        if not device_id or device_id in device_ids:
            raise ValueError("Los dispositivos deben tener IDs no vacios y unicos.")
        if not route_file or not Path(route_file).exists():
            raise ValueError(f"Ruta GPX no encontrada para '{device_id}': {route_file}")
        device_ids.add(device_id)
        for name in ("noise_meters", "speed_variation_pct"):
            if float(device.get(name, 0)) < 0:
                raise ValueError(f"'{name}' no puede ser negativo en '{device_id}'.")


def run(cfg: dict) -> None:
    validate_scenario(cfg)

    device_configs = [
        DeviceScenarioConfig(
            device_id=d["device_id"],
            route_file=d["route_file"],
            noise_meters=float(d.get("noise_meters", 3.5)),
            speed_variation_pct=float(d.get("speed_variation_pct", 1.5)),
            label=d.get("label", d["device_id"]),
        )
        for d in cfg["devices"]
    ]

    engine = ScenarioEngine(device_configs)
    engine.initialize()

    logger.info("=== LocationLab – Scenario Simulator ===")
    logger.info("API objetivo : %s", cfg["api_base_url"])
    logger.info("Tick         : %.1f s", cfg["tick_seconds"])
    logger.info("Dispositivos : %d", len(device_configs))
    for dev_id, label in engine.device_labels:
        logger.info("  ·  %s  →  %s", dev_id, label)
    logger.info(
        "Ventana ruta : %s  →  %s",
        engine.route_start.strftime("%H:%M:%S"),
        engine.route_end.strftime("%H:%M:%S"),
    )

    publisher = ApiPublisher(
        base_url=cfg["api_base_url"],
        use_batch=cfg["use_batch_endpoint"],
        extra_headers=cfg.get("extra_headers", {}),
    )

    tick_s = float(cfg["tick_seconds"])
    wall_tick_s = float(cfg.get("wall_tick_seconds", tick_s))
    batch_size = int(cfg["batch_size"])
    log_every = int(cfg["log_every_n_ticks"])
    max_dur = float(cfg["max_duration_seconds"])

    sim_now = engine.route_start
    route_end = engine.route_end
    wall_start = time.monotonic()

    tick_num = 0
    total_sent = 0
    total_failed = 0

    logger.info("Iniciando simulación… (Ctrl+C para detener)")

    try:
        while True:
            # Fin de ruta
            if sim_now > route_end:
                logger.info("Fin de ruta alcanzado en tick %d.", tick_num)
                break

            # Duración máxima
            elapsed = time.monotonic() - wall_start
            if max_dur > 0 and elapsed >= max_dur:
                logger.info("Duración máxima alcanzada (%.0f s).", max_dur)
                break

            events = engine.get_events(sim_now)

            if events:
                stats = publisher.send_events(events, batch_size=batch_size)
                total_sent += stats["sent"]
                total_failed += stats["failed"]

            if tick_num % log_every == 0:
                logger.info(
                    "Tick %4d | sim=%s | activos=%d | enviados=%d | errores=%d",
                    tick_num,
                    sim_now.strftime("%H:%M:%S"),
                    len(events),
                    total_sent,
                    total_failed,
                )

            sim_now += timedelta(seconds=tick_s)
            tick_num += 1
            time.sleep(wall_tick_s)

    except KeyboardInterrupt:
        logger.info("Simulación detenida por el usuario.")
    finally:
        publisher.close()
        elapsed = time.monotonic() - wall_start
        logger.info(
            "Resumen: %d ticks | %.1f s wall-clock | %d eventos enviados | %d errores",
            tick_num,
            elapsed,
            total_sent,
            total_failed,
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="LocationLab – Simulador de escenarios con rutas individuales"
    )
    parser.add_argument(
        "--scenario",
        metavar="PATH",
        default="scenarios/commute_bilbao.json",
        help="Ruta al JSON del escenario (por defecto: scenarios/commute_bilbao.json)",
    )
    args = parser.parse_args()
    cfg = load_scenario(args.scenario)
    run(cfg)


if __name__ == "__main__":
    main()
