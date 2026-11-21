import django_filters
from django.conf import settings
from django.db.models import Q

from .models import Contenedor, Lectura, Semaforo


class ContenedorFilter(django_filters.FilterSet):
    nivel_min = django_filters.NumberFilter(field_name="nivel_actual_pct", lookup_expr="gte", label="Nivel mínimo (%)")
    nivel_max = django_filters.NumberFilter(field_name="nivel_actual_pct", lookup_expr="lte", label="Nivel máximo (%)")
    semaforo = django_filters.ChoiceFilter(choices=Semaforo.choices, method="filtrar_semaforo")
    sector = django_filters.CharFilter(lookup_expr="icontains")
    con_dispositivo = django_filters.BooleanFilter(field_name="dispositivo", lookup_expr="isnull", exclude=True)

    class Meta:
        model = Contenedor
        fields = ["estado", "tipo_residuo", "sector", "nivel_min", "nivel_max", "semaforo", "con_dispositivo"]

    def filtrar_semaforo(self, queryset, name, value):
        umbral = settings.RUTAS["UMBRAL_LLENADO_PCT"]
        condiciones = {
            Semaforo.ROJO: Q(nivel_actual_pct__gte=umbral),
            Semaforo.AMBAR: Q(nivel_actual_pct__gte=50, nivel_actual_pct__lt=umbral),
            Semaforo.VERDE: Q(nivel_actual_pct__lt=50),
            Semaforo.SIN_DATOS: Q(nivel_actual_pct__isnull=True),
        }
        return queryset.filter(condiciones[value])


class LecturaFilter(django_filters.FilterSet):
    desde = django_filters.IsoDateTimeFilter(field_name="medido_en", lookup_expr="gte")
    hasta = django_filters.IsoDateTimeFilter(field_name="medido_en", lookup_expr="lte")
    device_id = django_filters.CharFilter(field_name="dispositivo__device_id")
    contenedor_codigo = django_filters.CharFilter(field_name="contenedor__codigo")

    class Meta:
        model = Lectura
        fields = ["contenedor", "dispositivo", "device_id", "contenedor_codigo", "origen", "desde", "hasta"]
