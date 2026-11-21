import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { SemaforoContenedorComponent } from '../../components/semaforo-contenedor/semaforo-contenedor';
import { ContenedorService } from '../../services/contenedor.service';
import { Contenedor } from '../../models/contenedor.model';

@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [CommonModule, SemaforoContenedorComponent],
  templateUrl: './dashboard.html',
  styleUrls: ['./dashboard.css']
})
export class DashboardComponent implements OnInit, OnDestroy {
  contenedores: Contenedor[] = [];
  private intervaloId: any;

  constructor(private contenedorService: ContenedorService) {}

  ngOnInit() {
    this.cargarDatos();
    // Actualización automática cada 5 segundos (5000 ms)
    this.intervaloId = setInterval(() => this.cargarDatos(), 5000);
  }

  ngOnDestroy() {
    // Limpiamos el intervalo si el usuario sale de la pantalla
    if (this.intervaloId) {
      clearInterval(this.intervaloId);
    }
  }

  cargarDatos() {
    this.contenedorService.getContenedores().subscribe({
      next: (data) => {
        // Si el backend aún no tiene nivel/batería, los simulamos temporalmente para que se vea el semáforo
        this.contenedores = data.map(c => ({
          ...c,
          nivel_llenado: c.nivel_llenado ?? Math.floor(Math.random() * 100),
          bateria: c.bateria ?? Math.floor(Math.random() * 100)
        }));
      },
      error: (err) => console.error('Error al cargar contenedores', err)
    });
  }
}