from rest_framework import serializers
from .models import Contenedor

class ContenedorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Contenedor
        fields = ['id', 'mac', 'latitud', 'longitud', 'capacidad', 'estado', 'fecha_registro']
        read_only_fields = ['id', 'fecha_registro']

    def validate_mac(self, value):
        # HU-01 Criterio 2: MAC no duplicada
        if Contenedor.objects.filter(mac=value).exists():
            raise serializers.ValidationError("Ya existe un contenedor con esta MAC.")
        return value

    def validate(self, data):
        # HU-01 Criterio 2: coordenadas dentro del distrito de Huánuco
        lat = float(data.get('latitud'))
        lng = float(data.get('longitud'))
        # Rango aproximado de Huánuco (ajústalo según tu mapa)
        if not (-10.1 <= lat <= -9.8 and -76.4 <= lng <= -76.1):
            raise serializers.ValidationError(
                "Las coordenadas deben estar dentro del distrito de Huánuco."
            )
        return data