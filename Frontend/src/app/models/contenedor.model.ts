export interface Contenedor {
  id?: number;
  mac: string;
  latitud: number;
  longitud: number;
  capacidad: number;
  nivel_llenado?: number; // Lo agregamos para la T-106
  bateria?: number;       // Lo agregamos para la T-106
}