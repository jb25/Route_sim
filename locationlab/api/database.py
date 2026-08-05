"""
Capa de persistencia SQLite para la API.
Usa sqlite3 nativo para mantener cero dependencias adicionales.
"""
from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator

_DB_PATH = Path(__file__).parent.parent.parent / "locationlab.db"
_lock = threading.Lock()


def get_db_path() -> Path:
    return _DB_PATH


def set_db_path(path: Path) -> None:
    global _DB_PATH
    _DB_PATH = path


@contextmanager
def get_connection() -> Generator[sqlite3.Connection, None, None]:
    conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """Crea las tablas si no existen."""
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS location_events (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id        TEXT    NOT NULL,
                latitude         REAL    NOT NULL,
                longitude        REAL    NOT NULL,
                timestamp_utc    TEXT    NOT NULL,
                accuracy_meters  REAL    NOT NULL DEFAULT 5.0,
                speed_mps        REAL    NOT NULL DEFAULT 0.0,
                bearing_degrees  REAL    NOT NULL DEFAULT 0.0,
                received_utc     TEXT    NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_le_device_time
                ON location_events (device_id, timestamp_utc DESC);

            CREATE TABLE IF NOT EXISTS detected_groups (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id     TEXT    NOT NULL,
                device_ids   TEXT    NOT NULL,
                detected_at  TEXT    NOT NULL,
                member_count INTEGER NOT NULL
            );
            """
        )


# ---------------------------------------------------------------------------
# Operaciones de escritura
# ---------------------------------------------------------------------------

def insert_event(
    device_id: str,
    latitude: float,
    longitude: float,
    timestamp_utc: datetime,
    accuracy_meters: float,
    speed_mps: float,
    bearing_degrees: float,
) -> int:
    received = datetime.now(timezone.utc).isoformat()
    with _lock, get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO location_events
                (device_id, latitude, longitude, timestamp_utc,
                 accuracy_meters, speed_mps, bearing_degrees, received_utc)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                device_id,
                latitude,
                longitude,
                timestamp_utc.isoformat(),
                accuracy_meters,
                speed_mps,
                bearing_degrees,
                received,
            ),
        )
        return cur.lastrowid  # type: ignore[return-value]


def insert_events_batch(events: list[dict]) -> int:
    """Inserta múltiples eventos en una sola transacción. Devuelve el nº insertado."""
    received = datetime.now(timezone.utc).isoformat()
    rows = [
        (
            e["device_id"],
            e["latitude"],
            e["longitude"],
            e["timestamp_utc"],
            e["accuracy_meters"],
            e["speed_mps"],
            e["bearing_degrees"],
            received,
        )
        for e in events
    ]
    with _lock, get_connection() as conn:
        conn.executemany(
            """
            INSERT INTO location_events
                (device_id, latitude, longitude, timestamp_utc,
                 accuracy_meters, speed_mps, bearing_degrees, received_utc)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        return len(rows)


def insert_group(group_id: str, device_ids: list[str], detected_at: datetime) -> None:
    with _lock, get_connection() as conn:
        conn.execute(
            """
            INSERT INTO detected_groups (group_id, device_ids, detected_at, member_count)
            VALUES (?, ?, ?, ?)
            """,
            (group_id, ",".join(sorted(device_ids)), detected_at.isoformat(), len(device_ids)),
        )


# ---------------------------------------------------------------------------
# Operaciones de lectura
# ---------------------------------------------------------------------------

def get_recent_samples(window_seconds: int = 15) -> list[dict]:
    """Devuelve la muestra más reciente de cada dispositivo en la ventana dada."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT device_id,
                   latitude,
                   longitude,
                   timestamp_utc,
                   speed_mps,
                   bearing_degrees
            FROM location_events
            WHERE timestamp_utc >= datetime('now', ? || ' seconds')
            GROUP BY device_id
            HAVING timestamp_utc = MAX(timestamp_utc)
            ORDER BY device_id
            """,
            (f"-{window_seconds}",),
        ).fetchall()
    return [dict(r) for r in rows]


def get_device_history(device_id: str, limit: int = 100) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT device_id, latitude, longitude, timestamp_utc,
                   accuracy_meters, speed_mps, bearing_degrees
            FROM location_events
            WHERE device_id = ?
            ORDER BY timestamp_utc DESC
            LIMIT ?
            """,
            (device_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def get_known_devices() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT le.device_id,
                   le.timestamp_utc  AS last_seen,
                   le.latitude       AS last_latitude,
                   le.longitude      AS last_longitude,
                   cnt.event_count
            FROM location_events le
            INNER JOIN (
                SELECT device_id,
                       MAX(timestamp_utc) AS max_ts,
                       COUNT(*)           AS event_count
                FROM location_events
                GROUP BY device_id
            ) cnt ON le.device_id = cnt.device_id
                 AND le.timestamp_utc = cnt.max_ts
            ORDER BY le.timestamp_utc DESC
            """,
        ).fetchall()
    return [dict(r) for r in rows]


def get_current_groups() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT group_id, device_ids, detected_at, member_count
            FROM detected_groups
            ORDER BY detected_at DESC
            LIMIT 50
            """,
        ).fetchall()
    return [dict(r) for r in rows]
