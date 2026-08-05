# LocationLab - PoC de simulacion de usuarios GPS

**Objetivo:** laboratorio para simular N dispositivos Android viajando juntos
y verificar si una app (Tribbu u otra) es capaz de distinguir tráfico sintético
del real. Uso exclusivo en entornos de pruebas **con autorización explícita**.

---

## Estado y alcance

La PoC implementa un pipeline local completo: escenarios GPX multi-ruta,
simulacion de dispositivos logicos, publicacion HTTP, API FastAPI, SQLite y
deteccion de grupos. La suite actual tiene 41 tests pasando.

La ruta recomendada no necesita emuladores Android. Los AVDs son opcionales y
solo sirven para validar visualmente una aplicacion propia o de staging
autorizado.

## Estructura del proyecto

```
Route_sim_2026/
├── locationlab/
│   ├── core/
│   │   ├── models.py          # Modelos Pydantic compartidos
│   │   ├── geo.py             # Haversine, bearing, ruido gaussiano
│   │   └── group_detector.py  # Detector de grupos con persistencia
│   ├── api/
│   │   ├── main.py            # FastAPI – endpoints REST
│   │   └── database.py        # SQLite (sin dependencias externas)
│   └── simulator/
│       ├── gpx_reader.py      # Lector GPX (gpxpy)
│       ├── interpolator.py    # Interpolación lineal de ruta
│       ├── engine.py          # Motor N-dispositivos con ruido y offsets
│       ├── publisher.py       # Cliente HTTP (httpx) con cabeceras Android
│       └── main.py            # CLI del simulador
├── tests/
│   ├── test_geo.py            # Tests Haversine, bearing, ruido
│   ├── test_group_detector.py # Tests detector de grupos
│   └── test_interpolator.py   # Tests interpolación GPX
├── routes/
│   └── sample-route.gpx       # Ruta de ejemplo (Bilbao, 4 min)
├── simulator_config.json      # Configuración del simulador
├── requirements.txt
└── README.md
```

---

## Instalación

```bash
# Dentro del virtualenv del proyecto
pip install -r requirements.txt
```

---

## Ejecución

### 1. Lanzar la API local (modo validacion)

```bash
uvicorn locationlab.api.main:app --reload --port 8080
```

Para una prueba aislada, usa una base SQLite temporal mediante
`LOCATIONLAB_DB_PATH`; el valor por defecto sigue siendo `locationlab.db`.

```powershell
$env:LOCATIONLAB_DB_PATH = "$PWD\artifacts\smoke\locationlab.db"
python -m uvicorn locationlab.api.main:app --port 8080
```

Swagger UI disponible en: http://localhost:8080/docs

### 2. Validar el escenario de carpooling

```bash
python validate_scenario.py
```

### 3. Ejecutar el escenario multi-ruta contra la API local

```bash
python -m locationlab.simulator.scenario_main \
  --scenario scenarios/commute_bilbao.json
```

Para recorrer la misma ventana de 57 minutos en pocos segundos, usa el
escenario smoke acelerado:

```bash
python -m locationlab.simulator.scenario_main \
  --scenario scenarios/commute_bilbao_smoke.json
```

### 4. Ejecutar el simulador generico contra la API local

```bash
python -m locationlab.simulator.main --config simulator_config.json
```

### 5. Integrar con otra API autorizada

Edita `simulator_config.json`:

```json
{
  "api_base_url": "https://staging.example.test",   // ← API propia autorizada
  "device_count": 50,
  "extra_headers": {
    "X-App-Version": "3.2.1",
    "Authorization": "Bearer ${LOCATIONLAB_TEST_TOKEN}"
  }
}
```

> **IMPORTANTE:** Los endpoints (`/api/locations`, `/api/locations/batch`) deben
> ajustarse al contrato de la API propia de staging en `publisher.py`. No
> guardes tokens reales en archivos JSON ni los publiques en Git.

### 6. Ejecutar tests

```bash
pytest tests/ -v
```

### 7. Limpiar datos SQLite antiguos

La limpieza conserva por defecto los ultimos 7 dias. Primero inspecciona el
resultado con `--dry-run`:

```powershell
python cleanup_database.py --dry-run --retention-days 7
python cleanup_database.py --retention-days 7
```

La limpieza elimina en una transaccion eventos y grupos cuya ultima actividad
sea anterior al corte. Para usar otra base, define `LOCATIONLAB_DB_PATH` antes
de ejecutar el comando.

---

## Configuracion del simulador

| Parámetro | Descripción | Por defecto |
|---|---|---|
| `api_base_url` | URL base de la API objetivo | `http://localhost:8080` |
| `route_file` | Ruta al archivo GPX | `routes/sample-route.gpx` |
| `device_count` | Número de dispositivos virtuales | `20` |
| `tick_seconds` | Intervalo entre ticks (segundos) | `1.0` |
| `wall_tick_seconds` | Espera real entre ticks; permite acelerar la simulacion | igual a `tick_seconds` |
| `batch_size` | Eventos por petición HTTP | `20` |
| `start_delay_jitter_ms` | Jitter de inicio por dispositivo (ms) | `1500` |
| `position_noise_meters` | Radio de ruido gaussiano en posición | `4.0` |
| `speed_variation_pct` | Variación de velocidad por dispositivo (%) | `2.0` |
| `use_batch_endpoint` | Usar endpoint batch en vez de uno a uno | `true` |
| `max_duration_seconds` | Duración máxima (0 = hasta fin de ruta) | `0` |
| `extra_headers` | Cabeceras HTTP adicionales (auth, cookies…) | `{}` |

---

## Escenarios de prueba recomendados

| Escenarios | Dispositivos | Objetivo |
|---|---:|---|
| Smoke test local | 20 | Validar pipeline completo |
| Carga media | 50 | Ajustar batch y latencia |
| Límite práctico | 100 | Probar saturación y detección |
| App propia de staging | 20-50 | Validar contrato HTTP autorizado |

---

## Como adaptar una API propia de staging

1. Documenta el contrato HTTP de tu API propia con Swagger/OpenAPI.
2. Identifica la URL, metodo HTTP, cabeceras y formato JSON de la localizacion.
3. Modifica `locationlab/simulator/publisher.py`:
   - `_DEFAULT_HEADERS` → ajusta `User-Agent`, `X-App-Version`, etc.
   - `send()` y `send_batch()` → adapta URLs y formato del payload.
4. Añade credenciales de prueba mediante variables de entorno; no las guardes
  en JSON ni las publiques en Git.

---

## Archivos GPX personalizados

Usa [gpx.studio](https://gpx.studio) para crear rutas visualmente y exportarlas
como GPX. Cópialas en `routes/` y actualiza `route_file` en la configuración.

---

## Integracion continua

El workflow [.github/workflows/ci.yml](.github/workflows/ci.yml) ejecuta en
GitHub Actions sobre Windows:

- instalacion de dependencias;
- `pytest`;
- compilacion de `locationlab`;
- `git diff --check`.

Se ejecuta en pushes a `main` y en pull requests.

## Notas de seguridad

- Este laboratorio está diseñado para **uso en entornos de pruebas autorizados**.
- No usar contra sistemas de producción sin consentimiento escrito del propietario.
- Los tokens y credenciales nunca deben commitearse al repositorio.
