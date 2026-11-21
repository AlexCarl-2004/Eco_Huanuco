"""
Simulador de sensores IoT de EcoHuánuco AI.

Publica lecturas realistas de nivel de llenado por MQTT (o por HTTP) como si fueran
los ESP32 instalados en los contenedores. Sirve para probar el broker (ECO-5) y el
worker de telemetría (ECO-6) sin tener el hardware.

Uso:
    python simulador.py                              # 20 sensores, cada 5 s, broker en localhost
    python simulador.py --dispositivos 5 --intervalo 2
    python simulador.py --broker 192.168.1.50 --usuario ESP32-0001 --clave ****
    python simulador.py --http http://localhost:8000  # sin broker, directo a la API
    python simulador.py --errores 0.1                # 10 % de mensajes inválidos (para probar validación)

Requiere: pip install paho-mqtt
"""

from __future__ import annotations

import argparse
import json
import random
import signal
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

PREFIJO = "ecohuanuco/v1"

# Altura útil (cm) de los contenedores creados por `manage.py cargar_datos_demo`,
# para que el nivel que muestra el simulador coincida con el que calcula el backend.
ALTURAS_DEMO = [120, 120, 100, 100, 120, 80, 120, 120, 100, 120, 100, 120, 120, 120, 120, 80, 100, 100, 80, 100]


@dataclass
class SensorVirtual:
    device_id: str
    altura_cm: float
    nivel: float          # % de llenado actual
    velocidad: float      # % que sube por cada lectura
    bateria: float

    def leer(self, rng: random.Random) -> dict:
        # El contenedor se llena; al pasar el 98 % lo "vacía" el camión
        self.nivel += self.velocidad * rng.uniform(0.4, 1.6)
        if self.nivel >= 98:
            self.nivel = rng.uniform(2, 8)
        self.bateria = max(5.0, self.bateria - rng.uniform(0, 0.05))

        distancia = self.altura_cm * (1 - self.nivel / 100)
        distancia += rng.gauss(0, 0.6)  # ruido típico del sensor ultrasónico
        return {
            "device_id": self.device_id,
            "ts": round(time.time(), 3),
            "distancia_cm": round(max(0.0, distancia), 1),
            "temp_c": round(rng.uniform(17, 30), 1),
            "bateria": round(self.bateria),
            "rssi": rng.randint(-88, -52),
            "fw": "1.0.0-sim",
        }


def payload_invalido(rng: random.Random, device_id: str) -> str:
    opciones = [
        "esto no es json",
        json.dumps({"device_id": device_id}),                      # falta distancia
        json.dumps({"device_id": device_id, "distancia_cm": -5}),  # fuera de rango
        json.dumps({"device_id": device_id, "distancia_cm": "abc"}),
    ]
    return rng.choice(opciones)


def crear_sensores(cantidad: int, rng: random.Random) -> list[SensorVirtual]:
    return [
        SensorVirtual(
            device_id=f"ESP32-{i:04d}",
            altura_cm=ALTURAS_DEMO[i - 1] if i <= len(ALTURAS_DEMO) else 120,
            nivel=rng.uniform(5, 70),
            velocidad=rng.uniform(0.3, 2.5),
            bateria=rng.uniform(60, 100),
        )
        for i in range(1, cantidad + 1)
    ]


# ------------------------------------------------------------------ MQTT
def ejecutar_mqtt(args, sensores, rng):
    try:
        import paho.mqtt.client as mqtt
    except ImportError:
        sys.exit("Falta paho-mqtt. Instálelo con:  pip install paho-mqtt")

    cliente = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"simulador-{rng.randint(1000, 9999)}",
    )
    if args.usuario:
        cliente.username_pw_set(args.usuario, args.clave)
    # Un único cliente simula a todos; el Last Will se registra para el simulador completo
    cliente.will_set(f"{PREFIJO}/sistema/simulador", "offline", qos=1, retain=True)
    try:
        cliente.connect(args.broker, args.puerto, keepalive=30)
    except OSError as exc:
        sys.exit(f"No se pudo conectar al broker {args.broker}:{args.puerto} → {exc}\n"
                 "¿Está corriendo Mosquitto? (docker compose up -d mosquitto)")
    cliente.loop_start()
    for s in sensores:
        cliente.publish(f"{PREFIJO}/contenedores/{s.device_id}/estado", "online", qos=1, retain=True)

    def publicar(sensor: SensorVirtual, invalido: bool):
        topico = f"{PREFIJO}/contenedores/{sensor.device_id}/telemetria"
        cuerpo = payload_invalido(rng, sensor.device_id) if invalido else json.dumps(sensor.leer(rng))
        cliente.publish(topico, cuerpo, qos=1).wait_for_publish(timeout=5)
        return topico, cuerpo

    try:
        bucle(args, sensores, rng, publicar)
    finally:
        for s in sensores:
            cliente.publish(f"{PREFIJO}/contenedores/{s.device_id}/estado", "offline", qos=1, retain=True)
        cliente.loop_stop()
        cliente.disconnect()


# ------------------------------------------------------------------ HTTP
def ejecutar_http(args, sensores, rng):
    url = args.http.rstrip("/") + "/api/telemetria/"

    def publicar(sensor: SensorVirtual, invalido: bool):
        cuerpo = payload_invalido(rng, sensor.device_id) if invalido else json.dumps(sensor.leer(rng))
        peticion = urllib.request.Request(url, data=cuerpo.encode(), headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(peticion, timeout=5) as r:
                estado = r.status
        except urllib.error.HTTPError as exc:
            estado = exc.code
        except urllib.error.URLError as exc:
            sys.exit(f"No se pudo conectar a {url} → {exc.reason}. ¿Está corriendo el backend?")
        return f"HTTP {estado}", cuerpo

    bucle(args, sensores, rng, publicar)


# ------------------------------------------------------------------ bucle
def bucle(args, sensores, rng, publicar):
    detener = {"si": False}
    signal.signal(signal.SIGINT, lambda *_: detener.update(si=True))
    enviados = 0
    ciclos = 0
    print(f"♻  Simulando {len(sensores)} sensores · cada {args.intervalo} s · Ctrl+C para detener\n")
    while not detener["si"]:
        for sensor in sensores:
            invalido = rng.random() < args.errores
            destino, cuerpo = publicar(sensor, invalido)
            enviados += 1
            marca = "✗" if invalido else "→"
            if args.verbose or invalido:
                print(f"  {marca} {destino}  {cuerpo}")
        ciclos += 1
        niveles = "  ".join(f"{s.device_id[-4:]}:{s.nivel:4.0f}%" for s in sensores[:8])
        print(f"[{time.strftime('%H:%M:%S')}] ciclo {ciclos} · {enviados} mensajes · {niveles}{' …' if len(sensores) > 8 else ''}")
        if args.ciclos and ciclos >= args.ciclos:
            break
        for _ in range(int(args.intervalo * 10)):
            if detener["si"]:
                break
            time.sleep(0.1)
    print(f"\nSimulación terminada: {enviados} mensajes enviados.")


def main():
    p = argparse.ArgumentParser(description="Simulador de sensores de llenado de EcoHuánuco AI")
    p.add_argument("--broker", default="localhost")
    p.add_argument("--puerto", type=int, default=1883)
    p.add_argument("--usuario")
    p.add_argument("--clave")
    p.add_argument("--http", help="URL del backend para enviar por HTTP en lugar de MQTT")
    p.add_argument("--dispositivos", type=int, default=20)
    p.add_argument("--intervalo", type=float, default=5, help="Segundos entre ciclos")
    p.add_argument("--ciclos", type=int, default=0, help="Número de ciclos (0 = infinito)")
    p.add_argument("--errores", type=float, default=0.0, help="Proporción de mensajes inválidos (0-1)")
    p.add_argument("--semilla", type=int)
    p.add_argument("-v", "--verbose", action="store_true", help="Mostrar cada mensaje")
    args = p.parse_args()

    rng = random.Random(args.semilla)
    sensores = crear_sensores(args.dispositivos, rng)
    if args.http:
        ejecutar_http(args, sensores, rng)
    else:
        ejecutar_mqtt(args, sensores, rng)


if __name__ == "__main__":
    main()
