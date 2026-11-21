"""
Configuración de Django para EcoHuánuco AI.

Todos los valores sensibles o que cambian entre entornos se leen del archivo
`.env` (ver `.env.example`). Si no existe `.env`, se usan valores seguros para
desarrollo local con SQLite.
"""

import os
import sys
from pathlib import Path

from django.templatetags.static import static
from django.urls import reverse_lazy
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "si", "sí"}


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


# --------------------------------------------------------------------------- #
# Seguridad
# --------------------------------------------------------------------------- #
SECRET_KEY = os.getenv(
    "DJANGO_SECRET_KEY",
    "django-insecure-solo-para-desarrollo-cambiar-en-produccion",
)
DEBUG = env_bool("DJANGO_DEBUG", True)
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")


# --------------------------------------------------------------------------- #
# Aplicaciones
# --------------------------------------------------------------------------- #
INSTALLED_APPS = [
    # Tema moderno para el panel de administración (debe ir antes de admin)
    "unfold",
    "unfold.contrib.filters",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Terceros
    "rest_framework",
    "django_filters",
    "corsheaders",
    "drf_spectacular",
    "drf_spectacular_sidecar",  # Swagger UI y ReDoc servidos localmente (funciona sin internet)
    # Proyecto
    "api",
    "monitoreo",
    "rutas",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "ecohuanuco.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "ecohuanuco.wsgi.application"


# --------------------------------------------------------------------------- #
# Base de datos (ECO-2)
#   DB_ENGINE=sqlite  -> archivo local db.sqlite3 (por defecto, no requiere nada)
#   DB_ENGINE=mysql   -> MySQL 8 (requiere `pip install -r requirements-mysql.txt`)
# --------------------------------------------------------------------------- #
DB_ENGINE = os.getenv("DB_ENGINE", "sqlite").lower()

if DB_ENGINE == "mysql":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.mysql",
            "NAME": os.getenv("DB_NAME", "ecohuanuco"),
            "USER": os.getenv("DB_USER", "ecohuanuco"),
            "PASSWORD": os.getenv("DB_PASSWORD", ""),
            "HOST": os.getenv("DB_HOST", "127.0.0.1"),
            "PORT": os.getenv("DB_PORT", "3306"),
            "OPTIONS": {
                "charset": "utf8mb4",
                "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
            },
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
            # WAL + espera: permite que el servidor web y el worker MQTT escriban sin bloquearse
            "OPTIONS": {
                "timeout": 20,
                "transaction_mode": "IMMEDIATE",
                "init_command": "PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;",
            },
        }
    }

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# --------------------------------------------------------------------------- #
# Contraseñas
# --------------------------------------------------------------------------- #
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# --------------------------------------------------------------------------- #
# Idioma y zona horaria (Huánuco, Perú)
# --------------------------------------------------------------------------- #
LANGUAGE_CODE = "es-pe"
TIME_ZONE = "America/Lima"
USE_I18N = True
USE_TZ = True


# --------------------------------------------------------------------------- #
# Archivos estáticos
# --------------------------------------------------------------------------- #
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]


# --------------------------------------------------------------------------- #
# CORS: permite que el Frontend Angular consuma la API
# --------------------------------------------------------------------------- #
CORS_ALLOWED_ORIGINS = env_list(
    "CORS_ALLOWED_ORIGINS", "http://localhost:4200,http://127.0.0.1:4200"
)


# --------------------------------------------------------------------------- #
# Django REST Framework
# --------------------------------------------------------------------------- #
REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 25,
    # En desarrollo la API es abierta para facilitar la integración con Angular.
    # Cuando exista el login (sprint siguiente) se cambiará a IsAuthenticated.
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticatedOrReadOnly"
        if env_bool("API_REQUIERE_LOGIN", False)
        else "rest_framework.permissions.AllowAny"
    ],
    "DATETIME_FORMAT": "iso-8601",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "EcoHuánuco AI · API",
    "DESCRIPTION": (
        "API REST de la plataforma de gestión inteligente de residuos sólidos de Huánuco. "
        "Incluye el registro de contenedores y dispositivos IoT, la telemetría de llenado "
        "y la generación de itinerarios de recolección optimizados."
    ),
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SWAGGER_UI_DIST": "SIDECAR",
    "SWAGGER_UI_FAVICON_HREF": "SIDECAR",
    "REDOC_DIST": "SIDECAR",
    "COMPONENT_SPLIT_REQUEST": True,
    "ENUM_NAME_OVERRIDES": {
        "EstadoContenedorEnum": "monitoreo.models.Contenedor.Estado",
        "EstadoPlanEnum": "rutas.models.PlanRecoleccion.Estado",
    },
    "TAGS": [
        {"name": "Contenedores", "description": "Registro y estado de contenedores (ECO-3)"},
        {"name": "Dispositivos", "description": "Sensores IoT asociados a contenedores (ECO-3)"},
        {"name": "Telemetría", "description": "Lecturas de nivel de llenado (ECO-6)"},
        {"name": "Red vial", "description": "Nodos, tramos y sentidos viales (ECO-9)"},
        {"name": "Vehículos", "description": "Flota de recolección (ECO-9)"},
        {"name": "Itinerarios", "description": "Generación de rutas optimizadas (ECO-10, ECO-12)"},
        {"name": "Sistema", "description": "Estado del servicio"},
    ],
    "SWAGGER_UI_SETTINGS": {
        "deepLinking": True,
        "persistAuthorization": True,
        "displayRequestDuration": True,
        "filter": True,
        "docExpansion": "none",
    },
}


# --------------------------------------------------------------------------- #
# MQTT / IoT (ECO-5, ECO-6)
# --------------------------------------------------------------------------- #
MQTT = {
    "HOST": os.getenv("MQTT_HOST", "localhost"),
    "PORT": int(os.getenv("MQTT_PORT", "1883")),
    "USER": os.getenv("MQTT_USER", ""),
    "PASSWORD": os.getenv("MQTT_PASSWORD", ""),
    "CLIENT_ID": os.getenv("MQTT_CLIENT_ID", "ecohuanuco-backend-worker"),
    "TOPIC_PREFIX": os.getenv("MQTT_TOPIC_PREFIX", "ecohuanuco/v1"),
    "QOS": int(os.getenv("MQTT_QOS", "1")),
}

# Minutos sin reportar a partir de los cuales un dispositivo se considera fuera de línea
DISPOSITIVO_TIMEOUT_MIN = int(os.getenv("DISPOSITIVO_TIMEOUT_MIN", "30"))


# --------------------------------------------------------------------------- #
# Optimización de rutas (ECO-9, ECO-10, ECO-12)
# --------------------------------------------------------------------------- #
RUTAS = {
    # Nivel de llenado (%) a partir del cual un contenedor entra al itinerario
    "UMBRAL_LLENADO_PCT": float(os.getenv("RUTAS_UMBRAL_PCT", "75")),
    # Tiempo de servicio por contenedor (minutos) para estimar la duración
    "TIEMPO_SERVICIO_MIN": float(os.getenv("RUTAS_TIEMPO_SERVICIO_MIN", "3")),
    # Factor para convertir distancia en línea recta a distancia por calles,
    # usado sólo cuando no hay tramos viales cargados
    "FACTOR_TORTUOSIDAD": float(os.getenv("RUTAS_FACTOR_TORTUOSIDAD", "1.3")),
}


# --------------------------------------------------------------------------- #
# Panel de administración (tema Unfold)
# --------------------------------------------------------------------------- #
UNFOLD = {
    "SITE_TITLE": "EcoHuánuco AI",
    "SITE_HEADER": "EcoHuánuco AI",
    "SITE_SUBHEADER": "Gestión inteligente de residuos",
    "SITE_URL": "/api/docs/",
    "SITE_SYMBOL": "recycling",
    "SITE_FAVICONS": [
        {"rel": "icon", "type": "image/svg+xml", "href": lambda request: static("img/logo.svg")},
    ],
    "SHOW_HISTORY": True,
    "SHOW_VIEW_ON_SITE": False,
    "ENVIRONMENT": "ecohuanuco.admin_dashboard.entorno",
    "DASHBOARD_CALLBACK": "ecohuanuco.admin_dashboard.dashboard_callback",
    "STYLES": [lambda request: static("css/admin.css")],
    "COLORS": {
        # Verde "eco" como color principal
        "primary": {
            "50": "oklch(97.9% .021 166.113)",
            "100": "oklch(95% .052 163.051)",
            "200": "oklch(90.5% .093 164.15)",
            "300": "oklch(84.5% .143 164.978)",
            "400": "oklch(76.5% .177 163.223)",
            "500": "oklch(69.6% .17 162.48)",
            "600": "oklch(59.6% .145 163.225)",
            "700": "oklch(50.8% .118 165.612)",
            "800": "oklch(43.2% .095 166.913)",
            "900": "oklch(37.8% .077 168.94)",
            "950": "oklch(26.2% .051 172.552)",
        },
    },
    "SIDEBAR": {
        "show_search": True,
        "show_all_applications": False,
        "navigation": [
            {
                "title": "Inicio",
                "items": [
                    {"title": "Panel general", "icon": "space_dashboard", "link": reverse_lazy("admin:index")},
                    {"title": "Documentación API", "icon": "api", "link": "/api/docs/"},
                ],
            },
            {
                "title": "Monitoreo IoT",
                "items": [
                    {"title": "Contenedores", "icon": "delete", "link": reverse_lazy("admin:monitoreo_contenedor_changelist")},
                    {"title": "Dispositivos", "icon": "sensors", "link": reverse_lazy("admin:monitoreo_dispositivo_changelist")},
                    {"title": "Lecturas", "icon": "monitoring", "link": reverse_lazy("admin:monitoreo_lectura_changelist")},
                ],
            },
            {
                "title": "Rutas de recolección",
                "items": [
                    {"title": "Planes de recolección", "icon": "route", "link": reverse_lazy("admin:rutas_planrecoleccion_changelist")},
                    {"title": "Vehículos", "icon": "local_shipping", "link": reverse_lazy("admin:rutas_vehiculo_changelist")},
                    {"title": "Nodos viales", "icon": "location_on", "link": reverse_lazy("admin:rutas_nodo_changelist")},
                    {"title": "Tramos viales", "icon": "alt_route", "link": reverse_lazy("admin:rutas_tramo_changelist")},
                ],
            },
            {
                "title": "Seguridad",
                "items": [
                    {"title": "Usuarios", "icon": "person", "link": reverse_lazy("admin:auth_user_changelist")},
                    {"title": "Grupos", "icon": "group", "link": reverse_lazy("admin:auth_group_changelist")},
                ],
            },
        ],
    },
}


# --------------------------------------------------------------------------- #
# Logs
# --------------------------------------------------------------------------- #
EJECUTANDO_TESTS = len(sys.argv) > 1 and sys.argv[1] == "test"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {"format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s", "datefmt": "%H:%M:%S"},
    },
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "simple"}},
    "loggers": {
        "monitoreo": {"handlers": ["console"], "level": "ERROR" if EJECUTANDO_TESTS else "INFO"},
        "rutas": {"handlers": ["console"], "level": "ERROR" if EJECUTANDO_TESTS else "INFO"},
    },
}
