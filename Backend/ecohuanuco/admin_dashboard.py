"""Datos del panel principal del administrador (tema Unfold)."""

import json
from datetime import timedelta

from django.conf import settings
from django.db.models import Avg, Count
from django.db.models.functions import TruncHour
from django.utils import timezone

from monitoreo.models import Contenedor, Dispositivo, Lectura, Semaforo, calcular_semaforo
from rutas.models import PlanRecoleccion


def entorno(request):
    if settings.DEBUG:
        return ["Desarrollo", "warning"]
    return ["Producción", "success"]


def dashboard_callback(request, context):
    ahora = timezone.now()
    umbral = settings.RUTAS["UMBRAL_LLENADO_PCT"]
    activos = Contenedor.objects.filter(estado=Contenedor.Estado.ACTIVO)

    conteo = {s.value: 0 for s in Semaforo}
    for nivel in activos.values_list("nivel_actual_pct", flat=True):
        conteo[calcular_semaforo(nivel)] += 1
    total_activos = sum(conteo.values()) or 1

    dispositivos = list(Dispositivo.objects.filter(activo=True))
    en_linea = sum(d.en_linea for d in dispositivos)
    promedio = activos.aggregate(p=Avg("nivel_actual_pct"))["p"]
    lecturas_24h = Lectura.objects.filter(medido_en__gte=ahora - timedelta(hours=24))

    # Lecturas por hora (últimas 24 h) para el gráfico
    por_hora = {
        fila["hora"]: fila["total"]
        for fila in lecturas_24h.annotate(hora=TruncHour("medido_en")).values("hora").annotate(total=Count("id"))
    }
    inicio = timezone.localtime(ahora).replace(minute=0, second=0, microsecond=0) - timedelta(hours=23)
    horas = [inicio + timedelta(hours=h) for h in range(24)]
    grafico = {
        "labels": [h.strftime("%H:%M") for h in horas],
        "datasets": [{
            "label": "Lecturas",
            "data": [por_hora.get(h, 0) for h in horas],
            "backgroundColor": "#10b981",
            "borderRadius": 4,
            "maxBarThickness": 22,
        }],
    }

    criticos = activos.filter(nivel_actual_pct__gte=umbral).select_related("dispositivo").order_by("-nivel_actual_pct")[:8]
    ultimo_plan = PlanRecoleccion.objects.select_related("deposito").first()

    context.update({
        "umbral": int(umbral),
        "kpis": [
            {
                "titulo": "Contenedores activos",
                "valor": activos.count(),
                "detalle": f"{Contenedor.objects.count()} registrados",
                "icono": "delete",
                "tono": "neutro",
            },
            {
                "titulo": f"Por recoger (≥ {int(umbral)} %)",
                "valor": conteo[Semaforo.ROJO],
                "detalle": "listos para el próximo plan",
                "icono": "warning",
                "tono": "rojo" if conteo[Semaforo.ROJO] else "verde",
            },
            {
                "titulo": "Nivel promedio",
                "valor": f"{promedio:.0f} %" if promedio is not None else "—",
                "detalle": "de llenado en la ciudad",
                "icono": "water_full",
                "tono": "ambar" if promedio and promedio >= 50 else "verde",
            },
            {
                "titulo": "Sensores en línea",
                "valor": f"{en_linea}/{len(dispositivos)}",
                "detalle": f"{lecturas_24h.count()} lecturas en 24 h",
                "icono": "sensors",
                "tono": "verde" if dispositivos and en_linea == len(dispositivos) else "ambar",
            },
        ],
        "semaforo": [
            {"nombre": "Verde", "clase": "verde", "total": conteo[Semaforo.VERDE], "pct": round(conteo[Semaforo.VERDE] * 100 / total_activos)},
            {"nombre": "Ámbar", "clase": "ambar", "total": conteo[Semaforo.AMBAR], "pct": round(conteo[Semaforo.AMBAR] * 100 / total_activos)},
            {"nombre": "Rojo", "clase": "rojo", "total": conteo[Semaforo.ROJO], "pct": round(conteo[Semaforo.ROJO] * 100 / total_activos)},
            {"nombre": "Sin datos", "clase": "gris", "total": conteo[Semaforo.SIN_DATOS], "pct": round(conteo[Semaforo.SIN_DATOS] * 100 / total_activos)},
        ],
        "criticos": criticos,
        "grafico_lecturas": json.dumps(grafico),
        "ultimo_plan": ultimo_plan,
        "ultimo_plan_km": f"{ultimo_plan.distancia_total_m / 1000:.2f}".replace(".", ",") if ultimo_plan else "",
    })
    return context
