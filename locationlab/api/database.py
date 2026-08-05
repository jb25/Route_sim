"""
Capa de persistencia SQLite para la API.
Usa sqlite3 nativo para mantener cero dependencias adicionales.
"""
from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
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
                member_count INTEGER NOT NULL,
                last_seen_utc TEXT NOT NULL DEFAULT ''
            );
            """
        )
        columns = {row[1] for row in conn.execute("PRAGMA table_info(detected_groups)")}
        if "last_seen_utc" not in columns:
            conn.execute(
                "ALTER TABLE detected_groups ADD COLUMN last_seen_utc TEXT NOT NULL DEFAULT ''"
            )
            conn.execute(
                "UPDATE detected_groups SET last_seen_utc = detected_at "
                "WHERE last_seen_utc = ''"
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
            (device_id, latitude, longitude, timestamp_utc.isoformat(),
             accuracy_meters, speed_mps, bearing_degrees, received),
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


def insert_group(
    group_id: str,
    device_ids: list[str],
    detected_at: datetime,
    last_seen_utc: datetime | None = None,
) -> None:
    device_key = ",".join(sorted(device_ids))
    last_seen = (last_seen_utc or detected_at).isoformat()
    with _lock, get_connection() as conn:
        updated = conn.execute(
            """
            UPDATE detected_groups
            SET group_id = ?, detected_at = ?, member_count = ?, last_seen_utc = ?
            WHERE device_ids = ?
            """,
            (group_id, detected_at.isoformat(), len(device_ids), last_seen, device_key),
        )
        if updated.rowcount == 0:
            conn.execute(
                """
                INSERT INTO detected_groups
                    (group_id, device_ids, detected_at, member_count, last_seen_utc)
                VALUES (?, ?, ?, ?, ?)
                """,
                (group_id, device_key, detected_at.isoformat(), len(device_ids), last_seen),
            )


# ---------------------------------------------------------------------------
# Operaciones de lectura
# ---------------------------------------------------------------------------

def get_recent_samples(
    window_seconds: int = 15,
    reference_timestamp: datetime | None = None,
) -> list[dict]:
    """Devuelve una muestra por dispositivo alrededor del tiempo simulado indicado."""
    with get_connection() as conn:
        reference = reference_timestamp or _latest_event_timestamp(conn)
        if reference is None:
            reference = datetime.now(timezone.utc)
        window_start = reference - timedelta(seconds=window_seconds)
        rows = conn.execute(
            """
            WITH ranked AS (
                SELECT device_id, latitude, longitude, timestamp_utc,
                       speed_mps, bearing_degrees,
                       ROW_NUMBER() OVER (
                           PARTITION BY device_id
                           ORDER BY datetime(timestamp_utc) DESC, id DESC
                       ) AS row_number
                FROM location_events
                WHERE datetime(timestamp_utc) >= datetime(?)
                  AND datetime(timestamp_utc) <= datetime(?)
            )
            SELECT device_id, latitude, longitude, timestamp_utc,
                   speed_mps, bearing_degrees
            FROM ranked
            WHERE row_number = 1
            ORDER BY device_id
            """,
            (window_start.isoformat(), reference.isoformat()),
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


def get_current_groups(
    reference_timestamp: datetime | None = None,
    window_seconds: int = 15,
) -> list[dict]:
    """Devuelve grupos cuya ultima muestra sigue dentro de la ventana activa."""
    with get_connection() as conn:
        reference = reference_timestamp or _latest_event_timestamp(conn)
        if reference is None:
            reference = datetime.now(timezone.utc)
        window_start = reference - timedelta(seconds=window_seconds)
        rows = conn.execute(
            """
            SELECT group_id, device_ids, detected_at, member_count
            FROM detected_groups
            WHERE datetime(last_seen_utc) >= datetime(?)
            ORDER BY detected_at DESC
            LIMIT 50
            """,
            (window_start.isoformat(),),
        ).fetchall()
    return [dict(r) for r in rows]


def _latest_event_timestamp(conn: sqlite3.Connection) -> datetime | None:
    value = conn.execute("SELECT MAX(timestamp_utc) FROM location_events").fetchone()[0]
    return datetime.fromisoformat(value) if value else None
