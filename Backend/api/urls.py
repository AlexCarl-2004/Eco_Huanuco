from rest_framework.routers import DefaultRouter

from django.urls import include, path

from monitoreo.views import ContenedorViewSet, DispositivoViewSet, LecturaViewSet, TelemetriaView
from rutas.views import NodoViewSet, PlanRecoleccionViewSet, TramoViewSet, VehiculoViewSet

from .views import SaludView

router = DefaultRouter()
router.register("contenedores", ContenedorViewSet, basename="contenedor")
router.register("dispositivos", DispositivoViewSet, basename="dispositivo")
router.register("lecturas", LecturaViewSet, basename="lectura")
router.register("nodos", NodoViewSet, basename="nodo")
router.register("tramos", TramoViewSet, basename="tramo")
router.register("vehiculos", VehiculoViewSet, basename="vehiculo")
router.register("planes", PlanRecoleccionViewSet, basename="plan")

urlpatterns = [
    path("salud/", SaludView.as_view(), name="salud"),
    path("telemetria/", TelemetriaView.as_view(), name="telemetria"),
    path("", include(router.urls)),
]
