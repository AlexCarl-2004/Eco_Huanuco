"""
ECO-6 · T-105 — Parseo y persistencia de la telemetría IoT.

Este módulo es independiente del transporte: lo usan tanto el worker MQTT
(`python manage.py mqtt_worker`) como el endpoint HTTP `POST /api/telemetria/`.

Formato del payload (JSON, UTF-8) publicado en
    ecohuanuco/v1/contenedores/<device_id>/telemetria

    {
      "device_id": "ESP32-0001",        # opcional si viene en el tópico
      "ts": "2026-11-17T12:00:00-05:00", # ISO-8601 o epoch en segundos; opcional
      "distancia_cm": 42.7,              # obligatorio
      "temp_c": 24.1,                    # opcional
      "bateria": 87,                     # opcional, 0-100
      "rssi": -67,                       # opcional, dBm
      "fw": "1.0.0"                      # opcional
    }
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone as dt_timezone

from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .models import Dispositivo, Lectura

log = logging.getLogger("monitoreo.telemetria")

DEVICE_ID_RE = re.compile(r"^[A-Za-z0-9_\-]{3,40}$")
DISTANCIA_MAX_CM = 600.0  # alcance máximo de los sensores ultrasónicos usados
TOLERANCIA_FUTURO = timedelta(minutes=5)


class PayloadInvalido(ValueError):
    """El mensaje no cumple el formato esperado."""


class DispositivoDesconocido(LookupError):
    """El device_id no está registrado o no tiene contenedor asignado."""


@dataclass(frozen=True)
class DatoTelemetria:
    device_id: str
    distancia_cm: float
    medido_en: datetime
    temperatura_c: float | None = None
    bateria_pct: int | None = None
    rssi_dbm: int | None = None
    firmware: str | None = None
    crudo: dict | None = None


def _numero(valor, campo: str, minimo: float | None = None, maximo: float | None = None) -> float:
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        try:
            valor = float(str(valor).replace(",", "."))
        except (TypeError, ValueError):
            raise PayloadInvalido(f"'{campo}' debe ser numérico") from None
    valor = float(valor)
    if valor != valor:  # NaN
        raise PayloadInvalido(f"'{campo}' no puede ser NaN")
    if minimo is not None and valor < minimo:
        raise PayloadInvalido(f"'{campo}' fuera de rango (< {minimo})")
    if maximo is not None and valor > maximo:
        raise PayloadInvalido(f"'{campo}' fuera de rango (> {maximo})")
    return valor


def _opcional(datos: dict, claves: tuple[str, ...], campo: str, minimo=None, maximo=None) -> float | None:
    for clave in claves:
        if datos.get(clave) is not None:
            return _numero(datos[clave], campo, minimo, maximo)
    return None


def _fecha(valor) -> datetime:
    if valor is None:
        return timezone.now()
    if isinstance(valor, (int, float)) and not isinstance(valor, bool):
        segundos = valor / 1000 if valor > 1e11 else valor  # admite milisegundos
        fecha = datetime.fromtimestamp(segundos, tz=dt_timezone.utc)
    elif isinstance(valor, str):
        fecha = parse_datetime(valor.strip())
        if fecha is None:
            raise PayloadInvalido("'ts' no tiene un formato de fecha válido (ISO-8601 o epoch)")
        if timezone.is_naive(fecha):
            fecha = timezone.make_aware(fecha)
    else:
        raise PayloadInvalido("'ts' no tiene un formato de fecha válido (ISO-8601 o epoch)")

    if fecha > timezone.now() + TOLERANCIA_FUTURO:
        raise PayloadInvalido("'ts' está en el futuro; revise el reloj (NTP) del dispositivo")
    return fecha


def device_id_desde_topico(topico: str, prefijo: str) -> str | None:
    """`ecohuanuco/v1/contenedores/ESP32-0001/telemetria` -> `ESP32-0001`."""
    partes = topico.strip("/").split("/")
    base = prefijo.strip("/").split("/") + ["contenedores"]
    if len(partes) == len(base) + 2 and partes[: len(base)] == base:
        return partes[len(base)]
    return None


def parsear_payload(contenido: bytes | str | dict, device_id_topico: str | None = None) -> DatoTelemetria:
    """Convierte el mensaje recibido en un `DatoTelemetria` validado."""
    if isinstance(contenido, dict):
        datos = contenido
    else:
        try:
            texto = contenido.decode("utf-8") if isinstance(contenido, bytes) else contenido
            datos = json.loads(texto)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise PayloadInvalido(f"JSON mal formado: {exc}") from None
    if not isinstance(datos, dict):
        raise PayloadInvalido("El payload debe ser un objeto JSON")

    device_id = str(datos.get("device_id") or device_id_topico or "").strip()
    if not device_id:
        raise PayloadInvalido("Falta 'device_id'")
    if not DEVICE_ID_RE.match(device_id):
        raise PayloadInvalido("'device_id' sólo admite letras, números, '-' y '_' (3 a 40 caracteres)")
    if device_id_topico and device_id != device_id_topico:
        raise PayloadInvalido(f"El device_id del payload ({device_id}) no coincide con el del tópico ({device_id_topico})")

    if "distancia_cm" not in datos:
        raise PayloadInvalido("Falta 'distancia_cm'")
    distancia = _numero(datos["distancia_cm"], "distancia_cm", 0, DISTANCIA_MAX_CM)

    bateria = _opcional(datos, ("bateria", "bateria_pct"), "bateria", 0, 100)
    rssi = _opcional(datos, ("rssi", "rssi_dbm"), "rssi", -130, 0)

    return DatoTelemetria(
        device_id=device_id,
        distancia_cm=distancia,
        medido_en=_fecha(datos.get("ts")),
        temperatura_c=_opcional(datos, ("temp_c", "temperatura_c"), "temp_c", -40, 85),
        bateria_pct=int(round(bateria)) if bateria is not None else None,
        rssi_dbm=int(round(rssi)) if rssi is not None else None,
        firmware=str(datos["fw"])[:20] if datos.get("fw") else None,
        crudo=datos,
    )


def calcular_nivel(distancia_corregida_cm: float, altura_util_cm: float) -> float:
    """Porcentaje de llenado a partir de la distancia sensor → superficie de residuos."""
    nivel = (altura_util_cm - distancia_corregida_cm) / altura_util_cm * 100
    return round(min(100.0, max(0.0, nivel)), 1)


def registrar_lectura(dato: DatoTelemetria, origen: str = Lectura.Origen.MQTT) -> tuple[Lectura, bool]:
    """
    Persiste la lectura y actualiza el estado del contenedor y del dispositivo.

    Devuelve (lectura, creada). Si el mensaje es un duplicado (mismo dispositivo
    y misma fecha de medición), no se crea nada y `creada` es False.
    """
    with transaction.atomic():
        try:
            dispositivo = (
                Dispositivo.objects.select_for_update()
                .select_related("contenedor")
                .get(device_id=dato.device_id)
            )
        except Dispositivo.DoesNotExist:
            raise DispositivoDesconocido(f"Dispositivo '{dato.device_id}' no registrado") from None
        if not dispositivo.activo:
            raise DispositivoDesconocido(f"Dispositivo '{dato.device_id}' está desactivado")
        contenedor = dispositivo.contenedor
        if contenedor is None:
            raise DispositivoDesconocido(f"Dispositivo '{dato.device_id}' no tiene contenedor asignado")

        existente = Lectura.objects.filter(dispositivo=dispositivo, medido_en=dato.medido_en).first()
        if existente:
            return existente, False

        corregida = round(dispositivo.corregir_distancia(dato.distancia_cm), 2)
        nivel = calcular_nivel(corregida, contenedor.altura_util_cm)

        try:
            with transaction.atomic():
                lectura = Lectura.objects.create(
                    dispositivo=dispositivo,
                    contenedor=contenedor,
                    distancia_cm=dato.distancia_cm,
                    distancia_corregida_cm=corregida,
                    nivel_pct=nivel,
                    temperatura_c=dato.temperatura_c,
                    bateria_pct=dato.bateria_pct,
                    rssi_dbm=dato.rssi_dbm,
                    medido_en=dato.medido_en,
                    origen=origen,
                    payload=dato.crudo or {},
                )
        except IntegrityError:
            return Lectura.objects.get(dispositivo=dispositivo, medido_en=dato.medido_en), False

        # Sólo la lectura más reciente actualiza el estado (los mensajes pueden llegar desordenados)
        if contenedor.ultima_lectura_en is None or dato.medido_en >= contenedor.ultima_lectura_en:
            contenedor.nivel_actual_pct = nivel
            contenedor.ultima_lectura_en = dato.medido_en
            contenedor.save(update_fields=["nivel_actual_pct", "ultima_lectura_en", "actualizado_en"])

        dispositivo.ultima_conexion = timezone.now()
        campos = ["ultima_conexion", "actualizado_en"]
        if dato.bateria_pct is not None:
            dispositivo.bateria_pct = dato.bateria_pct
            campos.append("bateria_pct")
        if dato.rssi_dbm is not None:
            dispositivo.rssi_dbm = dato.rssi_dbm
            campos.append("rssi_dbm")
        if dato.firmware:
            dispositivo.firmware = dato.firmware
            campos.append("firmware")
        dispositivo.save(update_fields=campos)

    log.info("Lectura %s · %s → %.1f%%", dato.device_id, contenedor.codigo, nivel)
    return lectura, True
