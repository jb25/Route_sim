"""Consulta la API y muestra el resumen de la simulacion."""
import httpx

base = "http://localhost:8080"

devs = httpx.get(f"{base}/api/devices").json()
print("=== DISPOSITIVOS REGISTRADOS ===")
for d in devs:
    did = d["device_id"]
    cnt = d["event_count"]
    lat = d["last_latitude"]
    lon = d["last_longitude"]
    print(f"  {did:<28}  eventos={cnt:>3}  ultima_pos=({lat:.5f}, {lon:.5f})")

groups = httpx.get(f"{base}/api/groups/current").json()
print(f"\n=== GRUPOS DETECTADOS ({len(groups)}) ===")
for g in groups[:15]:
    members = g["device_ids"]
    joined = " + ".join(members)
    print(f"  Grupo {g['group_id']}: {len(members)} miembros  [{joined}]")
if len(groups) > 15:
    print(f"  ... y {len(groups)-15} grupos mas")

hist = httpx.get(f"{base}/api/devices/conductor-lemoa/locations?limit=5").json()
print("\n=== ULTIMAS 5 POSICIONES DEL CONDUCTOR ===")
for h in hist:
    print(f"  {h['timestamp_utc']}  ({h['latitude']:.5f}, {h['longitude']:.5f})  {h['speed_mps']:.1f} m/s")
