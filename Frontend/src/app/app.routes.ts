import { Routes } from '@angular/router';
import { Login } from './pages/login/login'; 
import { DashboardComponent } from './pages/dashboard/dashboard'; 
import { RegistroContenedorComponent } from './pages/registro-contenedor/registro-contenedor'; 

export const routes: Routes = [
  { path: '', redirectTo: 'login', pathMatch: 'full' },
  { path: 'login', component: Login },
  { path: 'dashboard', component: DashboardComponent },
  { path: 'registro-contenedor', component: RegistroContenedorComponent },
  { path: '**', redirectTo: 'login' }
];