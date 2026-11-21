"""ECO-3 · T-102 — API REST CRUD de contenedores y dispositivos IoT."""

from datetime import timedelta

from django.conf import settings
from django.db.models import Avg
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from .filters import ContenedorFilter, LecturaFilter
from .models import Contenedor, Dispositivo, Lectura, Semaforo, calcular_semaforo
from .serializers import (
    CalibracionSerializer,
    ContenedorRegistroIoTSerializer,
    ContenedorSerializer,
    DispositivoSerializer,
    LecturaSerializer,
    ResumenSerializer,
    TelemetriaEntradaSerializer,
)
from .telemetria import DispositivoDesconocido, PayloadInvalido, parsear_payload, registrar_lectura


@extend_schema_view(
    list=extend_schema(summary="Listar contenedores", description="Admite filtros por estado, tipo, sector, semáforo y rango de nivel."),
    retrieve=extend_schema(summary="Detalle de un contenedor"),
    create=extend_schema(summary="Registrar contenedor (opcionalmente con su dispositivo IoT)"),
    update=extend_schema(summary="Actualizar contenedor"),
    partial_update=extend_schema(summary="Actualizar parcialmente un contenedor"),
    destroy=extend_schema(summary="Eliminar contenedor"),
)
@extend_schema(tags=["Contenedores"])
class ContenedorViewSet(viewsets.ModelViewSet):
    queryset = Contenedor.objects.select_related("dispositivo").all()
    filterset_class = ContenedorFilter
    search_fields = ["codigo", "nombre", "direccion", "sector"]
    ordering_fields = ["codigo", "nivel_actual_pct", "ultima_lectura_en", "creado_en"]

    def get_serializer_class(self):
        if self.action == "create":
            return ContenedorRegistroIoTSerializer
        return ContenedorSerializer

    @extend_schema(
        summary="Historial de lecturas del contenedor",
        parameters=[OpenApiParameter("horas", int, description="Ventana de tiempo hacia atrás (por defecto 24)")],
        responses=LecturaSerializer(many=True),
    )
    @action(detail=True, methods=["get"])
    def lecturas(self, request, pk=None):
        contenedor = self.get_object()
        try:
            horas = max(1, min(int(request.query_params.get("horas", 24)), 24 * 90))
        except ValueError:
            horas = 24
        qs = contenedor.lecturas.select_related("dispositivo", "contenedor").filter(
            medido_en__gte=timezone.now() - timedelta(hours=horas)
        )
        pagina = self.paginate_queryset(qs)
        serializer = LecturaSerializer(pagina if pagina is not None else qs, many=True)
        return self.get_paginated_response(serializer.data) if pagina is not None else Response(serializer.data)

    @extend_schema(summary="Indicadores generales para el dashboard", responses=ResumenSerializer)
    @action(detail=False, methods=["get"])
    def resumen(self, request):
        qs = Contenedor.objects.all()
        activos = qs.filter(estado=Contenedor.Estado.ACTIVO)
        por_semaforo = {s.value: 0 for s in Semaforo}
        for nivel in activos.values_list("nivel_actual_pct", flat=True):
            por_semaforo[calcular_semaforo(nivel)] += 1
        dispositivos = list(Dispositivo.objects.filter(activo=True))
        promedio = activos.aggregate(p=Avg("nivel_actual_pct"))["p"]
        datos = {
            "total_contenedores": qs.count(),
            "activos": activos.count(),
            "por_semaforo": por_semaforo,
            "nivel_promedio_pct": round(promedio, 1) if promedio is not None else None,
            "dispositivos_total": len(dispositivos),
            "dispositivos_en_linea": sum(d.en_linea for d in dispositivos),
            "lecturas_24h": Lectura.objects.filter(medido_en__gte=timezone.now() - timedelta(hours=24)).count(),
        }
        return Response(ResumenSerializer(datos).data)

    @extend_schema(
        summary="Contenedores que superan el umbral de llenado",
        parameters=[OpenApiParameter("umbral", float, description="Por defecto el configurado (75 %)")],
        responses=ContenedorSerializer(many=True),
    )
    @action(detail=False, methods=["get"])
    def criticos(self, request):
        try:
            umbral = float(request.query_params.get("umbral", settings.RUTAS["UMBRAL_LLENADO_PCT"]))
        except ValueError:
            umbral = settings.RUTAS["UMBRAL_LLENADO_PCT"]
        qs = self.get_queryset().filter(
            estado=Contenedor.Estado.ACTIVO, nivel_actual_pct__gte=umbral
        ).order_by("-nivel_actual_pct")
        return Response(ContenedorSerializer(qs, many=True).data)


@extend_schema_view(
    list=extend_schema(summary="Listar dispositivos IoT"),
    retrieve=extend_schema(summary="Detalle de un dispositivo"),
    create=extend_schema(summary="Registrar dispositivo"),
    update=extend_schema(summary="Actualizar dispositivo"),
    partial_update=extend_schema(summary="Actualizar parcialmente un dispositivo"),
    destroy=extend_schema(summary="Eliminar dispositivo"),
)
@extend_schema(tags=["Dispositivos"])
class DispositivoViewSet(viewsets.ModelViewSet):
    queryset = Dispositivo.objects.select_related("contenedor").all()
    serializer_class = DispositivoSerializer
    filterset_fields = ["activo", "modelo_sensor", "contenedor"]
    search_fields = ["device_id", "contenedor__codigo", "contenedor__nombre"]
    ordering_fields = ["device_id", "ultima_conexion", "bateria_pct"]
    lookup_value_regex = "[^/]+"

    def get_object(self):
        # Permite usar tanto el id numérico como el device_id: /dispositivos/ESP32-0001/
        valor = self.kwargs[self.lookup_field]
        if not str(valor).isdigit():
            self.lookup_field = "device_id"
            self.kwargs["device_id"] = str(valor).upper()
        return super().get_object()

    @extend_schema(
        summary="Aplicar coeficientes de calibración (ECO-8)",
        request=CalibracionSerializer,
        responses=DispositivoSerializer,
    )
    @action(detail=True, methods=["post"])
    def calibracion(self, request, pk=None):
        dispositivo = self.get_object()
        serializer = CalibracionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        dispositivo.factor_escala = serializer.validated_data["factor_escala"]
        dispositivo.offset_cm = serializer.validated_data["offset_cm"]
        dispositivo.calibrado_en = timezone.now()
        dispositivo.save(update_fields=["factor_escala", "offset_cm", "calibrado_en", "actualizado_en"])
        return Response(DispositivoSerializer(dispositivo).data)


@extend_schema_view(
    list=extend_schema(summary="Listar lecturas de telemetría"),
    retrieve=extend_schema(summary="Detalle de una lectura"),
)
@extend_schema(tags=["Telemetría"])
class LecturaViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = Lectura.objects.select_related("dispositivo", "contenedor").all()
    serializer_class = LecturaSerializer
    filterset_class = LecturaFilter
    ordering_fields = ["medido_en", "nivel_pct"]


@extend_schema(tags=["Telemetría"])
class TelemetriaView(APIView):
    """Ingreso de telemetría por HTTP, alternativo a MQTT (mismo formato de payload)."""

    @extend_schema(
        summary="Enviar una lectura por HTTP",
        request=TelemetriaEntradaSerializer,
        responses={
            201: LecturaSerializer,
            200: OpenApiResponse(LecturaSerializer, description="Lectura duplicada; se devuelve la existente"),
            400: OpenApiResponse(description="Payload inválido"),
            404: OpenApiResponse(description="Dispositivo no registrado"),
        },
    )
    def post(self, request):
        try:
            dato = parsear_payload(dict(request.data))
            lectura, creada = registrar_lectura(dato, Lectura.Origen.HTTP)
        except PayloadInvalido as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except DispositivoDesconocido as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        return Response(
            LecturaSerializer(lectura).data,
            status=status.HTTP_201_CREATED if creada else status.HTTP_200_OK,
        )
