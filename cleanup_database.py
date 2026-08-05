"""Limpia datos SQLite antiguos de una ejecucion local de LocationLab."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone

from locationlab.api import database as db


def main() -> None:
    parser = argparse.ArgumentParser(description="Limpia datos antiguos de LocationLab")
    parser.add_argument(
        "--retention-days",
        type=float,
        default=7,
        help="Conservar este numero de dias hacia atras (por defecto: 7)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Solo contar los registros que se eliminarian",
    )
    args = parser.parse_args()
    if args.retention_days <= 0:
        parser.error("--retention-days debe ser positivo")

    cutoff = datetime.now(timezone.utc) - timedelta(days=args.retention_days)
    if args.dry_run:
        result = db.count_expired_data(cutoff)
        action = "se eliminarian"
    else:
        result = db.delete_expired_data(cutoff)
        action = "eliminados"

    print(
        f"Corte UTC: {cutoff.isoformat()} | "
        f"eventos {action}: {result['location_events']} | "
        f"grupos {action}: {result['detected_groups']}"
    )


if __name__ == "__main__":
    main()