"""
ECO-6 · T-105 — Worker en segundo plano que escucha el broker MQTT,
parsea los payloads JSON de telemetría y persiste las lecturas.

Uso:
    python manage.py mqtt_worker
    python manage.py mqtt_worker --host 192.168.1.50 --hilos 4

Arquitectura:
    Broker Mosquitto ──► hilo de red de paho-mqtt ──► cola en memoria ──► N hilos que
    validan y guardan en la base de datos

La cola desacopla la recepción de la escritura: si la base de datos se demora,
los mensajes no se pierden ni bloquean la conexión MQTT.
"""

import logging
import queue
import signal
import threading
import time
from dataclasses import dataclass, field

import paho.mqtt.client as mqtt
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import OperationalError, close_old_connections, connection
from django.utils import timezone

from monitoreo.models import Dispositivo, Lectura
from monitoreo.telemetria import (
    DispositivoDesconocido,
    PayloadInvalido,
    device_id_desde_topico,
    parsear_payload,
    registrar_lectura,
)

log = logging.getLogger("monitoreo.worker")


@dataclass
class Estadisticas:
    recibidos: int = 0
    guardados: int = 0
    duplicados: int = 0
    invalidos: int = 0
    desconocidos: int = 0
    errores: int = 0
    inicio: float = field(default_factory=time.monotonic)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def sumar(self, campo: str) -> None:
        with self._lock:
            setattr(self, campo, getattr(self, campo) + 1)

    def resumen(self) -> str:
        minutos = (time.monotonic() - self.inicio) / 60
        return (
            f"recibidos={self.recibidos} guardados={self.guardados} duplicados={self.duplicados} "
            f"inválidos={self.invalidos} desconocidos={self.desconocidos} errores={self.errores} "
            f"({minutos:.1f} min)"
        )


class Command(BaseCommand):
    help = "Escucha la telemetría MQTT de los contenedores y guarda las lecturas en la base de datos."

    def add_arguments(self, parser):
        cfg = settings.MQTT
        parser.add_argument("--host", default=cfg["HOST"])
        parser.add_argument("--port", type=int, default=cfg["PORT"])
        parser.add_argument("--usuario", default=cfg["USER"])
        parser.add_argument("--clave", default=cfg["PASSWORD"])
        parser.add_argument("--prefijo", default=cfg["TOPIC_PREFIX"])
        parser.add_argument("--qos", type=int, default=cfg["QOS"], choices=[0, 1, 2])
        parser.add_argument(
            "--hilos", type=int, default=None,
            help="Hilos que escriben en la base de datos (por defecto 1 con SQLite y 4 con MySQL)",
        )
        parser.add_argument("--max-cola", type=int, default=10_000)
        parser.add_argument("--duracion", type=float, default=0, help="Segundos de ejecución (0 = indefinido)")

    def handle(self, *args, **opts):
        self.prefijo = opts["prefijo"].strip("/")
        self.qos = opts["qos"]
        self.cola: queue.Queue = queue.Queue(maxsize=opts["max_cola"])
        self.stats = Estadisticas()
        self.detener = threading.Event()

        topico_telemetria = f"{self.prefijo}/contenedores/+/telemetria"
        topico_estado = f"{self.prefijo}/contenedores/+/estado"
        self.suscripciones = [(topico_telemetria, self.qos), (topico_estado, self.qos)]

        cliente = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=settings.MQTT["CLIENT_ID"],
            clean_session=False,  # el broker guarda los mensajes QoS 1 si el worker se reinicia
        )
        if opts["usuario"]:
            cliente.username_pw_set(opts["usuario"], opts["clave"] or None)
        cliente.on_connect = self._on_connect
        cliente.on_disconnect = self._on_disconnect
        cliente.on_message = self._on_message
        cliente.reconnect_delay_set(min_delay=1, max_delay=60)

        # SQLite admite un solo escritor a la vez: más hilos sólo generarían esperas
        num_hilos = opts["hilos"] or (1 if connection.vendor == "sqlite" else 4)
        hilos = [
            threading.Thread(target=self._procesar_cola, name=f"db-{i}", daemon=True)
            for i in range(max(1, num_hilos))
        ]
        for hilo in hilos:
            hilo.start()

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(sig, lambda *_: self.detener.set())
            except ValueError:  # no estamos en el hilo principal (p. ej. en tests)
                pass

        self.stdout.write(self.style.SUCCESS("♻  EcoHuánuco · worker MQTT"))
        self.stdout.write(f"   Broker:   {opts['host']}:{opts['port']}")
        self.stdout.write(f"   Tópicos:  {topico_telemetria}")
        self.stdout.write(f"             {topico_estado}")
        self.stdout.write(f"   Hilos BD: {len(hilos)}   (Ctrl+C para detener)\n")

        conectado = False
        while not conectado and not self.detener.is_set():
            try:
                cliente.connect(opts["host"], opts["port"], keepalive=60)
                conectado = True
            except OSError as exc:
                log.warning("No se pudo conectar al broker (%s). Reintentando en 5 s…", exc)
                self.detener.wait(5)

        cliente.loop_start()
        fin = time.monotonic() + opts["duracion"] if opts["duracion"] else None
        ultimo_resumen = time.monotonic()
        try:
            while not self.detener.is_set():
                self.detener.wait(1)
                if fin and time.monotonic() >= fin:
                    break
                if time.monotonic() - ultimo_resumen >= 60:
                    log.info("Resumen: %s", self.stats.resumen())
                    ultimo_resumen = time.monotonic()
        finally:
            self.stdout.write("\nDeteniendo worker… procesando mensajes pendientes")
            cliente.loop_stop()
            cliente.disconnect()
            self.cola.join()
            self.detener.set()
            self.stdout.write(self.style.SUCCESS(f"Listo. {self.stats.resumen()}"))

    # ------------------------------------------------------------------ MQTT
    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            log.error("El broker rechazó la conexión: %s", reason_code)
            return
        client.subscribe(self.suscripciones)
        log.info("Conectado al broker y suscrito a %d tópicos", len(self.suscripciones))

    def _on_disconnect(self, client, userdata, flags, reason_code, properties):
        if not self.detener.is_set():
            log.warning("Desconectado del broker (%s). paho-mqtt reintentará automáticamente.", reason_code)

    def _on_message(self, client, userdata, msg):
        self.stats.sumar("recibidos")
        try:
            self.cola.put_nowait((msg.topic, msg.payload))
        except queue.Full:
            self.stats.sumar("errores")
            log.error("Cola llena: se descartó un mensaje de %s", msg.topic)

    # --------------------------------------------------------- procesamiento
    def _procesar_cola(self):
        while True:
            try:
                topico, payload = self.cola.get(timeout=0.5)
            except queue.Empty:
                if self.detener.is_set():
                    return
                continue
            try:
                for intento in range(1, 4):
                    try:
                        close_old_connections()
                        self.procesar_mensaje(topico, payload)
                        break
                    except OperationalError as exc:  # base de datos ocupada o reconectando
                        if intento == 3:
                            raise
                        log.warning("Base de datos ocupada (%s). Reintento %d/3…", exc, intento)
                        time.sleep(0.5 * intento)
            except Exception:  # noqa: BLE001 - el worker nunca debe caerse por un mensaje
                self.stats.sumar("errores")
                log.exception("Error inesperado procesando %s", topico)
            finally:
                self.cola.task_done()

    def procesar_mensaje(self, topico: str, payload: bytes) -> None:
        device_id = device_id_desde_topico(topico, self.prefijo)
        if topico.endswith("/estado"):
            self._procesar_estado(device_id, payload)
            return
        try:
            dato = parsear_payload(payload, device_id)
            _, creada = registrar_lectura(dato, Lectura.Origen.MQTT)
            self.stats.sumar("guardados" if creada else "duplicados")
        except PayloadInvalido as exc:
            self.stats.sumar("invalidos")
            log.warning("Payload inválido en %s: %s", topico, exc)
        except DispositivoDesconocido as exc:
            self.stats.sumar("desconocidos")
            log.warning("%s (regístrelo en /admin o vía API)", exc)

    def _procesar_estado(self, device_id: str | None, payload: bytes) -> None:
        """Mensajes 'online'/'offline' (este último lo publica el broker como Last Will)."""
        estado = payload.decode("utf-8", "ignore").strip().lower()
        if device_id and estado == "online":
            Dispositivo.objects.filter(device_id=device_id).update(ultima_conexion=timezone.now())
        log.info("Dispositivo %s → %s", device_id, estado or "?")
