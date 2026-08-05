"""
Detector de grupos: identifica conjuntos de dispositivos que viajan juntos
en base a proximidad espacial, desfase temporal y persistencia mínima.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import NamedTuple

from locationlab.core.geo import haversine_meters


class Sample(NamedTuple):
    device_id: str
    latitude: float
    longitude: float
    timestamp_utc: datetime
    speed_meters_per_second: float = 0.0
    bearing_degrees: float = 0.0


@dataclass
class GroupDetectorConfig:
    """Parámetros configurables del detector."""

    max_distance_meters: float = 30.0
    max_time_skew_seconds: float = 10.0
    min_persistence_ticks: int = 3  # ticks mínimos para consolidar grupo
    max_speed_diff_mps: float = 2.0  # 0 = no filtrar por velocidad


@dataclass
class _GroupState:
    members: frozenset[str]
    persistence_ticks: int = 0


class GroupDetector:
    """
    Detector basado en reglas con persistencia por tick.

    Uso:
        detector = GroupDetector(config)
        for tick in ...:
            samples = [Sample(...), ...]
            groups = detector.tick(samples)
    """

    def __init__(self, config: GroupDetectorConfig | None = None) -> None:
        self._cfg = config or GroupDetectorConfig()
        # clave = frozenset de device_ids, valor = estado del grupo
        self._states: dict[frozenset[str], _GroupState] = {}

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def tick(self, samples: list[Sample]) -> list[frozenset[str]]:
        """
        Procesa un tick de muestras y devuelve los grupos consolidados
        (con persistencia >= min_persistence_ticks).
        """
        instant_groups = self._detect_instant(samples)
        self._update_persistence(instant_groups)
        return [
            s.members
            for s in self._states.values()
            if s.persistence_ticks >= self._cfg.min_persistence_ticks
        ]

    def reset(self) -> None:
        self._states.clear()

    # ------------------------------------------------------------------
    # Lógica interna
    # ------------------------------------------------------------------

    def _detect_instant(self, samples: list[Sample]) -> list[frozenset[str]]:
        """
        Detecta grupos instantáneos: componentes conexas del grafo de proximidad.
        """
        cfg = self._cfg
        n = len(samples)
        # union-find sencillo
        parent = list(range(n))

        def find(i: int) -> int:
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        def union(i: int, j: int) -> None:
            parent[find(i)] = find(j)

        for i in range(n):
            for j in range(i + 1, n):
                a, b = samples[i], samples[j]

                dist = haversine_meters(a.latitude, a.longitude, b.latitude, b.longitude)
                if dist > cfg.max_distance_meters:
                    continue

                dt = abs((a.timestamp_utc - b.timestamp_utc).total_seconds())
                if dt > cfg.max_time_skew_seconds:
                    continue

                if cfg.max_speed_diff_mps > 0:
                    speed_diff = abs(a.speed_meters_per_second - b.speed_meters_per_second)
                    if speed_diff > cfg.max_speed_diff_mps:
                        continue

                union(i, j)

        # agrupar por raíz
        from collections import defaultdict

        components: dict[int, list[str]] = defaultdict(list)
        for i, s in enumerate(samples):
            components[find(i)].append(s.device_id)

        return [
            frozenset(members)
            for members in components.values()
            if len(members) >= 2
        ]

    def _update_persistence(self, instant_groups: list[frozenset[str]]) -> None:
        """
        Incrementa el contador de los grupos activos y decrementa los inactivos.
        Elimina los que llegan a 0.
        """
        active_keys = set()
        for group in instant_groups:
            key = group
            if key not in self._states:
                self._states[key] = _GroupState(members=key)
            self._states[key].persistence_ticks += 1
            active_keys.add(key)

        to_remove = []
        for key, state in self._states.items():
            if key not in active_keys:
                state.persistence_ticks -= 1
                if state.persistence_ticks <= 0:
                    to_remove.append(key)

        for key in to_remove:
            del self._states[key]
