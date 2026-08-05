"""
Punto de entrada del simulador.

Uso:
    python -m locationlab.simulator.main [--config simulator_config.json]

O directamente:
    python locationlab/simulator/main.py

El simulador itera por la ruta GPX enviando un tick por segundo (configurable)
a la API objetivo. Loguea estadísticas cada N ticks.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from locationlab.simulator.engine import SimulationEngine
from locationlab.simulator.publisher import ApiPublisher

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("simulator")

# ---------------------------------------------------------------------------
# Configuración por defecto
# ---------------------------------------------------------------------------

DEFAULT_CONFIG = {
    "api_base_url": "http://localhost:8080",
    "route_file": "routes/sample-route.gpx",
    "device_count": 20,
    "tick_seconds": 1.0,
    "batch_size": 20,
    "start_delay_jitter_ms": 1500,
    "position_noise_meters": 4.0,
    "speed_variation_pct": 2.0,
    "use_batch_endpoint": True,
    "log_every_n_ticks": 10,
    # Cabeceras extra para autenticación con Tribbu u otra app objetivo.
    # Añade aquí Authorization, Cookie, X-Auth-Token, etc.
    "extra_headers": {},
    # Duración máxima en segundos (0 = sin límite, sigue hasta fin de ruta)
    "max_duration_seconds": 0,
}


def load_config(path: str | None) -> dict:
    cfg = dict(DEFAULT_CONFIG)
    if path:
        config_path = Path(path)
        if config_path.exists():
            with config_path.open("r", encoding="utf-8") as f:
                cfg.update(json.load(f))
            logger.info("Configuración cargada desde %s", config_path)
        else:
            logger.warning("Archivo de config no encontrado: %s. Usando valores por defecto.", path)
    return cfg


# ---------------------------------------------------------------------------
# Bucle principal
# ---------------------------------------------------------------------------

def run(cfg: dict) -> None:
    logger.info("=== LocationLab Simulator ===")
    logger.info("API objetivo : %s", cfg["api_base_url"])
    logger.info("Ruta GPX     : %s", cfg["route_file"])
    logger.info("Dispositivos : %d", cfg["device_count"])
    logger.info("Tick         : %.1f s", cfg["tick_seconds"])
    logger.info("Lote         : %d eventos/petición", cfg["batch_size"])
    logger.info("Noise        : %.1f m", cfg["position_noise_meters"])

    # Motor de simulación
    engine = SimulationEngine(
        route_file=cfg["route_file"],
        device_count=cfg["device_count"],
        start_delay_jitter_ms=float(cfg["start_delay_jitter_ms"]),
        position_noise_meters=float(cfg["position_noise_meters"]),
        speed_variation_pct=float(cfg["speed_variation_pct"]),
    )
    engine.initialize()
    logger.info(
        "Ruta cargada: %d puntos  [%s → %s]",
        len(engine._base_route),
        engine.route_start,
        engine.route_end,
    )

    # Publicador HTTP
    publisher = ApiPublisher(
        base_url=cfg["api_base_url"],
        use_batch=cfg["use_batch_endpoint"],
        extra_headers=cfg.get("extra_headers", {}),
    )

    tick_s = float(cfg["tick_seconds"])
    batch_size = int(cfg["batch_size"])
    log_every = int(cfg["log_every_n_ticks"])
    max_dur = float(cfg["max_duration_seconds"])

    # La simulación viaja en "tiempo de ruta" a partir de route_start
    # para no depender del reloj real. Si quieres tiempo real, cambia
    # sim_now por datetime.now(timezone.utc).
    route_start = engine.route_start
    route_end = engine.route_end

    sim_now = route_start
    wall_start = time.monotonic()

    tick_num = 0
    total_sent = 0
    total_failed = 0

    logger.info("Iniciando simulación… (Ctrl+C para detener)")

    try:
        while True:
            # Fin de ruta
            if route_end and sim_now > route_end:
                logger.info("Fin de ruta alcanzado en tick %d.", tick_num)
                break

            # Duración máxima
            elapsed = time.monotonic() - wall_start
            if max_dur > 0 and elapsed >= max_dur:
                logger.info("Duración máxima (%.0f s) alcanzada.", max_dur)
                break

            # Generar y enviar eventos
            events = engine.get_events(sim_now)
            if events:
                stats = publisher.send_events(events, batch_size=batch_size)
                total_sent += stats["sent"]
                total_failed += stats["failed"]

            # Log periódico
            if tick_num % log_every == 0:
                logger.info(
                    "Tick %4d | sim_t=%s | events=%d | enviados=%d | errores=%d",
                    tick_num,
                    sim_now.strftime("%H:%M:%S"),
                    len(events),
                    total_sent,
                    total_failed,
                )

            # Avanzar reloj de simulación y esperar
            sim_now += timedelta(seconds=tick_s)
            tick_num += 1

            # Throttle: esperar el tiempo de tick real
            time.sleep(tick_s)

    except KeyboardInterrupt:
        logger.info("Simulación detenida por el usuario.")
    finally:
        publisher.close()
        elapsed = time.monotonic() - wall_start
        logger.info(
            "Resumen: %d ticks | %.1f s | %d eventos enviados | %d errores",
            tick_num,
            elapsed,
            total_sent,
            total_failed,
        )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="LocationLab – Simulador de dispositivos GPS")
    parser.add_argument(
        "--config",
        metavar="PATH",
        help="Ruta al archivo JSON de configuración (por defecto: simulator_config.json)",
        default="simulator_config.json",
    )
    args = parser.parse_args()
    cfg = load_config(args.config)
    run(cfg)


if __name__ == "__main__":
    main()
