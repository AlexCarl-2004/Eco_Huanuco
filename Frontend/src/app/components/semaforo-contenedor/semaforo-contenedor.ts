import { Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'app-semaforo-contenedor',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './semaforo-contenedor.html',
  styleUrls: ['./semaforo-contenedor.css']
})
export class SemaforoContenedorComponent {
  @Input() nivelLlenado: number = 0; // Porcentaje de 0 a 100
  @Input() bateria: number = 100;    // Porcentaje de 0 a 100

  // Lógica del semáforo
  get colorEstado(): string {
    if (this.bateria < 15) return 'bg-warning'; // Ámbar
    if (this.nivelLlenado >= 75) return 'bg-danger'; // Rojo
    return 'bg-success'; // Verde
  }

  get textoEstado(): string {
    if (this.bateria < 15) return 'Batería Baja';
    if (this.nivelLlenado >= 75) return 'Lleno (Recolectar)';
    return 'Disponible';
  }
}