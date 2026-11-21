"""
ECO-2 · T-101 — Esquema de datos de contenedores y dispositivos IoT.

    Contenedor 1 ──── 0..1 Dispositivo
         1                    1
         └──── * Lectura * ───┘

- Contenedor: punto físico de acopio en la ciudad.
- Dispositivo: nodo IoT (ESP32 + sensor ultrasónico) instalado en la tapa.
- Lectura: cada medición de telemetría recibida por MQTT o HTTP.

El esquema equivalente en SQL para MySQL 8 está en DataBase/schema.sql.
"""

from datetime import timedelta

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone


class Semaforo(models.TextChoices):
    """Clasificación del nivel de llenado usada por el Frontend y por las rutas."""

    VERDE = "verde", "Verde (< 50 %)"
    AMBAR = "ambar", "Ámbar (50 – 75 %)"
    ROJO = "rojo", "Rojo (≥ 75 %)"
    SIN_DATOS = "sin_datos", "Sin datos"


def calcular_semaforo(nivel_pct: float | None) -> str:
    if nivel_pct is None:
        return Semaforo.SIN_DATOS
    if nivel_pct >= settings.RUTAS["UMBRAL_LLENADO_PCT"]:
        return Semaforo.ROJO
    if nivel_pct >= 50:
        return Semaforo.AMBAR
    return Semaforo.VERDE


class ModeloBase(models.Model):
    creado_en = models.DateTimeField("creado", auto_now_add=True)
    actualizado_en = models.DateTimeField("actualizado", auto_now=True)

    class Meta:
        abstract = True


class Contenedor(ModeloBase):
    class TipoResiduo(models.TextChoices):
        GENERAL = "general", "General"
        ORGANICO = "organico", "Orgánico"
        RECICLABLE = "reciclable", "Reciclable"
        PELIGROSO = "peligroso", "Peligroso"

    class Estado(models.TextChoices):
        ACTIVO = "activo", "Activo"
        MANTENIMIENTO = "mantenimiento", "En mantenimiento"
        INACTIVO = "inactivo", "Inactivo"

    codigo = models.CharField("código", max_length=20, unique=True, help_text="Ej.: CNT-001")
    nombre = models.CharField(max_length=120, help_text="Referencia del lugar. Ej.: Plaza de Armas")
    direccion = models.CharField("dirección", max_length=200, blank=True)
    sector = models.CharField(max_length=80, blank=True, help_text="Distrito o sector. Ej.: Huánuco, Amarilis, Pillco Marca")
    latitud = models.DecimalField(
        max_digits=9, decimal_places=6,
        validators=[MinValueValidator(-90), MaxValueValidator(90)],
    )
    longitud = models.DecimalField(
        max_digits=9, decimal_places=6,
        validators=[MinValueValidator(-180), MaxValueValidator(180)],
    )
    tipo_residuo = models.CharField("tipo de residuo", max_length=20, choices=TipoResiduo.choices, default=TipoResiduo.GENERAL)
    capacidad_litros = models.PositiveIntegerField("capacidad (L)", validators=[MinValueValidator(1)], default=1100)
    altura_util_cm = models.FloatField(
        "altura útil (cm)", validators=[MinValueValidator(1)], default=120,
        help_text="Distancia desde el sensor hasta el fondo del contenedor vacío.",
    )
    estado = models.CharField(max_length=20, choices=Estado.choices, default=Estado.ACTIVO)

    # Campos desnormalizados con la última lectura, para consultas rápidas
    nivel_actual_pct = models.FloatField("nivel actual (%)", null=True, blank=True)
    ultima_lectura_en = models.DateTimeField("última lectura", null=True, blank=True)

    class Meta:
        verbose_name = "contenedor"
        verbose_name_plural = "contenedores"
        ordering = ["codigo"]
        indexes = [
            models.Index(fields=["estado", "nivel_actual_pct"], name="idx_cont_estado_nivel"),
        ]

    def __str__(self) -> str:
        return f"{self.codigo} · {self.nombre}"

    @property
    def semaforo(self) -> str:
        return calcular_semaforo(self.nivel_actual_pct)

    @property
    def litros_estimados(self) -> float:
        """Volumen de residuos estimado según el nivel actual."""
        return round(self.capacidad_litros * (self.nivel_actual_pct or 0) / 100, 1)


class Dispositivo(ModeloBase):
    class ModeloSensor(models.TextChoices):
        JSN_SR04T = "JSN-SR04T", "JSN-SR04T (impermeable)"
        HC_SR04 = "HC-SR04", "HC-SR04"
        A02YYUW = "A02YYUW", "DFRobot A02YYUW"
        OTRO = "otro", "Otro"

    device_id = models.CharField(
        "ID del dispositivo", max_length=40, unique=True,
        help_text="Identificador que el equipo usa en MQTT. Ej.: ESP32-0001",
    )
    contenedor = models.OneToOneField(
        Contenedor, on_delete=models.SET_NULL, null=True, blank=True, related_name="dispositivo",
    )
    modelo_sensor = models.CharField("modelo del sensor", max_length=20, choices=ModeloSensor.choices, default=ModeloSensor.JSN_SR04T)
    firmware = models.CharField(max_length=20, blank=True)
    activo = models.BooleanField(default=True)

    # Calibración (ECO-8): distancia_corregida = factor_escala * distancia_medida + offset_cm
    factor_escala = models.FloatField(default=1.0, help_text="Pendiente obtenida en la calibración")
    offset_cm = models.FloatField("offset (cm)", default=0.0, help_text="Intercepto obtenido en la calibración")
    calibrado_en = models.DateTimeField("calibrado", null=True, blank=True)

    # Diagnóstico
    ultima_conexion = models.DateTimeField("última conexión", null=True, blank=True)
    bateria_pct = models.PositiveSmallIntegerField("batería (%)", null=True, blank=True, validators=[MaxValueValidator(100)])
    rssi_dbm = models.SmallIntegerField("señal (dBm)", null=True, blank=True)

    class Meta:
        verbose_name = "dispositivo"
        verbose_name_plural = "dispositivos"
        ordering = ["device_id"]

    def __str__(self) -> str:
        return self.device_id

    @property
    def en_linea(self) -> bool:
        if not self.ultima_conexion:
            return False
        limite = timezone.now() - timedelta(minutes=settings.DISPOSITIVO_TIMEOUT_MIN)
        return self.ultima_conexion >= limite

    def corregir_distancia(self, distancia_cm: float) -> float:
        return self.factor_escala * distancia_cm + self.offset_cm


class Lectura(models.Model):
    class Origen(models.TextChoices):
        MQTT = "mqtt", "MQTT"
        HTTP = "http", "HTTP"
        SIMULADOR = "simulador", "Simulador"

    dispositivo = models.ForeignKey(Dispositivo, on_delete=models.CASCADE, related_name="lecturas")
    contenedor = models.ForeignKey(Contenedor, on_delete=models.CASCADE, related_name="lecturas")
    distancia_cm = models.FloatField("distancia medida (cm)")
    distancia_corregida_cm = models.FloatField("distancia corregida (cm)")
    nivel_pct = models.FloatField("nivel (%)", validators=[MinValueValidator(0), MaxValueValidator(100)])
    temperatura_c = models.FloatField("temperatura (°C)", null=True, blank=True)
    bateria_pct = models.PositiveSmallIntegerField("batería (%)", null=True, blank=True)
    rssi_dbm = models.SmallIntegerField("señal (dBm)", null=True, blank=True)
    medido_en = models.DateTimeField("medido", db_index=True)
    recibido_en = models.DateTimeField("recibido", auto_now_add=True)
    origen = models.CharField(max_length=12, choices=Origen.choices, default=Origen.MQTT)
    payload = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = "lectura"
        verbose_name_plural = "lecturas"
        ordering = ["-medido_en"]
        get_latest_by = "medido_en"
        indexes = [
            models.Index(fields=["contenedor", "-medido_en"], name="idx_lect_cont_fecha"),
        ]
        constraints = [
            # Evita duplicados cuando el broker reenvía un mensaje (QoS 1)
            models.UniqueConstraint(fields=["dispositivo", "medido_en"], name="uq_lectura_disp_fecha"),
        ]

    def __str__(self) -> str:
        return f"{self.dispositivo_id} · {self.nivel_pct:.0f}% · {self.medido_en:%d/%m %H:%M}"

    @property
    def semaforo(self) -> str:
        return calcular_semaforo(self.nivel_pct)
