"""
Crea los 4 AVDs para el carpool directamente escribiendo los archivos .ini,
sin necesidad de avdmanager. Compatible con Android SDK emulator.

Uso:
    python create_avds.py
"""
import os
import pathlib

SDK_ROOT = r"C:\Android\Sdk"
AVD_HOME = pathlib.Path.home() / ".android" / "avd"
IMG_PATH = rf"{SDK_ROOT}\system-images\android-30\google_apis_playstore\x86_64"

DEVICES = [
    ("LL_conductor",  "conductor-lemoa"),
    ("LL_pasajero1",  "pasajero-amorebieta"),
    ("LL_pasajero2",  "pasajero-durango"),
    ("LL_pasajero3",  "pasajero-eibar"),
]

AVD_HOME.mkdir(parents=True, exist_ok=True)

for avd_name, label in DEVICES:
    avd_dir = AVD_HOME / f"{avd_name}.avd"
    avd_dir.mkdir(parents=True, exist_ok=True)

    # Pointer .ini
    pointer = AVD_HOME / f"{avd_name}.ini"
    pointer.write_text(
        f"avd.ini.encoding=UTF-8\n"
        f"path={avd_dir}\n"
        f"path.rel=avd\\{avd_name}.avd\n"
        f"target=android-30\n",
        encoding="utf-8",
    )

    # Config .ini
    config = avd_dir / "config.ini"
    config.write_text(
        f"avd.ini.encoding=UTF-8\n"
        f"abi.type=x86_64\n"
        f"hw.cpu.arch=x86_64\n"
        f"hw.gpu.enabled=yes\n"
        f"hw.gpu.mode=swiftshader_indirect\n"
        f"hw.ramSize=768\n"
        f"hw.sdCard=no\n"
        f"hw.lcd.width=1080\n"
        f"hw.lcd.height=2400\n"
        f"hw.lcd.density=420\n"
        f"image.sysdir.1={IMG_PATH}\\\n"
        f"showDeviceFrame=no\n"
        f"tag.display=Google Play\n"
        f"tag.id=google_apis_playstore\n"
        f"target=android-30\n"
        f"vm.heapSize=256\n",
        encoding="utf-8",
    )

    print(f"  Creado: {avd_name}  ({label})")
    print(f"    {pointer}")
    print(f"    {config}")

print(f"\nAVDs en {AVD_HOME}:")
for f in sorted(AVD_HOME.iterdir()):
    print(f"  {f.name}")
