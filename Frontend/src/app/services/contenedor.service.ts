import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { Contenedor } from '../models/contenedor.model';

@Injectable({
  providedIn: 'root'
})
export class ContenedorService {
  private apiUrl = 'http://localhost:8000/api/contenedores/'; 

  constructor(private http: HttpClient) {}

  registrarContenedor(contenedor: Contenedor): Observable<Contenedor> {
    return this.http.post<Contenedor>(this.apiUrl, contenedor);
  }

  getContenedores(): Observable<Contenedor[]> {
    return this.http.get<Contenedor[]>(this.apiUrl);
  }
}