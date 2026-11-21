// =====================================================================
// Copie este archivo como "config.h" y complete sus datos.
// config.h está en .gitignore para no subir contraseñas a GitHub.
// =====================================================================
#pragma once

// --- Identidad del equipo (debe existir en la plataforma) ---
#define DEVICE_ID        "ESP32-0001"

// --- WiFi ---
#define WIFI_SSID        "MiRedWiFi"
#define WIFI_PASSWORD    "clave-wifi"

// --- Broker MQTT (Mosquitto) ---
#define MQTT_HOST        "192.168.1.50"   // IP de la PC/servidor con Mosquitto
#define MQTT_PORT        1883
#define MQTT_USER        DEVICE_ID          // en producción: usuario = device_id
#define MQTT_PASSWORD    ""                 // vacío en desarrollo (allow_anonymous)

// --- Pines (ESP32 DevKit v1) ---
#define PIN_TRIG         5
#define PIN_ECHO         18                 // usar divisor 5V→3.3V si el sensor trabaja a 5V
#define PIN_BATERIA      34                 // ADC con divisor 100k/100k desde la batería

// --- Medición ---
#define MUESTRAS_DEFECTO      7             // se usa la mediana
#define INTERVALO_DEFECTO_S   900           // 15 min entre lecturas (deep sleep)
#define TEMPERATURA_DEFECTO_C 22.0          // Huánuco: ~22 °C de media; ajustar si hay sensor de temperatura
#define DISTANCIA_MIN_CM      20.0          // zona ciega del JSN-SR04T
#define DISTANCIA_MAX_CM      450.0
