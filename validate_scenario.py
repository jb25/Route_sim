"""Script de validacion rapida del escenario de carpool."""
from locationlab.simulator.scenario import ScenarioEngine, DeviceScenarioConfig
from locationlab.simulator.scenario_main import load_scenario
from locationlab.core.geo import haversine_meters
from datetime import datetime, timezone

cfg = load_scenario("scenarios/commute_bilbao.json")
devices = [
    DeviceScenarioConfig(
        device_id=d["device_id"],
        route_file=d["route_file"],
        noise_meters=d.get("noise_meters", 3.5),
        speed_variation_pct=d.get("speed_variation_pct", 1.5),
        label=d.get("label", ""),
    )
    for d in cfg["devices"]
]
engine = ScenarioEngine(devices)
engine.initialize()

print("Dispositivos cargados:")
for dev_id, label in engine.device_labels:
    print(f"  {dev_id}: {label}")

start = engine.route_start.strftime("%H:%M")
end = engine.route_end.strftime("%H:%M")
print(f"\nVentana: {start} -> {end} UTC")

instants = [
    ("07:05 solo conductor en marcha",      datetime(2026, 7, 14, 7,  5, 0, tzinfo=timezone.utc)),
    ("07:15 conductor+P1 en A-8",           datetime(2026, 7, 14, 7, 15, 0, tzinfo=timezone.utc)),
    ("07:28 conductor+P1+P2 en AP-8",       datetime(2026, 7, 14, 7, 28, 0, tzinfo=timezone.utc)),
    ("07:50 los 4 juntos hacia Mondragon",  datetime(2026, 7, 14, 7, 50, 0, tzinfo=timezone.utc)),
]

for label, t in instants:
    events = engine.get_events(t)
    print(f"\n-- {label} | {len(events)} activos --")
    for e in events:
        print(f"   {e.device_id}: ({e.latitude:.5f}, {e.longitude:.5f}) {e.speed_meters_per_second:.1f} m/s")
    if len(events) > 1:
        ref = events[0]
        max_d = max(
            haversine_meters(ref.latitude, ref.longitude, e.latitude, e.longitude)
            for e in events[1:]
        )
        print(f"   Dispersion maxima entre activos: {max_d:.1f} m")
