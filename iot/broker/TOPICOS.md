# 📡 Tópicos MQTT de EcoHuánuco AI (ECO-5 · T-104)

Este documento describe el contrato entre los sensores de los contenedores y la plataforma.
Si se cambia, el firmware (`iot/firmware`), el simulador (`iot/simulador`) y el worker
(`Backend/monitoreo/telemetria.py`) deben actualizarse juntos.

## Jerarquía

```
ecohuanuco/v1/
├── contenedores/
│   └── {device_id}/
│       ├── telemetria   ← el sensor publica sus lecturas de nivel
│       ├── estado       ← "online" / "offline" (Last Will)
│       └── config       ← la plataforma envía la configuración al sensor
└── sistema/
    └── ...              ← reservado para mensajes internos del backend
```

- **`v1`** versiona el contrato: si en el futuro cambia el payload, se publica en `v2`
  sin romper los sensores ya instalados.
- **`{device_id}`** es el identificador del equipo (por ejemplo `ESP32-0001`). En producción
  también es su **usuario MQTT**, así la ACL impide que un sensor publique por otro.

## Tabla de tópicos

| Tópico | Publica | Se suscribe | QoS | Retenido | Contenido |
|---|---|---|---|---|---|
| `ecohuanuco/v1/contenedores/{id}/telemetria` | Sensor | Worker backend, panel | 1 | No | JSON de lectura (ver abajo) |
| `ecohuanuco/v1/contenedores/{id}/estado` | Sensor / broker (LWT) | Worker backend, panel | 1 | **Sí** | `online` u `offline` |
| `ecohuanuco/v1/contenedores/{id}/config` | Backend | Sensor | 1 | **Sí** | JSON de configuración |

Comodines útiles:

- Todas las lecturas: `ecohuanuco/v1/contenedores/+/telemetria`
- Todo lo de un sensor: `ecohuanuco/v1/contenedores/ESP32-0001/#`

### ¿Por qué QoS 1?

Con QoS 1 el broker garantiza que cada lectura llega **al menos una vez**. Si se reenvía
un mensaje, el backend lo detecta como duplicado (mismo `device_id` + misma fecha) y no lo
vuelve a guardar. QoS 2 sería más pesado para el ESP32 sin aportar nada en este caso.

## Payload de telemetría

```json
{
  "device_id": "ESP32-0001",
  "ts": 1794940800,
  "distancia_cm": 42.7,
  "temp_c": 24.1,
  "bateria": 87,
  "rssi": -67,
  "fw": "1.0.0"
}
```

| Campo | Tipo | Obligatorio | Rango válido | Descripción |
|---|---|---|---|---|
| `device_id` | texto | No* | `[A-Za-z0-9_-]{3,40}` | Si se envía, debe coincidir con el del tópico |
| `ts` | número o texto | No | No más de 5 min en el futuro | Epoch en segundos (o ms) o ISO-8601. Si falta, se usa la hora de llegada |
| `distancia_cm` | número | **Sí** | 0 – 600 | Distancia del sensor a la superficie de los residuos (mediana de varias muestras) |
| `temp_c` | número | No | −40 – 85 | Temperatura usada para compensar la velocidad del sonido |
| `bateria` | entero | No | 0 – 100 | Porcentaje de batería |
| `rssi` | entero | No | −130 – 0 | Intensidad de la señal WiFi en dBm |
| `fw` | texto | No | ≤ 20 caracteres | Versión de firmware |

\* Obligatorio cuando se envía por HTTP (`POST /api/telemetria/`), porque ahí no hay tópico.

El backend calcula el nivel de llenado así:

```
distancia_corregida = factor_escala × distancia_cm + offset_cm   (coeficientes de calibración, ECO-8)
nivel_% = (altura_útil − distancia_corregida) / altura_útil × 100   (limitado a 0–100)
```

## Payload de configuración (retenido)

```json
{ "intervalo_s": 900, "muestras": 7 }
```

Como es **retenido**, el sensor lo recibe apenas se conecta, aunque se haya publicado antes.

## Last Will (detección de desconexión)

Al conectarse, el sensor registra en el broker este "testamento":

- tópico `ecohuanuco/v1/contenedores/{id}/estado`, mensaje `offline`, QoS 1, retenido.

Luego publica `online` (retenido). Si el sensor se desconecta sin avisar (batería agotada,
sin WiFi), el broker publica `offline` automáticamente cuando vence el keep-alive.

## Probar con la línea de comandos

```bash
# Ver todo lo que llega
mosquitto_sub -h localhost -t "ecohuanuco/v1/#" -v

# Publicar una lectura de prueba
mosquitto_pub -h localhost -q 1 \
  -t "ecohuanuco/v1/contenedores/ESP32-0001/telemetria" \
  -m '{"distancia_cm": 18.5, "temp_c": 23, "bateria": 90}'
```
