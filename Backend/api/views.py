from django.shortcuts import render
from rest_framework import viewsets
from .models import Contenedor
from .serializers import ContenedorSerializer

class ContenedorViewSet(viewsets.ModelViewSet):
    queryset = Contenedor.objects.all().order_by('-fecha_registro')
    serializer_class = ContenedorSerializer