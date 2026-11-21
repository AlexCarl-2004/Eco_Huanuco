# 🔌 Firmware del sensor de llenado

Firmware para **ESP32 + sensor ultrasónico impermeable JSN-SR04T** instalado en la tapa del contenedor.

## Conexiones

| JSN-SR04T | ESP32 | Nota |
|---|---|---|
| 5V | VIN (5 V) | |
| GND | GND | |
| Trig | GPIO 5 | |
| Echo | GPIO 18 | Usar divisor resistivo (1 kΩ / 2 kΩ) para bajar de 5 V a 3,3 V |

Batería Li-ion 18650 → divisor 100 kΩ / 100 kΩ → GPIO 34 (lectura del nivel de batería).

## Instalación

1. Instale el **Arduino IDE 2** y el paquete de placas **esp32** de Espressif.
2. Desde el gestor de librerías instale **PubSubClient** y **ArduinoJson** (v7).
3. Copie `sensor_contenedor/config.example.h` como `sensor_contenedor/config.h` y complete el
   WiFi, la IP del broker y el `DEVICE_ID` (debe estar registrado en la plataforma).
4. Abra `sensor_contenedor/sensor_contenedor.ino`, elija la placa **ESP32 Dev Module** y súbalo.
5. En el Monitor Serie (115200 baudios) verá cada medición y la publicación MQTT.

## Comportamiento

- Toma 7 mediciones, descarta las inválidas y usa la **mediana**. Así ignora los ecos falsos
  de las paredes y la tapa.
- Compensa la velocidad del sonido con la temperatura (por defecto 22 °C).
- Mide **antes** de encender el WiFi, porque la radio genera ruido eléctrico.
- Publica con QoS 1 y registra un **Last Will** (`offline`) para que la plataforma sepa si se cayó.
- Duerme en **deep sleep** entre lecturas (15 min por defecto). El intervalo se puede cambiar
  desde la plataforma publicando en el tópico `config` (ver `iot/broker/TOPICOS.md`).

La corrección fina de cada sensor (factor y offset) **no** se programa en el firmware. Se calcula
con el procedimiento de calibración (`iot/calibracion`) y la aplica el backend.
