from django.conf import settings
from django.contrib import admin
from django.contrib.auth.admin import GroupAdmin as BaseGroupAdmin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group, User
from django.db.models import Q
from django.utils import timezone
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from unfold.admin import ModelAdmin, StackedInline
from unfold.decorators import display
from unfold.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm

from .models import Contenedor, Dispositivo, Lectura, Semaforo, calcular_semaforo

def barra_nivel(nivel: float | None):
    if nivel is None:
        return mark_safe('<span style="color:var(--eco-muted)">Sin datos</span>')
    clase = {"verde": "", "ambar": "eco-meter--ambar", "rojo": "eco-meter--rojo"}.get(calcular_semaforo(nivel), "")
    return format_html(
        '<span class="eco-nivel"><span class="eco-meter {}"><span style="width:{}%"></span></span><b>{} %</b></span>',
        clase, round(nivel), round(nivel),
    )


def fecha_corta(fecha):
    if not fecha:
        return "—"
    local = timezone.localtime(fecha)
    hoy = timezone.localdate()
    if local.date() == hoy:
        return f"Hoy, {local:%H:%M}"
    return f"{local:%d/%m/%Y %H:%M}"


# --------------------------------------------------------------------------- #
# Usuarios con el estilo de Unfold
# --------------------------------------------------------------------------- #
admin.site.unregister(User)
admin.site.unregister(Group)


@admin.register(User)
class UserAdmin(BaseUserAdmin, ModelAdmin):
    form = UserChangeForm
    add_form = UserCreationForm
    change_password_form = AdminPasswordChangeForm


@admin.register(Group)
class GroupAdmin(BaseGroupAdmin, ModelAdmin):
    pass


# --------------------------------------------------------------------------- #
# Filtros
# --------------------------------------------------------------------------- #
class SemaforoFilter(admin.SimpleListFilter):
    title = "semáforo"
    parameter_name = "semaforo"

    def lookups(self, request, model_admin):
        return Semaforo.choices

    def queryset(self, request, queryset):
        umbral = settings.RUTAS["UMBRAL_LLENADO_PCT"]
        condiciones = {
            Semaforo.ROJO: Q(nivel_actual_pct__gte=umbral),
            Semaforo.AMBAR: Q(nivel_actual_pct__gte=50, nivel_actual_pct__lt=umbral),
            Semaforo.VERDE: Q(nivel_actual_pct__lt=50),
            Semaforo.SIN_DATOS: Q(nivel_actual_pct__isnull=True),
        }
        if self.value() in condiciones:
            return queryset.filter(condiciones[self.value()])
        return queryset


# --------------------------------------------------------------------------- #
# Contenedores
# --------------------------------------------------------------------------- #
class DispositivoInline(StackedInline):
    model = Dispositivo
    extra = 0
    max_num = 1
    fields = [("device_id", "modelo_sensor", "activo"), ("factor_escala", "offset_cm", "calibrado_en"), ("ultima_conexion", "bateria_pct", "rssi_dbm")]
    readonly_fields = ["ultima_conexion", "bateria_pct", "rssi_dbm"]
    verbose_name = "Dispositivo IoT instalado"


@admin.register(Contenedor)
class ContenedorAdmin(ModelAdmin):
    list_display = ["codigo_corto", "nombre", "sector", "tipo_residuo", "nivel", "semaforo_label", "estado_label", "ultima_lectura"]
    list_display_links = ["codigo_corto", "nombre"]
    list_filter = [SemaforoFilter, "estado", "tipo_residuo", "sector"]
    search_fields = ["codigo", "nombre", "direccion", "sector"]
    ordering = ["-nivel_actual_pct"]
    readonly_fields = ["nivel_actual_pct", "ultima_lectura_en", "creado_en", "actualizado_en"]
    inlines = [DispositivoInline]
    list_per_page = 50
    fieldsets = [
        ("Identificación", {"fields": [("codigo", "estado"), "nombre", ("direccion", "sector")]}),
        ("Ubicación", {"fields": [("latitud", "longitud")]}),
        ("Características", {"fields": [("tipo_residuo", "capacidad_litros", "altura_util_cm")]}),
        ("Estado actual", {"fields": [("nivel_actual_pct", "ultima_lectura_en"), ("creado_en", "actualizado_en")]}),
    ]

    @display(description="Código", ordering="codigo")
    def codigo_corto(self, obj):
        return format_html('<span class="eco-codigo">{}</span>', obj.codigo)

    @display(description="Nivel", ordering="nivel_actual_pct")
    def nivel(self, obj):
        return barra_nivel(obj.nivel_actual_pct)

    @display(description="Última lectura", ordering="ultima_lectura_en")
    def ultima_lectura(self, obj):
        return fecha_corta(obj.ultima_lectura_en)

    @display(description="Semáforo", label={"Verde": "success", "Ámbar": "warning", "Rojo": "danger", "Sin datos": "info"})
    def semaforo_label(self, obj):
        return {"verde": "Verde", "ambar": "Ámbar", "rojo": "Rojo"}.get(obj.semaforo, "Sin datos")

    @display(description="Estado", label={"Activo": "success", "En mantenimiento": "warning", "Inactivo": "danger"})
    def estado_label(self, obj):
        return obj.get_estado_display()


# --------------------------------------------------------------------------- #
# Dispositivos
# --------------------------------------------------------------------------- #
@admin.register(Dispositivo)
class DispositivoAdmin(ModelAdmin):
    list_display = ["device_id", "contenedor", "sensor", "conexion", "bateria", "rssi_dbm", "calibracion", "conexion_fecha"]
    list_filter = ["activo", "modelo_sensor"]
    search_fields = ["device_id", "contenedor__codigo", "contenedor__nombre"]
    autocomplete_fields = ["contenedor"]
    readonly_fields = ["ultima_conexion", "bateria_pct", "rssi_dbm", "creado_en", "actualizado_en"]
    fieldsets = [
        ("Equipo", {"fields": [("device_id", "activo"), "contenedor", ("modelo_sensor", "firmware")]}),
        ("Calibración (ECO-8)", {
            "fields": [("factor_escala", "offset_cm", "calibrado_en")],
            "description": "distancia corregida = factor_escala × distancia medida + offset",
        }),
        ("Diagnóstico", {"fields": [("ultima_conexion", "bateria_pct", "rssi_dbm"), ("creado_en", "actualizado_en")]}),
    ]

    @display(description="Conexión")
    def conexion(self, obj):
        if obj.en_linea:
            return mark_safe('<span class="eco-pill eco-pill--on">En línea</span>')
        return mark_safe('<span class="eco-pill eco-pill--off">Fuera de línea</span>')

    @display(description="Batería", ordering="bateria_pct")
    def bateria(self, obj):
        if obj.bateria_pct is None:
            return "—"
        clase = "" if obj.bateria_pct >= 50 else "eco-meter--ambar" if obj.bateria_pct >= 20 else "eco-meter--rojo"
        return format_html(
            '<span class="eco-nivel"><span class="eco-meter {}"><span style="width:{}%"></span></span><b>{} %</b></span>',
            clase, obj.bateria_pct, obj.bateria_pct,
        )

    @display(description="Sensor", ordering="modelo_sensor")
    def sensor(self, obj):
        return obj.modelo_sensor

    @display(description="Última conexión", ordering="ultima_conexion")
    def conexion_fecha(self, obj):
        return fecha_corta(obj.ultima_conexion)

    @display(description="Calibrado", boolean=True)
    def calibracion(self, obj):
        return obj.calibrado_en is not None


# --------------------------------------------------------------------------- #
# Lecturas (sólo lectura: las crea el worker MQTT)
# --------------------------------------------------------------------------- #
@admin.register(Lectura)
class LecturaAdmin(ModelAdmin):
    list_display = ["fecha", "contenedor", "dispositivo", "nivel", "distancia_cm", "distancia_corregida_cm", "temperatura_c", "origen"]
    list_filter = ["origen", "contenedor"]
    search_fields = ["dispositivo__device_id", "contenedor__codigo"]
    date_hierarchy = "medido_en"
    list_select_related = ["contenedor", "dispositivo"]
    list_per_page = 50

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    @display(description="Medido", ordering="medido_en")
    def fecha(self, obj):
        return fecha_corta(obj.medido_en)

    @display(description="Nivel", ordering="nivel_pct")
    def nivel(self, obj):
        return barra_nivel(obj.nivel_pct)
