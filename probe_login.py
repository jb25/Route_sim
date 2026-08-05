"""
probe_login.py - Utilidad para explorar el flujo de login en un emulador Android.

Permite:
- Verificar conectividad ADB por serial
- Instalar APK (opcional)
- Abrir app por package (opcional)
- Capturar screenshot + dump UI (uiautomator)

Uso:
  python probe_login.py --serial emulator-5554
  python probe_login.py --serial emulator-5554 --apk C:\apps\tribbu.apk --package com.empresa.app
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
from datetime import datetime
from pathlib import Path


def find_adb() -> str:
    if shutil.which("adb"):
        return "adb"
    candidates = [
        r"C:\Android\platform-tools\adb.exe",
        r"C:\Android\Sdk\platform-tools\adb.exe",
        str(Path.home() / "AppData/Local/Android/Sdk/platform-tools/adb.exe"),
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return candidate
    return "adb"


def run(cmd: list[str], timeout: int = 20) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def ensure_device(adb: str, serial: str) -> bool:
    result = run([adb, "devices"])
    for line in result.stdout.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2 and parts[0] == serial and parts[1] == "device":
            return True
    return False


def install_apk(adb: str, serial: str, apk_path: Path) -> None:
    print(f"[INFO] Instalando APK: {apk_path}")
    result = run([adb, "-s", serial, "install", "-r", str(apk_path)], timeout=120)
    if result.returncode != 0:
        raise RuntimeError(f"Fallo instalacion APK:\n{result.stderr.strip()}")
    print("[OK] APK instalada")


def launch_package(adb: str, serial: str, package_name: str) -> None:
    print(f"[INFO] Abriendo package: {package_name}")
    result = run([adb, "-s", serial, "shell", "monkey", "-p", package_name, "-c", "android.intent.category.LAUNCHER", "1"])
    if result.returncode != 0:
        raise RuntimeError(f"No se pudo abrir la app:\n{result.stderr.strip()}")
    print("[OK] App abierta")


def current_focus(adb: str, serial: str) -> str:
    result = run([adb, "-s", serial, "shell", "dumpsys", "window", "windows"])
    for line in result.stdout.splitlines():
        text = line.strip()
        if "mCurrentFocus=" in text or "mFocusedApp=" in text:
            return text
    return "(sin foco detectado)"


def capture_probe(adb: str, serial: str, out_dir: Path) -> tuple[Path, Path, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    png_remote = "/sdcard/probe_screen.png"
    xml_remote = "/sdcard/probe_ui.xml"

    png_local = out_dir / f"{stamp}_{serial}_screen.png"
    xml_local = out_dir / f"{stamp}_{serial}_ui.xml"

    run([adb, "-s", serial, "shell", "screencap", "-p", png_remote], timeout=30)
    run([adb, "-s", serial, "pull", png_remote, str(png_local)], timeout=30)

    run([adb, "-s", serial, "shell", "uiautomator", "dump", xml_remote], timeout=30)
    run([adb, "-s", serial, "pull", xml_remote, str(xml_local)], timeout=30)

    focus = current_focus(adb, serial)
    return png_local, xml_local, focus


def main() -> None:
    parser = argparse.ArgumentParser(description="Explora pantallas de login en emulador Android")
    parser.add_argument("--serial", default="emulator-5554", help="Serial ADB del emulador")
    parser.add_argument("--apk", default=None, help="Ruta al APK para instalar")
    parser.add_argument("--package", default=None, help="Nombre del package para abrir")
    parser.add_argument("--out", default="artifacts/login_probe", help="Directorio de salida")
    args = parser.parse_args()

    adb = find_adb()
    print(f"[INFO] adb: {adb}")

    if not ensure_device(adb, args.serial):
        raise SystemExit(f"[ERROR] Emulador no disponible: {args.serial}")

    if args.apk:
        apk_path = Path(args.apk)
        if not apk_path.exists():
            raise SystemExit(f"[ERROR] APK no encontrado: {apk_path}")
        install_apk(adb, args.serial, apk_path)

    if args.package:
        launch_package(adb, args.serial, args.package)

    png_local, xml_local, focus = capture_probe(adb, args.serial, Path(args.out))
    print("[OK] Captura completada")
    print(f"[INFO] Focus: {focus}")
    print(f"[INFO] Screenshot: {png_local}")
    print(f"[INFO] UI XML: {xml_local}")
    print("[TIP] Siguiente accion: abre la pantalla de login y vuelve a ejecutar este script para comparar estados.")


if __name__ == "__main__":
    main()
