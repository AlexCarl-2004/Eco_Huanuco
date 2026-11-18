from django.db import models

class Contenedor(models.Model):
    ESTADOS = [
        ('Activo', 'Activo'),
        ('Inactivo', 'Inactivo'),
        ('Mantenimiento', 'Mantenimiento'),
    ]

    mac = models.CharField(max_length=17, unique=True)
    latitud = models.DecimalField(max_digits=9, decimal_places=6)
    longitud = models.DecimalField(max_digits=9, decimal_places=6)
    capacidad = models.DecimalField(max_digits=8, decimal_places=2, default=100)
    estado = models.CharField(max_length=20, choices=ESTADOS, default='Activo')
    fecha_registro = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.mac} ({self.estado})"