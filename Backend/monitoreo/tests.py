"""Pruebas de ECO-2, ECO-3 y ECO-6. Ejecutar con:  python manage.py test"""

import json
from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APITestCase

from .management.commands.mqtt_worker import Command as WorkerCommand
from .management.commands.mqtt_worker import Estadisticas
from .models import Contenedor, Dispositivo, Lectura, Semaforo, calcular_semaforo
from .telemetria import (
    DispositivoDesconocido,
    PayloadInvalido,
    calcular_nivel,
    device_id_desde_topico,
    parsear_payload,
    registrar_lectura,
)


def crear_contenedor(codigo="CNT-001", nivel=None, **extra):
    datos = dict(codigo=codigo, nombre=f"Contenedor {codigo}", latitud=-9.93, longitud=-76.24,
                 capacidad_litros=1100, altura_util_cm=120, nivel_actual_pct=nivel)
    datos.update(extra)
    return Contenedor.objects.create(**datos)


class ParserTelemetriaTests(TestCase):
    def test_payload_valido_completo(self):
        dato = parsear_payload(b'{"device_id":"ESP32-0001","distancia_cm":42.5,"temp_c":23,"bateria":88,"rssi":-60,"fw":"1.0"}')
        self.assertEqual(dato.device_id, "ESP32-0001")
        self.assertEqual(dato.distancia_cm, 42.5)
        self.assertEqual(dato.bateria_pct, 88)
        self.assertEqual(dato.rssi_dbm, -60)

    def test_device_id_desde_topico(self):
        self.assertEqual(device_id_desde_topico("ecohuanuco/v1/contenedores/ESP32-0007/telemetria", "ecohuanuco/v1"), "ESP32-0007")
        self.assertIsNone(device_id_desde_topico("otro/topico/x", "ecohuanuco/v1"))
        dato = parsear_payload('{"distancia_cm": 10}', device_id_topico="ESP32-0007")
        self.assertEqual(dato.device_id, "ESP32-0007")

    def test_fecha_epoch_segundos_milisegundos_e_iso(self):
        ahora = timezone.now().replace(microsecond=0)
        for ts in (ahora.timestamp(), ahora.timestamp() * 1000, ahora.isoformat()):
            dato = parsear_payload({"device_id": "ESP32-0001", "distancia_cm": 10, "ts": ts})
            self.assertEqual(dato.medido_en, ahora)

    def test_payloads_invalidos(self):
        casos = [
            b"no es json",
            b"[1, 2, 3]",
            b'{"device_id": "ESP32-0001"}',                                 # falta distancia
            b'{"device_id": "ESP32-0001", "distancia_cm": -1}',             # negativa
            b'{"device_id": "ESP32-0001", "distancia_cm": 9999}',           # fuera de alcance
            b'{"device_id": "ESP32-0001", "distancia_cm": "abc"}',
            b'{"device_id": "ESP 32", "distancia_cm": 10}',                 # caracteres no permitidos
            b'{"device_id": "ESP32-0001", "distancia_cm": 10, "bateria": 150}',
            b'{"device_id": "ESP32-0001", "distancia_cm": 10, "ts": "ayer"}',
        ]
        for caso in casos:
            with self.subTest(caso=caso), self.assertRaises(PayloadInvalido):
                parsear_payload(caso)

    def test_rechaza_fecha_futura(self):
        futuro = (timezone.now() + timedelta(hours=1)).isoformat()
        with self.assertRaises(PayloadInvalido):
            parsear_payload({"device_id": "ESP32-0001", "distancia_cm": 10, "ts": futuro})

    def test_rechaza_device_id_distinto_al_topico(self):
        with self.assertRaises(PayloadInvalido):
            parsear_payload('{"device_id":"ESP32-0002","distancia_cm":10}', device_id_topico="ESP32-0001")

    def test_calculo_de_nivel(self):
        self.assertEqual(calcular_nivel(120, 120), 0)
        self.assertEqual(calcular_nivel(30, 120), 75)
        self.assertEqual(calcular_nivel(0, 120), 100)
        self.assertEqual(calcular_nivel(-5, 120), 100)   # limitado a 100
        self.assertEqual(calcular_nivel(150, 120), 0)    # limitado a 0

    def test_semaforo(self):
        self.assertEqual(calcular_semaforo(None), Semaforo.SIN_DATOS)
        self.assertEqual(calcular_semaforo(10), Semaforo.VERDE)
        self.assertEqual(calcular_semaforo(60), Semaforo.AMBAR)
        self.assertEqual(calcular_semaforo(75), Semaforo.ROJO)


class RegistroLecturaTests(TestCase):
    def setUp(self):
        self.contenedor = crear_contenedor()
        self.dispositivo = Dispositivo.objects.create(device_id="ESP32-0001", contenedor=self.contenedor)

    def test_guarda_lectura_y_actualiza_contenedor(self):
        lectura, creada = registrar_lectura(parsear_payload({"device_id": "ESP32-0001", "distancia_cm": 30, "bateria": 77}))
        self.assertTrue(creada)
        self.assertEqual(lectura.nivel_pct, 75)
        self.contenedor.refresh_from_db()
        self.dispositivo.refresh_from_db()
        self.assertEqual(self.contenedor.nivel_actual_pct, 75)
        self.assertEqual(self.dispositivo.bateria_pct, 77)
        self.assertTrue(self.dispositivo.en_linea)

    def test_aplica_calibracion(self):
        self.dispositivo.factor_escala = 1.1
        self.dispositivo.offset_cm = -3
        self.dispositivo.save()
        lectura, _ = registrar_lectura(parsear_payload({"device_id": "ESP32-0001", "distancia_cm": 50}))
        self.assertAlmostEqual(lectura.distancia_corregida_cm, 52.0)
        self.assertEqual(lectura.distancia_cm, 50)

    def test_ignora_duplicados(self):
        ts = timezone.now().isoformat()
        registrar_lectura(parsear_payload({"device_id": "ESP32-0001", "distancia_cm": 30, "ts": ts}))
        _, creada = registrar_lectura(parsear_payload({"device_id": "ESP32-0001", "distancia_cm": 30, "ts": ts}))
        self.assertFalse(creada)
        self.assertEqual(Lectura.objects.count(), 1)

    def test_lectura_antigua_no_pisa_el_estado_actual(self):
        ahora = timezone.now()
        registrar_lectura(parsear_payload({"device_id": "ESP32-0001", "distancia_cm": 12, "ts": ahora.isoformat()}))
        registrar_lectura(parsear_payload({"device_id": "ESP32-0001", "distancia_cm": 100, "ts": (ahora - timedelta(hours=1)).isoformat()}))
        self.contenedor.refresh_from_db()
        self.assertEqual(self.contenedor.nivel_actual_pct, 90)
        self.assertEqual(Lectura.objects.count(), 2)

    def test_dispositivo_desconocido_o_sin_contenedor(self):
        with self.assertRaises(DispositivoDesconocido):
            registrar_lectura(parsear_payload({"device_id": "ESP32-9999", "distancia_cm": 10}))
        Dispositivo.objects.create(device_id="ESP32-0002")
        with self.assertRaises(DispositivoDesconocido):
            registrar_lectura(parsear_payload({"device_id": "ESP32-0002", "distancia_cm": 10}))


class WorkerMQTTTests(TestCase):
    """Prueba el procesamiento de mensajes del worker sin necesitar un broker real."""

    def setUp(self):
        Dispositivo.objects.create(device_id="ESP32-0001", contenedor=crear_contenedor())
        self.worker = WorkerCommand(stdout=StringIO())
        self.worker.prefijo = "ecohuanuco/v1"
        self.worker.stats = Estadisticas()

    def test_procesa_telemetria_valida_invalida_y_desconocida(self):
        base = "ecohuanuco/v1/contenedores/{}/telemetria"
        self.worker.procesar_mensaje(base.format("ESP32-0001"), json.dumps({"distancia_cm": 60}).encode())
        self.worker.procesar_mensaje(base.format("ESP32-0001"), b"basura")
        self.worker.procesar_mensaje(base.format("ESP32-0404"), json.dumps({"distancia_cm": 60}).encode())
        self.assertEqual(self.worker.stats.guardados, 1)
        self.assertEqual(self.worker.stats.invalidos, 1)
        self.assertEqual(self.worker.stats.desconocidos, 1)
        self.assertEqual(Lectura.objects.get().nivel_pct, 50)

    def test_mensaje_de_estado_online(self):
        self.worker.procesar_mensaje("ecohuanuco/v1/contenedores/ESP32-0001/estado", b"online")
        self.assertIsNotNone(Dispositivo.objects.get().ultima_conexion)


class ApiContenedoresTests(APITestCase):
    def setUp(self):
        self.c1 = crear_contenedor("CNT-001", nivel=90)
        self.c2 = crear_contenedor("CNT-002", nivel=60)
        self.c3 = crear_contenedor("CNT-003", nivel=20)
        self.c4 = crear_contenedor("CNT-004", nivel=95, estado=Contenedor.Estado.MANTENIMIENTO)

    def test_listar_y_filtrar_por_semaforo(self):
        r = self.client.get("/api/contenedores/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["count"], 4)
        r = self.client.get("/api/contenedores/?semaforo=rojo")
        self.assertEqual({c["codigo"] for c in r.data["results"]}, {"CNT-001", "CNT-004"})
        r = self.client.get("/api/contenedores/?nivel_min=50&nivel_max=70")
        self.assertEqual([c["codigo"] for c in r.data["results"]], ["CNT-002"])

    def test_criticos_solo_activos_ordenados(self):
        r = self.client.get("/api/contenedores/criticos/?umbral=50")
        self.assertEqual([c["codigo"] for c in r.data], ["CNT-001", "CNT-002"])

    def test_crear_contenedor_con_dispositivo(self):
        r = self.client.post("/api/contenedores/", {
            "codigo": "cnt-050", "nombre": "Mercado", "latitud": "-9.930000", "longitud": "-76.240000",
            "capacidad_litros": 660, "altura_util_cm": 100, "device_id": "esp32-0050",
        }, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["codigo"], "CNT-050")
        self.assertEqual(r.data["dispositivo"]["device_id"], "ESP32-0050")

    def test_validaciones_al_crear(self):
        r = self.client.post("/api/contenedores/", {"codigo": "CNT-001", "nombre": "x", "latitud": 200, "longitud": 0}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("codigo", r.data)
        self.assertIn("latitud", r.data)

    def test_no_permite_reusar_un_dispositivo_instalado(self):
        Dispositivo.objects.create(device_id="ESP32-0001", contenedor=self.c1)
        r = self.client.post("/api/contenedores/", {
            "codigo": "CNT-060", "nombre": "x", "latitud": -9.9, "longitud": -76.2, "device_id": "ESP32-0001",
        }, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("device_id", r.data)

    def test_actualizar_y_eliminar(self):
        r = self.client.patch(f"/api/contenedores/{self.c3.pk}/", {"estado": "inactivo"}, format="json")
        self.assertEqual(r.data["estado"], "inactivo")
        self.assertEqual(self.client.delete(f"/api/contenedores/{self.c3.pk}/").status_code, 204)

    def test_resumen(self):
        r = self.client.get("/api/contenedores/resumen/")
        self.assertEqual(r.data["total_contenedores"], 4)
        self.assertEqual(r.data["por_semaforo"]["rojo"], 1)  # el de mantenimiento no cuenta

    def test_historial_de_lecturas(self):
        d = Dispositivo.objects.create(device_id="ESP32-0001", contenedor=self.c1)
        for h in (1, 5, 30):
            Lectura.objects.create(dispositivo=d, contenedor=self.c1, distancia_cm=50, distancia_corregida_cm=50,
                                   nivel_pct=58, medido_en=timezone.now() - timedelta(hours=h))
        r = self.client.get(f"/api/contenedores/{self.c1.pk}/lecturas/?horas=24")
        self.assertEqual(r.data["count"], 2)


class ApiDispositivosYTelemetriaTests(APITestCase):
    def setUp(self):
        self.contenedor = crear_contenedor()
        Dispositivo.objects.create(device_id="ESP32-0001", contenedor=self.contenedor)

    def test_buscar_por_device_id(self):
        r = self.client.get("/api/dispositivos/esp32-0001/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["contenedor_codigo"], "CNT-001")

    def test_aplicar_calibracion(self):
        r = self.client.post("/api/dispositivos/ESP32-0001/calibracion/", {"factor_escala": 1.02, "offset_cm": -1.5}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["factor_escala"], 1.02)
        self.assertIsNotNone(r.data["calibrado_en"])
        r = self.client.post("/api/dispositivos/ESP32-0001/calibracion/", {"factor_escala": 3, "offset_cm": 0}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_telemetria_http(self):
        r = self.client.post("/api/telemetria/", {"device_id": "ESP32-0001", "distancia_cm": 30}, format="json")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.data["nivel_pct"], 75)
        self.assertEqual(r.data["semaforo"], "rojo")
        self.assertEqual(self.client.post("/api/telemetria/", {"device_id": "ESP32-0001"}, format="json").status_code, 400)
        self.assertEqual(self.client.post("/api/telemetria/", {"device_id": "ESP32-0404", "distancia_cm": 3}, format="json").status_code, 404)

    def test_salud_y_documentacion(self):
        self.assertEqual(self.client.get("/api/salud/").data["estado"], "ok")
        self.assertEqual(self.client.get("/api/schema/").status_code, 200)


class DatosDemoTests(TestCase):
    def test_carga_datos_demo(self):
        call_command("cargar_datos_demo", stdout=StringIO())
        self.assertEqual(Contenedor.objects.count(), 20)
        self.assertTrue(Lectura.objects.exists())
        self.assertGreater(Contenedor.objects.filter(nivel_actual_pct__gte=75).count(), 3)
