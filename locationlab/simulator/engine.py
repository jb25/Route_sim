"""
Motor de simulación.
Gestiona el estado de N dispositivos virtuales y produce eventos de localización
en cada tick usando interpolación sobre la ruta GPX.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from locationlab.core.geo import add_noise_meters
from locationlab.core.models import LocationEvent
from locationlab.simulator.gpx_reader import TrackPoint, load_gpx
from locationlab.simulator.interpolator import build_time_offset_route, interpolate_position


@dataclass
class DeviceState:
    device_id: str
    route: list[TrackPoint]  # ruta personal (con offset temporal)
    accuracy_meters: float = 5.0
    speed_variation_pct: float = 2.0  # ±% de variación de velocidad
    noise_meters: float = 4.0


@dataclass
class SimulationEngine:
    """
    Gestiona todos los dispositivos virtuales.

    Parámetros (se leen de SimulationConfig en main del simulador):
    - route_file:              ruta al archivo GPX
    - device_count:            número de dispositivos a simular
    - start_delay_jitter_ms:   jitter máximo en el inicio (ms)
    - position_noise_meters:   radio máximo de ruido gaussiano en posición
    - speed_variation_pct:     variación de velocidad por dispositivo
    """

    route_file: str
    device_count: int = 20
    start_delay_jitter_ms: float = 1500.0
    position_noise_meters: float = 4.0
    speed_variation_pct: float = 2.0
    device_prefix: str = "dev"

    _devices: list[DeviceState] = field(default_factory=list, init=False)
    _base_route: list[TrackPoint] = field(default_factory=list, init=False)

    def initialize(self) -> None:
        """Carga la ruta y crea los dispositivos virtuales."""
        self._base_route = load_gpx(self.route_file)
        self._devices = []

        for i in range(self.device_count):
            device_id = f"{self.device_prefix}-{i:03d}"

            # Pequeño desfase temporal por dispositivo
            jitter_s = random.uniform(
                -self.start_delay_jitter_ms / 1000.0,
                self.start_delay_jitter_ms / 1000.0,
            )
            offset_route = build_time_offset_route(self._base_route, jitter_s)

            self._devices.append(
                DeviceState(
                    device_id=device_id,
                    route=offset_route,
                    accuracy_meters=random.uniform(4.0, 8.0),
                    speed_variation_pct=self.speed_variation_pct,
                    noise_meters=self.position_noise_meters,
                )
            )

    def get_events(self, now: datetime | None = None) -> list[LocationEvent]:
        """
        Genera un evento por dispositivo para el instante *now*.
        Los dispositivos cuya ruta ha terminado emiten su última posición.
        """
        if now is None:
            now = datetime.now(timezone.utc)

        events: list[LocationEvent] = []
        for dev in self._devices:
            result = interpolate_position(dev.route, now)
            if result is None:
                continue

            lat, lon, speed, bear = result

            # Ruido espacial gaussiano
            lat, lon = add_noise_meters(lat, lon, dev.noise_meters)

            # Variación de velocidad
            speed_factor = 1.0 + random.uniform(
                -dev.speed_variation_pct / 100.0,
                dev.speed_variation_pct / 100.0,
            )
            speed = max(0.0, speed * speed_factor)

            events.append(
                LocationEvent(
                    device_id=dev.device_id,
                    latitude=round(lat, 7),
                    longitude=round(lon, 7),
                    timestamp_utc=now,
                    accuracy_meters=round(dev.accuracy_meters, 1),
                    speed_meters_per_second=round(speed, 3),
                    bearing_degrees=round(bear, 1),
                )
            )

        return events

    @property
    def route_start(self) -> datetime | None:
        return self._base_route[0].timestamp_utc if self._base_route else None

    @property
    def route_end(self) -> datetime | None:
        return self._base_route[-1].timestamp_utc if self._base_route else None
