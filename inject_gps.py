"""
inject_gps.py – Inyecta posiciones GPS del ScenarioEngine a N emuladores
                Android simultáneamente via ADB.

Cada emulador recibe la posición del dispositivo que tiene asignado.
Las inyecciones se ejecutan en paralelo (un hilo por emulador) para que
todos los GPS se actualicen en el mismo tick sin bloqueos.

Prerequisito: Android SDK instalado y 'adb' en el PATH.

Uso:
    python inject_gps.py                        # usa emulator_config.json
    python inject_gps.py --config mi_config.json
    python inject_gps.py --detect               # lista emuladores conectados
    python inject_gps.py --speed 1              # tiempo real (57 min)
    python inject_gps.py --speed 30             # 30x velocidad (~2 min)
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from locationlab.core.geo import haversine_meters
from locationlab.simulator.scenario import DeviceScenarioConfig, ScenarioEngine
from locationlab.simulator.scenario_main import load_scenario


# ── Helpers ADB ───────────────────────────────────────────────────────────────

def _find_adb() -> str:
    """
    Busca el ejecutable adb en el PATH y en rutas habituales del SDK.
    Devuelve la ruta completa o 'adb' si está en el PATH.
    """
    import shutil
    if shutil.which("adb"):
        return "adb"
    candidates = [
        r"C:\Android\platform-tools\adb.exe",
        r"C:\Android\Sdk\platform-tools\adb.exe",
        str(Path.home() / "AppData/Local/Android/Sdk/platform-tools/adb.exe"),
    ]
    for c in candidates:
        if Path(c).exists():
            return c
    return "adb"  # fallback: fallará con mensaje claro


_ADB = _find_adb()


def adb_devices() -> list[str]:
    """Devuelve los seriales de todos los emuladores conectados."""
    try:
        result = subprocess.run(
            [_ADB, "devices"], capture_output=True, text=True, timeout=5
        )
        serials = []
        for line in result.stdout.splitlines()[1:]:
            if "emulator" in line and "device" in line:
                serials.append(line.split()[0])
        return serials
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []


def adb_geo_fix(serial: str, latitude: float, longitude: float, altitude: float = 0.0) -> bool:
    """
    Inyecta posición GPS a un emulador via 'adb emu geo fix'.
    NOTA: el orden ADB es <lon> <lat> (invertido respecto al convenio lat/lon).
    """
    try:
        result = subprocess.run(
            [_ADB, "-s", serial, "emu", "geo", "fix",
             f"{longitude:.7f}", f"{latitude:.7f}", f"{altitude:.1f}"],
            capture_output=True, text=True, timeout=3
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def adb_check() -> bool:
    """Verifica que adb esté disponible."""
    try:
        subprocess.run([_ADB, "version"], capture_output=True, timeout=3)
        return True
    except FileNotFoundError:
        return False


# ── Modelos de configuración ──────────────────────────────────────────────────

@dataclass
class EmulatorMapping:
    serial: str      # ej. "emulator-5554"
    device_id: str   # ej. "conductor-lemoa"
    label: str = ""


# ── Motor principal ───────────────────────────────────────────────────────────

def _inject_one(serial: str, lat: float, lon: float, alt: float) -> tuple[str, bool]:
    """Función ejecutada en hilo independiente para un emulador."""
    ok = adb_geo_fix(serial, lat, lon, alt)
    return serial, ok


def run_injection(cfg: dict, speed: int) -> None:
    """
    Bucle principal: cada tick inyecta GPS a todos los emuladores en paralelo.
    """
    # Cargar escenario
    scenario_cfg = load_scenario(cfg["scenario"])
    device_cfgs = [
        DeviceScenarioConfig(
            device_id=d["device_id"],
            route_file=d["route_file"],
            noise_meters=d.get("noise_meters", 3.5),
            speed_variation_pct=d.get("speed_variation_pct", 1.5),
            label=d.get("label", ""),
        )
        for d in scenario_cfg["devices"]
    ]
    engine = ScenarioEngine(device_cfgs)
    engine.initialize()

    # Mapeo serial → device_id
    mappings: list[EmulatorMapping] = [
        EmulatorMapping(
            serial=m["serial"],
            device_id=m["device_id"],
            label=m.get("label", m["device_id"]),
        )
        for m in cfg["emulator_map"]
    ]

    # Verificar emuladores activos
    active_serials = adb_devices()
    active_mappings = [m for m in mappings if m.serial in active_serials]
    inactive = [m for m in mappings if m.serial not in active_serials]

    print("\n" + "=" * 65)
    print("  LocationLab – GPS Injector  (4 emuladores Android)")
    print("=" * 65)
    print(f"  Velocidad   : {speed}x  |  Tick: 1 s real = {speed} s sim")
    print(f"  Activos     : {len(active_mappings)}/{len(mappings)}")
    for m in active_mappings:
        print(f"    [OK] {m.serial:<20}  →  {m.label}")
    for m in inactive:
        print(f"    [--] {m.serial:<20}  →  {m.label}  (no detectado)")

    if not active_mappings:
        print("\n  ERROR: Ningún emulador detectado. Lanza los AVD primero.")
        print("         Usa: python inject_gps.py --detect")
        sys.exit(1)

    # Construir lookup device_id → serial
    dev_to_serial: dict[str, str] = {m.device_id: m.serial for m in active_mappings}

    sim_now = engine.route_start
    route_end = engine.route_end
    total_min = (route_end - sim_now).total_seconds() / 60
    real_s = (route_end - sim_now).total_seconds() / speed

    print(f"\n  Ruta: {sim_now.strftime('%H:%M')} → {route_end.strftime('%H:%M')} UTC"
          f"  ({total_min:.0f} min sim  →  {real_s:.0f} s reales)")
    print("  Iniciando en 2 s... (Ctrl+C para detener)\n")
    time.sleep(2)

    tick = 0
    ok_total = 0
    err_total = 0
    prev_lines = 0
    W = 65

    try:
        while sim_now <= route_end:
            t0 = time.monotonic()
            events = engine.get_events(sim_now)

            # Filtrar solo los eventos de emuladores activos
            tasks = []
            for e in events:
                serial = dev_to_serial.get(e.device_id)
                if serial:
                    tasks.append((serial, e.latitude, e.longitude, 0.0, e))

            # Inyectar en paralelo
            tick_ok = 0
            tick_err = 0
            results: dict[str, tuple[float, float, float]] = {}

            with ThreadPoolExecutor(max_workers=len(tasks) or 1) as pool:
                futures = {
                    pool.submit(_inject_one, serial, lat, lon, alt): (dev_e.device_id, lat, lon, dev_e.speed_meters_per_second)
                    for serial, lat, lon, alt, dev_e in tasks
                }
                for future in as_completed(futures):
                    dev_id, lat, lon, spd = futures[future]
                    serial_result, ok = future.result()
                    if ok:
                        tick_ok += 1
                        ok_total += 1
                    else:
                        tick_err += 1
                        err_total += 1
                    results[dev_id] = (lat, lon, spd)

            # Display
            lines = _render(sim_now, engine.route_start, route_end,
                            events, results, tick, speed, ok_total, err_total,
                            active_mappings, dev_to_serial, W)

            if prev_lines > 0:
                sys.stdout.write(f"\033[{prev_lines}A\033[J")

            output = "\n".join(lines) + "\n"
            sys.stdout.write(output)
            sys.stdout.flush()
            prev_lines = len(lines) + 1

            sim_now += timedelta(seconds=speed)
            tick += 1
            elapsed = time.monotonic() - t0
            time.sleep(max(0.0, 1.0 - elapsed))

    except KeyboardInterrupt:
        print("\n\n  Detenido.")
    finally:
        elapsed_real = tick
        print(f"\n  Fin. Ticks: {tick} | GPS OK: {ok_total} | Errores: {err_total}\n")


def _render(sim_now, route_start, route_end, events, results,
            tick, speed, ok_total, err_total, mappings, dev_to_serial, W) -> list[str]:
    prog = min(1.0, (sim_now - route_start).total_seconds() /
               max(1, (route_end - route_start).total_seconds()))
    bar = "=" * int(38 * prog) + "-" * (38 - int(38 * prog))

    lines = [
        "=" * W,
        f"  GPS Injector – {len(mappings)} emuladores  ({speed}x velocidad)",
        "=" * W,
        f"  Hora sim : {sim_now.strftime('%H:%M:%S')} UTC   Tick #{tick}",
        f"  Progreso : [{bar}] {prog * 100:.0f}%",
        "-" * W,
        f"  {'Serial':<20}  {'Lat':>9}  {'Lon':>10}  {'m/s':>6}  Estado",
        "-" * W,
    ]

    for m in mappings:
        serial = m.serial
        dev_id = m.device_id
        if dev_id in results:
            lat, lon, spd = results[dev_id]
            estado = "EN COCHE  " if spd > 5 else ("CAMINANDO " if spd > 0.2 else "ESPERANDO ")
            lines.append(
                f"  {serial:<20}  {lat:>9.5f}  {lon:>10.5f}  {spd:>6.1f}  {estado}"
            )
        else:
            lines.append(f"  {serial:<20}  {'–':>9}  {'–':>10}  {'–':>6}  Sin datos")

    # Dispersión del grupo en coche
    car_events = [e for e in events if e.speed_meters_per_second > 5
                  and e.device_id in dev_to_serial]
    if len(car_events) >= 2:
        ref = car_events[0]
        max_d = max(
            haversine_meters(ref.latitude, ref.longitude, e.latitude, e.longitude)
            for e in car_events[1:]
        )
        lines += [
            "-" * W,
            f"  Grupo en coche: {len(car_events)} dispositivos  |  Dispersion: {max_d:.1f} m",
        ]

    lines += [
        "-" * W,
        f"  Inyecciones OK: {ok_total}   Errores: {err_total}",
        "=" * W,
    ]
    return lines


# ── CLI ───────────────────────────────────────────────────────────────────────

def cmd_detect() -> None:
    """Lista los emuladores Android conectados y sus seriales."""
    if not adb_check():
        print("ERROR: 'adb' no encontrado en PATH.")
        print("Instala Android Studio o Android SDK y añade platform-tools al PATH.")
        sys.exit(1)
    serials = adb_devices()
    if not serials:
        print("Ningún emulador detectado. ¿Están los AVD corriendo?")
    else:
        print(f"Emuladores detectados ({len(serials)}):")
        for s in serials:
            print(f"  {s}")
        print("\nUsa estos seriales en emulator_config.json → emulator_map[].serial")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Inyecta GPS del ScenarioEngine a emuladores Android via ADB"
    )
    parser.add_argument("--config", default="emulator_config.json",
                        help="Archivo de configuración (default: emulator_config.json)")
    parser.add_argument("--detect", action="store_true",
                        help="Lista emuladores conectados y termina")
    parser.add_argument("--speed", type=int, default=1,
                        help="Factor de velocidad (default: 1 = tiempo real)")
    args = parser.parse_args()

    if args.detect:
        cmd_detect()
        return

    if not adb_check():
        print("ERROR: 'adb' no encontrado. Añade Android SDK/platform-tools al PATH.")
        sys.exit(1)

    config_path = Path(args.config)
    if not config_path.exists():
        print(f"ERROR: Config no encontrada: {config_path}")
        sys.exit(1)

    with config_path.open("r", encoding="utf-8") as f:
        cfg = json.load(f)

    cfg.setdefault("speed", args.speed)
    speed = args.speed if args.speed != 1 else cfg.get("speed", 1)

    run_injection(cfg, speed)


if __name__ == "__main__":
    main()
