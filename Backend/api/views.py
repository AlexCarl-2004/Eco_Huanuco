from django.db import connection
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView


class SaludView(APIView):
    """Comprobación rápida de que la API y la base de datos responden."""

    @extend_schema(tags=["Sistema"], summary="Estado del servicio", responses={200: dict})
    def get(self, request):
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
            base_datos = "ok"
        except Exception as exc:  # noqa: BLE001
            base_datos = f"error: {exc}"
        return Response({
            "servicio": "EcoHuánuco AI",
            "estado": "ok" if base_datos == "ok" else "degradado",
            "base_datos": base_datos,
            "motor": connection.vendor,
            "hora_servidor": timezone.localtime().isoformat(),
        })
