# LocationLab – PoC de simulación de usuarios GPS

**Objetivo:** laboratorio para simular N dispositivos Android viajando juntos
y verificar si una app (Tribbu u otra) es capaz de distinguir tráfico sintético
del real. Uso exclusivo en entornos de pruebas **con autorización explícita**.

---

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

### 1. Lanzar la API local (modo validación)

```bash
uvicorn locationlab.api.main:app --reload --port 8080
```

Swagger UI disponible en: http://localhost:8080/docs

### 2. Ejecutar el simulador contra la API local

```bash
python -m locationlab.simulator.main --config simulator_config.json
```

### 3. Ejecutar el simulador contra Tribbu (o cualquier app objetivo)

Edita `simulator_config.json`:

```json
{
  "api_base_url": "https://api.tribbu.com",   // ← URL real de la app
  "device_count": 50,
  "extra_headers": {
    "Authorization": "Bearer <token>",         // ← token válido
    "X-App-Version": "3.2.1"
  }
}
```

> **IMPORTANTE:** Los endpoints (`/api/locations`, `/api/locations/batch`) deben
> ajustarse a los endpoints reales de la app objetivo en `publisher.py`.

### 4. Ejecutar tests

```bash
pytest tests/ -v
```

---

## Configuración del simulador

| Parámetro | Descripción | Por defecto |
|---|---|---|
| `api_base_url` | URL base de la API objetivo | `http://localhost:8080` |
| `route_file` | Ruta al archivo GPX | `routes/sample-route.gpx` |
| `device_count` | Número de dispositivos virtuales | `20` |
| `tick_seconds` | Intervalo entre ticks (segundos) | `1.0` |
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
| App objetivo | 20–50 | Probar si Tribbu detecta tráfico sintético |

---

## Cómo adaptar los endpoints a Tribbu

1. Captura una petición real de Tribbu con un proxy (mitmproxy, Charles, Burp Suite).
2. Identifica la URL, método HTTP, cabeceras y formato JSON de la localización.
3. Modifica `locationlab/simulator/publisher.py`:
   - `_DEFAULT_HEADERS` → ajusta `User-Agent`, `X-App-Version`, etc.
   - `send()` y `send_batch()` → adapta URLs y formato del payload.
4. Añade el token de autenticación en `extra_headers` del `simulator_config.json`.

---

## Archivos GPX personalizados

Usa [gpx.studio](https://gpx.studio) para crear rutas visualmente y exportarlas
como GPX. Cópialas en `routes/` y actualiza `route_file` en la configuración.

---

## Notas de seguridad

- Este laboratorio está diseñado para **uso en entornos de pruebas autorizados**.
- No usar contra sistemas de producción sin consentimiento escrito del propietario.
- Los tokens y credenciales nunca deben commitearse al repositorio.
