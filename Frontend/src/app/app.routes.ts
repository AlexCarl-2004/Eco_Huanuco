import { Routes } from '@angular/router';
import { Login } from './pages/login/login';
import { RegistroContenedorComponent } from './pages/registro-contenedor/registro-contenedor';

export const routes: Routes = [
  { path: 'login', component: Login },
  { path: 'registro-contenedor', component: RegistroContenedorComponent },
  { path: '', redirectTo: '/login', pathMatch: 'full' }
];