# 🌱 EcoHuánuco AI

Plataforma web con IoT para la **gestión inteligente de residuos sólidos** en Huánuco, Perú.
Proyecto académico de la **Universidad de Huánuco**, gestionado con **Scrum** en Jira.

> ⚠️ **Estado:** en desarrollo inicial. Ya está la arquitectura base de Frontend y Backend; las funcionalidades se irán agregando por sprints.

---

## 📋 Tabla de contenido

- [Descripción](#-descripción)
- [Tecnologías](#-tecnologías)
- [Estructura del proyecto](#-estructura-del-proyecto)
- [Requisitos previos](#-requisitos-previos)
- [Instalación](#-instalación)
- [Ejecución](#-ejecución)
- [Pruebas](#-pruebas)
- [Hoja de ruta](#-hoja-de-ruta)
- [Flujo de trabajo con Git](#-flujo-de-trabajo-con-git)
- [Autores](#-autores)

---

## 📖 Descripción

EcoHuánuco AI busca monitorear los contenedores de residuos de la ciudad. Los sensores IoT medirán su nivel de llenado y una plataforma web permitirá:

- Ver en tiempo real el estado de los contenedores.
- Recibir alertas cuando un contenedor esté por llenarse.
- Optimizar las rutas de recolección.
- Consultar reportes e historial de lecturas.

---

## 🛠 Tecnologías

| Capa | Tecnología | Versión |
|---|---|---|
| Frontend | Angular (componentes standalone) | 21.2 |
| Lenguaje Frontend | TypeScript | 5.9 |
| Pruebas Frontend | Vitest + jsdom | 4.0 |
| Formato de código | Prettier | 3.8 |
| Backend | Django | 6.1.3 |
| API REST | Django REST Framework | 3.18.3 |
| Base de datos (desarrollo) | SQLite | — |
| IoT | *Por definir* | — |
| Gestión del proyecto | Jira (Scrum) | — |

---

## 📁 Estructura del proyecto

```
Eco_Huanuco/
├── Backend/                  # API REST con Django + DRF
│   ├── ecohuanuco/           # Configuración del proyecto Django
│   │   ├── settings.py
│   │   ├── urls.py
│   │   ├── asgi.py
│   │   └── wsgi.py
│   ├── api/                  # App principal (modelos, vistas, serializers)
│   │   ├── migrations/
│   │   ├── models.py
│   │   ├── views.py
│   │   ├── admin.py
│   │   └── tests.py
│   ├── manage.py
│   └── requirements.txt
│
├── Frontend/                 # Aplicación web con Angular
│   ├── public/
│   ├── src/
│   │   ├── app/
│   │   │   ├── pages/
│   │   │   │   ├── login/       # Pantalla de inicio de sesión
│   │   │   │   └── dashboard/   # Panel principal
│   │   │   ├── app.routes.ts
│   │   │   ├── app.config.ts
│   │   │   └── app.ts
│   │   ├── index.html
│   │   ├── main.ts
│   │   └── styles.css
│   ├── angular.json
│   └── package.json
│
├── DataBase/                 # Scripts y modelo de la base de datos
├── iot/                      # Código de los sensores / microcontroladores
├── .gitignore
└── README.md
```

---

## ✅ Requisitos previos

- [Git](https://git-scm.com/)
- [Python 3.12+](https://www.python.org/downloads/)
- [Node.js 22+](https://nodejs.org/) y npm 11
- Angular CLI (opcional, también se puede usar con `npx`):
  ```bash
  npm install -g @angular/cli
  ```

---

## ⚙️ Instalación

### 1. Clonar el repositorio

```bash
git clone https://github.com/AlexCarl-2004/Eco_Huanuco.git
cd Eco_Huanuco
```

### 2. Backend (Django)

```bash
cd Backend

# Crear el entorno virtual
python -m venv venv

# Activarlo
# Windows (PowerShell)
venv\Scripts\Activate.ps1
# Windows (CMD)
venv\Scripts\activate.bat
# Linux / macOS
source venv/bin/activate

# Instalar dependencias
pip install -r requirements.txt

# Crear las tablas de la base de datos
python manage.py migrate

# (Opcional) Crear un usuario administrador
python manage.py createsuperuser
```

### 3. Frontend (Angular)

```bash
cd Frontend
npm install
```

---

## ▶️ Ejecución

Abre **dos terminales**, una para cada servidor.

**Terminal 1: Backend**

```bash
cd Backend
venv\Scripts\Activate.ps1      # o: source venv/bin/activate
python manage.py runserver
```

La API queda en 👉 http://localhost:8000
y el panel de administración en 👉 http://localhost:8000/admin/

**Terminal 2: Frontend**

```bash
cd Frontend
npm start
```

La aplicación queda en 👉 http://localhost:4200

---

## 🧪 Pruebas

```bash
# Backend
cd Backend
python manage.py test

# Frontend
cd Frontend
npm test
```

---

## 🗺 Hoja de ruta

- [x] Arquitectura inicial: Frontend (Angular) y Backend (Django + DRF)
- [x] Carpetas base para `DataBase/` e `iot/`
- [x] Componentes iniciales de Login y Dashboard
- [ ] Configurar CORS entre Angular y Django
- [ ] Modelos de datos: contenedores, sensores, lecturas, rutas y alertas
- [ ] Endpoints REST con serializers y viewsets
- [ ] Autenticación de usuarios (login)
- [ ] Dashboard con el estado de los contenedores en tiempo real
- [ ] Integración con los sensores IoT
- [ ] Sistema de alertas por nivel de llenado
- [ ] Optimización de rutas de recolección
- [ ] Reportes e historial
- [ ] Migración a una base de datos de producción
- [ ] Despliegue

---

## 🔀 Flujo de trabajo con Git

1. Crea una rama a partir de `main` usando la clave de la historia en Jira:
   ```bash
   git checkout -b feature/ECO-12-login
   ```
2. Haz commits pequeños y con mensajes claros:
   ```bash
   git commit -m "ECO-12: formulario de inicio de sesión"
   ```
3. Sube la rama y abre un **Pull Request** hacia `main`.
4. Después de la revisión, haz el merge.

> 💡 No subas `node_modules/`, `venv/`, `db.sqlite3` ni `__pycache__/`; ya están en `.gitignore`.

---

## 👥 Autores

| Nombre | Rol | Contacto |
|---|---|---|
| Alexis Cárdenas | Desarrollador | [@AlexCarl-2004](https://github.com/AlexCarl-2004) |
| *Agregar integrante* | *Rol Scrum* | — |

---

<p align="center">
  Universidad de Huánuco · 2026
</p>
