import { Component, AfterViewInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ContenedorService } from '../../services/contenedor.service';
import { Contenedor } from '../../models/contenedor.model';
import * as L from 'leaflet';

@Component({
  selector: 'app-registro-contenedor',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './registro-contenedor.html',
  styleUrls: ['./registro-contenedor.css']
})
export class RegistroContenedorComponent implements AfterViewInit, OnDestroy {
  private map!: L.Map;
  private marker?: L.Marker;
  
  // Datos del formulario
  nuevoContenedor: Contenedor = {
    mac: '',
    latitud: -9.9306, // Centro de Huánuco por defecto
    longitud: -76.2422,
    capacidad: 100
  };
  
  mensaje: string = '';
  error: string = '';

  constructor(private contenedorService: ContenedorService) {}

  ngAfterViewInit(): void {
    this.initMap();
  }

  ngOnDestroy(): void {
    if (this.map) {
      this.map.remove();
    }
  }

  private initMap(): void {
    // Coordenadas de Huánuco
    const huancuoCoords: L.LatLngExpression = [-9.9306, -76.2422];
    
    this.map = L.map('map').setView(huancuoCoords, 14);

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '© OpenStreetMap contributors'
    }).addTo(this.map);

    // Evento: clic en el mapa para poner el marcador
    this.map.on('click', (e: L.LeafletMouseEvent) => {
      this.actualizarUbicacion(e.latlng.lat, e.latlng.lng);
    });

    // Poner un marcador inicial (opcional)
    this.actualizarUbicacion(this.nuevoContenedor.latitud, this.nuevoContenedor.longitud);
  }

  private actualizarUbicacion(lat: number, lng: number): void {
    this.nuevoContenedor.latitud = lat;
    this.nuevoContenedor.longitud = lng;

    if (this.marker) {
      this.marker.setLatLng([lat, lng]);
    } else {
      this.marker = L.marker([lat, lng], { draggable: true }).addTo(this.map);
      
      // Si el usuario arrastra el marcador, actualizamos los datos
      this.marker.on('dragend', () => {
        const position = this.marker!.getLatLng();
        this.nuevoContenedor.latitud = position.lat;
        this.nuevoContenedor.longitud = position.lng;
      });
    }
  }

  onSubmit(): void {
    this.mensaje = '';
    this.error = '';

    // Validación básica de HU-01: Coordenadas dentro de Huánuco (rango aproximado)
    const { latitud, longitud } = this.nuevoContenedor;
    if (latitud < -10.1 || latitud > -9.8 || longitud < -76.4 || longitud > -76.1) {
      this.error = 'Las coordenadas deben estar dentro del distrito de Huánuco.';
      return;
    }

    if (!this.nuevoContenedor.mac || this.nuevoContenedor.mac.trim() === '') {
      this.error = 'La dirección MAC es obligatoria.';
      return;
    }

    // Llamada al backend
    this.contenedorService.registrarContenedor(this.nuevoContenedor).subscribe({
      next: (res) => {
        this.mensaje = 'Contenedor registrado exitosamente.';
        // Resetear formulario (excepto mapa)
        this.nuevoContenedor = { mac: '', latitud: latitud, longitud: longitud, capacidad: 100 };
      },
      error: (err) => {
        this.error = 'Error al registrar: ' + (err.error?.mac || err.message);
      }
    });
  }
}