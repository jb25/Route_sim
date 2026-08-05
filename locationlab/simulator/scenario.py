"""
ScenarioEngine – motor de simulación con ruta propia por dispositivo.

A diferencia del SimulationEngine (que replica una ruta única para N dispositivos),
el ScenarioEngine permite asignar un GPX diferente a cada dispositivo. Esto hace
posible simular el escenario de carpooling: el conductor tiene la ruta completa y
cada pasajero tiene su propio "walk-to-pickup" + el tramo compartido.

Las rutas se sincronizan por tiempo de simulación: todos avanzan al mismo instante
(sim_now), por lo que los pasajeros que todavía no han llegado al punto de recogida
emiten su posición real (a pie), y los que ya subieron al coche emiten posiciones
idénticas al conductor (con ruido gaussiano independiente).
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal
from pathlib import Path

from locationlab.core.geo import add_noise_meters
from locationlab.core.models import LocationEvent
from locationlab.simulator.gpx_reader import TrackPoint, load_gpx
from locationlab.simulator.interpolator import interpolate_position


@dataclass
class DeviceScenarioConfig:
    """Configuración de un dispositivo individual en el escenario."""

    device_id: str
    route_file: str
    noise_meters: float = 3.5
    speed_variation_pct: float = 1.5
    label: str = ""  # descripción humana (conductor, pasajero 1…)
    trip_start_utc: datetime | None = None
    app_start: dict | None = None


@dataclass
class _DeviceState:
    cfg: DeviceScenarioConfig
    route: list[TrackPoint]


TripPhase = Literal["waiting", "walking", "on_trip", "arrived"]


class ScenarioEngine:
    """
    Motor de simulación con GPX independiente por dispositivo.

    Uso:
        engine = ScenarioEngine(device_configs)
        engine.initialize()
        events = engine.get_events(sim_now)
    """

    def __init__(self, device_configs: list[DeviceScenarioConfig]) -> None:
        self._device_configs = device_configs
        self._states: list[_DeviceState] = []

    def initialize(self) -> None:
        """Carga los GPX de cada dispositivo y valida que existan."""
        self._states = []
        for cfg in self._device_configs:
            route = load_gpx(cfg.route_file)
            self._states.append(_DeviceState(cfg=cfg, route=route))

    def get_events(self, now: datetime) -> list[LocationEvent]:
        """
        Genera un evento por dispositivo activo en el instante *now*.
        Los dispositivos cuya ruta aún no ha empezado o ya terminó
        emiten su primer/último punto (GPS estático) en lugar de
        desaparecer, para no confundir al backend con gaps.
        """
        events: list[LocationEvent] = []

        for state in self._states:
            result = interpolate_position(state.route, now)
            if result is None:
                continue

            lat, lon, speed, bear = result

            # Ruido gaussiano independiente por dispositivo
            lat, lon = add_noise_meters(lat, lon, state.cfg.noise_meters)

            # Variación de velocidad
            var = state.cfg.speed_variation_pct / 100.0
            speed = max(0.0, speed * (1.0 + random.uniform(-var, var)))

            events.append(
                LocationEvent(
                    device_id=state.cfg.device_id,
                    latitude=round(lat, 7),
                    longitude=round(lon, 7),
                    timestamp_utc=now,
                    accuracy_meters=round(random.uniform(3.0, 6.5), 1),
                    speed_meters_per_second=round(speed, 3),
                    bearing_degrees=round(bear, 1),
                )
            )

        return events

    def phase_at(self, device_id: str, now: datetime) -> TripPhase:
        """Devuelve la fase del trayecto de un dispositivo en tiempo simulado."""
        state = next((item for item in self._states if item.cfg.device_id == device_id), None)
        if state is None:
            raise KeyError(f"Dispositivo no encontrado: {device_id}")

        if now < state.route[0].timestamp_utc:
            return "waiting"
        if now >= state.route[-1].timestamp_utc:
            return "arrived"
        if state.cfg.trip_start_utc and now >= state.cfg.trip_start_utc:
            return "on_trip"
        return "walking"

    # ------------------------------------------------------------------
    # Metadatos de tiempo del escenario
    # ------------------------------------------------------------------

    @property
    def route_start(self) -> datetime:
        """Instante más temprano entre todas las rutas."""
        return min(s.route[0].timestamp_utc for s in self._states)

    @property
    def route_end(self) -> datetime:
        """Instante más tardío entre todas las rutas."""
        return max(s.route[-1].timestamp_utc for s in self._states)

    @property
    def device_labels(self) -> list[tuple[str, str]]:
        """Lista de (device_id, label) para logging."""
        return [(s.cfg.device_id, s.cfg.label or s.cfg.device_id) for s in self._states]
