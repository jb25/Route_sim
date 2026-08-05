"""
Demo en vivo del carpool Lemoa → Mondragón.

Velocidad por defecto: 30x  → el viaje de 57 min se ve en ~2 min.
El GPS de cada dispositivo se actualiza cada 1 segundo real (realista).

Uso:
    python run_demo.py               # 30x velocidad, con API local si está activa
    python run_demo.py --speed 60    # 60x velocidad (~1 min de demo)
    python run_demo.py --no-api      # solo display, sin enviar a la API
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timedelta, timezone

from locationlab.core.geo import haversine_meters
from locationlab.simulator.scenario import DeviceScenarioConfig, ScenarioEngine
from locationlab.simulator.scenario_main import load_scenario

# ── Hitos de la ruta ──────────────────────────────────────────────────────────
_MILESTONES = [
    (datetime(2026, 7, 14, 7, 10,  0, tzinfo=timezone.utc), "Recogida P1 en Amorebieta"),
    (datetime(2026, 7, 14, 7, 22, 30, tzinfo=timezone.utc), "Recogida P2 en Durango"),
    (datetime(2026, 7, 14, 7, 40, 30, tzinfo=timezone.utc), "Recogida P3 en Eibar"),
    (datetime(2026, 7, 14, 7, 57, 30, tzinfo=timezone.utc), "LLEGADA – Poligono Industrial Mondragon"),
]

_PHASES = [
    (datetime(2026, 7, 14, 7, 11, 30, tzinfo=timezone.utc), "BI-635 Lemoa -> Amorebieta   [solo conductor]"),
    (datetime(2026, 7, 14, 7, 24,  0, tzinfo=timezone.utc), "A-8  Amorebieta -> Durango   [conductor + P1]"),
    (datetime(2026, 7, 14, 7, 42,  0, tzinfo=timezone.utc), "AP-8 Durango -> Eibar        [conductor + P1 + P2]"),
    (datetime(2026, 7, 14, 7, 57, 30, tzinfo=timezone.utc), "Eibar -> Mondragon           [los 4 juntos]"),
]


def _phase(t: datetime) -> str:
    for cutoff, label in _PHASES:
        if t < cutoff:
            return label
    return "DESTINO – Poligono Industrial Mondragon  *** LLEGADA ***"


def _next_milestone(t: datetime) -> str:
    for ts, label in _MILESTONES:
        if t < ts:
            secs = int((ts - t).total_seconds())
            return f"{label}  (en {secs // 60:02d}:{secs % 60:02d} sim)"
    return "Fin de ruta"


def _device_status(speed: float) -> str:
    if speed > 5:
        return "EN COCHE  "
    if speed > 0.2:
        return "CAMINANDO "
    return "ESPERANDO "


def _device_icon(device_id: str, speed: float) -> str:
    if "conductor" in device_id:
        return "CAR"
    key = next((k for k in ("amorebieta", "durango", "eibar") if k in device_id), "???")
    icons = {"amorebieta": "P1 ", "durango": "P2 ", "eibar": "P3 "}
    return icons.get(key, "???")


def _render(
    sim_now: datetime,
    route_start: datetime,
    route_end: datetime,
    events,
    sent: int,
    failed: int,
    tick: int,
    speed: int,
) -> list[str]:
    W = 70
    total_s = (route_end - route_start).total_seconds()
    elapsed_s = max(0.0, (sim_now - route_start).total_seconds())
    prog = min(1.0, elapsed_s / total_s)
    bar = "=" * int(38 * prog) + "-" * (38 - int(38 * prog))

    in_car = [e for e in events if e.speed_meters_per_second > 5]
    walking = [e for e in events if 0.2 < e.speed_meters_per_second <= 5]
    waiting = [e for e in events if e.speed_meters_per_second <= 0.2]

    # Grupo en coche
    if len(in_car) >= 2:
        ref = in_car[0]
        max_d = max(
            haversine_meters(ref.latitude, ref.longitude, e.latitude, e.longitude)
            for e in in_car[1:]
        )
        members = " + ".join(_device_icon(e.device_id, e.speed_meters_per_second) for e in in_car)
        grupo = f"{members}   dispersion={max_d:.1f} m"
    elif len(in_car) == 1:
        grupo = f"{_device_icon(in_car[0].device_id, in_car[0].speed_meters_per_second)} (solo)"
    else:
        grupo = "ninguno aun en marcha"

    lines = [
        "=" * W,
        f"  LocationLab – Carpool Bilbao  (velocidad {speed}x)",
        "=" * W,
        f"  Hora sim   : {sim_now.strftime('%H:%M:%S')} UTC         Tick #{tick}",
        f"  Progreso   : [{bar}] {prog * 100:.0f}%",
        f"  Fase       : {_phase(sim_now)}",
        f"  Siguiente  : {_next_milestone(sim_now)}",
        "-" * W,
        f"  {'[Dev]':<5}  {'Dispositivo':<24}  {'Lat':>9}  {'Lon':>10}  {'m/s':>6}  Estado",
        "-" * W,
    ]

    for e in events:
        icon = _device_icon(e.device_id, e.speed_meters_per_second)
        status = _device_status(e.speed_meters_per_second)
        name = e.device_id[:24]
        lines.append(
            f"  [{icon}]  {name:<24}  {e.latitude:>9.5f}  {e.longitude:>10.5f}"
            f"  {e.speed_meters_per_second:>6.1f}  {status}"
        )

    lines += [
        "-" * W,
        f"  Grupo en coche  : {grupo}",
        f"  En coche: {len(in_car):>2}   Caminando: {len(walking):>2}   Esperando: {len(waiting):>2}",
        f"  Eventos enviados: {sent:>5}   Errores: {failed:>3}",
        "=" * W,
    ]
    return lines


def run_demo(speed: int = 30, use_api: bool = True) -> None:
    # ── Cargar escenario ──────────────────────────────────────────────────────
    cfg = load_scenario("scenarios/commute_bilbao.json")
    device_configs = [
        DeviceScenarioConfig(
            device_id=d["device_id"],
            route_file=d["route_file"],
            noise_meters=d.get("noise_meters", 3.5),
            speed_variation_pct=d.get("speed_variation_pct", 1.5),
            label=d.get("label", ""),
        )
        for d in cfg["devices"]
    ]
    engine = ScenarioEngine(device_configs)
    engine.initialize()

    # ── Publicador HTTP (opcional) ─────────────────────────────────────────────
    publisher = None
    if use_api:
        try:
            import httpx
            r = httpx.get("http://localhost:8080/health", timeout=1.5)
            if r.status_code == 200:
                from locationlab.simulator.publisher import ApiPublisher
                publisher = ApiPublisher(base_url="http://localhost:8080", use_batch=True)
                print("\n  API local detectada en http://localhost:8080 – enviando eventos")
            else:
                print("\n  API local no disponible – modo display solo")
        except Exception:
            print("\n  API local no disponible – modo display solo")

    route_start = engine.route_start
    route_end = engine.route_end
    total_sim_min = (route_end - route_start).total_seconds() / 60
    total_real_s = (route_end - route_start).total_seconds() / speed

    print(f"  Ruta: {route_start.strftime('%H:%M')} → {route_end.strftime('%H:%M')} UTC"
          f"  ({total_sim_min:.0f} min de viaje simulado)")
    print(f"  Demo durara aprox. {total_real_s:.0f} segundos reales ({speed}x)")
    print(f"  GPS update: cada 1 s real = {speed} s sim  |  Ctrl+C para detener\n")
    time.sleep(2)

    sim_now = route_start
    sent = 0
    failed = 0
    tick = 0
    prev_n_lines = 0

    try:
        while sim_now <= route_end:
            t0 = time.monotonic()

            events = engine.get_events(sim_now)

            if publisher and events:
                stats = publisher.send_events(events, batch_size=10)
                sent += stats["sent"]
                failed += stats["failed"]

            lines = _render(sim_now, route_start, route_end, events, sent, failed, tick, speed)

            # Sobreescribir bloque anterior (ANSI cursor up + clear to end)
            if prev_n_lines > 0:
                sys.stdout.write(f"\033[{prev_n_lines}A\033[J")

            output = "\n".join(lines) + "\n"
            sys.stdout.write(output)
            sys.stdout.flush()
            prev_n_lines = len(lines) + 1

            sim_now += timedelta(seconds=speed)  # 1 real second = speed sim seconds
            tick += 1

            # Esperar el resto del segundo real
            elapsed = time.monotonic() - t0
            sleep_t = max(0.0, 1.0 - elapsed)
            time.sleep(sleep_t)

    except KeyboardInterrupt:
        print("\n\n  Simulacion detenida por el usuario.")
    finally:
        if publisher:
            publisher.close()
        print(f"\n  Fin.  Ticks: {tick}  |  Enviados: {sent}  |  Errores: {failed}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Demo en vivo del carpool Bilbao → Mondragon")
    parser.add_argument(
        "--speed", type=int, default=30,
        help="Factor de aceleracion (default: 30 → 57 min en ~2 min)"
    )
    parser.add_argument(
        "--no-api", action="store_true",
        help="Solo display, no enviar eventos a la API"
    )
    args = parser.parse_args()
    run_demo(speed=args.speed, use_api=not args.no_api)


if __name__ == "__main__":
    main()
