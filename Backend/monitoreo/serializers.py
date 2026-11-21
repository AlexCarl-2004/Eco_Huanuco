from django.db import transaction
from rest_framework import serializers

from .models import Contenedor, Dispositivo, Lectura


class DispositivoResumenSerializer(serializers.ModelSerializer):
    en_linea = serializers.BooleanField(read_only=True)

    class Meta:
        model = Dispositivo
        fields = ["id", "device_id", "modelo_sensor", "en_linea", "bateria_pct", "rssi_dbm", "ultima_conexion"]


class ContenedorSerializer(serializers.ModelSerializer):
    semaforo = serializers.CharField(read_only=True)
    litros_estimados = serializers.FloatField(read_only=True)
    dispositivo = DispositivoResumenSerializer(read_only=True)

    class Meta:
        model = Contenedor
        fields = [
            "id", "codigo", "nombre", "direccion", "sector", "latitud", "longitud",
            "tipo_residuo", "capacidad_litros", "altura_util_cm", "estado",
            "nivel_actual_pct", "semaforo", "litros_estimados", "ultima_lectura_en",
            "dispositivo", "creado_en", "actualizado_en",
        ]
        read_only_fields = ["nivel_actual_pct", "ultima_lectura_en", "creado_en", "actualizado_en"]

    def validate_codigo(self, valor: str) -> str:
        return valor.strip().upper()


class ContenedorRegistroIoTSerializer(ContenedorSerializer):
    """
    Registro de un contenedor junto con su dispositivo IoT en una sola petición.
    Pensado para el formulario de alta del Frontend (ECO-4).
    """

    device_id = serializers.CharField(write_only=True, required=False, max_length=40)
    modelo_sensor = serializers.ChoiceField(
        choices=Dispositivo.ModeloSensor.choices, write_only=True, required=False,
        default=Dispositivo.ModeloSensor.JSN_SR04T,
    )

    class Meta(ContenedorSerializer.Meta):
        fields = ContenedorSerializer.Meta.fields + ["device_id", "modelo_sensor"]

    def validate_device_id(self, valor: str) -> str:
        valor = valor.strip().upper()
        existente = Dispositivo.objects.filter(device_id=valor).select_related("contenedor").first()
        if existente and existente.contenedor_id:
            raise serializers.ValidationError(
                f"El dispositivo ya está instalado en {existente.contenedor.codigo}."
            )
        return valor

    @transaction.atomic
    def create(self, validated_data):
        device_id = validated_data.pop("device_id", None)
        modelo = validated_data.pop("modelo_sensor", Dispositivo.ModeloSensor.JSN_SR04T)
        contenedor = super().create(validated_data)
        if device_id:
            Dispositivo.objects.update_or_create(
                device_id=device_id,
                defaults={"contenedor": contenedor, "modelo_sensor": modelo, "activo": True},
            )
        return contenedor


class DispositivoSerializer(serializers.ModelSerializer):
    en_linea = serializers.BooleanField(read_only=True)
    contenedor_codigo = serializers.CharField(source="contenedor.codigo", read_only=True, default=None)

    class Meta:
        model = Dispositivo
        fields = [
            "id", "device_id", "contenedor", "contenedor_codigo", "modelo_sensor", "firmware", "activo",
            "factor_escala", "offset_cm", "calibrado_en",
            "en_linea", "ultima_conexion", "bateria_pct", "rssi_dbm", "creado_en", "actualizado_en",
        ]
        read_only_fields = ["ultima_conexion", "bateria_pct", "rssi_dbm", "creado_en", "actualizado_en"]

    def validate_device_id(self, valor: str) -> str:
        return valor.strip().upper()

    def validate_factor_escala(self, valor: float) -> float:
        if not 0.5 <= valor <= 1.5:
            raise serializers.ValidationError("El factor de escala debe estar entre 0.5 y 1.5.")
        return valor


class CalibracionSerializer(serializers.Serializer):
    factor_escala = serializers.FloatField(min_value=0.5, max_value=1.5)
    offset_cm = serializers.FloatField(min_value=-50, max_value=50)


class LecturaSerializer(serializers.ModelSerializer):
    device_id = serializers.CharField(source="dispositivo.device_id", read_only=True)
    contenedor_codigo = serializers.CharField(source="contenedor.codigo", read_only=True)
    semaforo = serializers.CharField(read_only=True)

    class Meta:
        model = Lectura
        fields = [
            "id", "device_id", "contenedor", "contenedor_codigo", "distancia_cm", "distancia_corregida_cm",
            "nivel_pct", "semaforo", "temperatura_c", "bateria_pct", "rssi_dbm",
            "medido_en", "recibido_en", "origen",
        ]


class TelemetriaEntradaSerializer(serializers.Serializer):
    """Documenta el payload que acepta `POST /api/telemetria/` (mismo formato que MQTT)."""

    device_id = serializers.CharField(max_length=40)
    distancia_cm = serializers.FloatField()
    ts = serializers.CharField(required=False, help_text="ISO-8601 o epoch en segundos")
    temp_c = serializers.FloatField(required=False)
    bateria = serializers.IntegerField(required=False, min_value=0, max_value=100)
    rssi = serializers.IntegerField(required=False)
    fw = serializers.CharField(required=False, max_length=20)


class ResumenSerializer(serializers.Serializer):
    total_contenedores = serializers.IntegerField()
    activos = serializers.IntegerField()
    por_semaforo = serializers.DictField(child=serializers.IntegerField())
    nivel_promedio_pct = serializers.FloatField(allow_null=True)
    dispositivos_total = serializers.IntegerField()
    dispositivos_en_linea = serializers.IntegerField()
    lecturas_24h = serializers.IntegerField()
