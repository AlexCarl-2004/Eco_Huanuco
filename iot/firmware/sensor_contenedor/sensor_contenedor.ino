/*
 * =====================================================================
 *  EcoHuánuco AI · Firmware del sensor de llenado (ESP32 + JSN-SR04T)
 * =====================================================================
 *  Ciclo de trabajo:
 *    1. Despierta del deep sleep
 *    2. Mide la distancia N veces y toma la MEDIANA (descarta ecos falsos)
 *    3. Se conecta a WiFi y al broker MQTT
 *    4. Publica la lectura en ecohuanuco/v1/contenedores/<ID>/telemetria (QoS 1)
 *    5. Lee la configuración retenida (intervalo, muestras) y vuelve a dormir
 *
 *  Librerías (Gestor de librerías del Arduino IDE):
 *    - PubSubClient  (Nick O'Leary)   ≥ 2.8
 *    - ArduinoJson   (Benoit Blanchon) ≥ 7.0
 *  Placa: "ESP32 Dev Module" (paquete esp32 de Espressif ≥ 3.0)
 *
 *  Contrato de tópicos y payload: iot/broker/TOPICOS.md
 * =====================================================================
 */

#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <time.h>
#include "config.h"

#define FW_VERSION "1.0.0"
#define PREFIJO    "ecohuanuco/v1/contenedores/"

// Sobreviven al deep sleep (memoria RTC)
RTC_DATA_ATTR uint32_t intervaloS = INTERVALO_DEFECTO_S;
RTC_DATA_ATTR uint8_t  muestras   = MUESTRAS_DEFECTO;
RTC_DATA_ATTR uint32_t arranques  = 0;

WiFiClient wifi;
PubSubClient mqtt(wifi);

String topicoTelemetria = String(PREFIJO) + DEVICE_ID + "/telemetria";
String topicoEstado     = String(PREFIJO) + DEVICE_ID + "/estado";
String topicoConfig     = String(PREFIJO) + DEVICE_ID + "/config";

// ---------------------------------------------------------------------
// Medición ultrasónica
// ---------------------------------------------------------------------

// Velocidad del sonido en cm/µs según la temperatura del aire
float velocidadSonido(float tempC) {
  return (331.3f + 0.606f * tempC) / 10000.0f;
}

// Una medición; devuelve -1 si no hubo eco o está fuera de rango
float medirUnaVez(float tempC) {
  digitalWrite(PIN_TRIG, LOW);
  delayMicroseconds(4);
  digitalWrite(PIN_TRIG, HIGH);
  delayMicroseconds(20);           // el JSN-SR04T necesita un pulso ≥ 10 µs
  digitalWrite(PIN_TRIG, LOW);

  unsigned long duracion = pulseIn(PIN_ECHO, HIGH, 30000UL);  // máx. ~5 m
  if (duracion == 0) return -1;

  float distancia = duracion * velocidadSonido(tempC) / 2.0f;
  if (distancia < DISTANCIA_MIN_CM || distancia > DISTANCIA_MAX_CM) return -1;
  return distancia;
}

// Mediana de varias mediciones válidas (robusta ante ecos en las paredes)
float medirDistancia(float tempC, uint8_t n) {
  float valores[15];
  uint8_t validas = 0;
  n = constrain(n, 3, 15);
  for (uint8_t i = 0; i < n; i++) {
    float d = medirUnaVez(tempC);
    if (d > 0) valores[validas++] = d;
    delay(70);                     // deja disipar el eco anterior
  }
  if (validas == 0) return -1;

  // Ordenamiento por inserción (n pequeño)
  for (uint8_t i = 1; i < validas; i++) {
    float x = valores[i];
    int8_t j = i - 1;
    while (j >= 0 && valores[j] > x) { valores[j + 1] = valores[j]; j--; }
    valores[j + 1] = x;
  }
  return (validas % 2) ? valores[validas / 2]
                       : (valores[validas / 2 - 1] + valores[validas / 2]) / 2.0f;
}

int leerBateria() {
  // Divisor 1:2 → 4.2 V llena = 2.1 V en el pin; 3.3 V vacía = 1.65 V
  uint32_t mv = analogReadMilliVolts(PIN_BATERIA) * 2;
  return constrain(map(mv, 3300, 4200, 0, 100), 0, 100);
}

// ---------------------------------------------------------------------
// Conectividad
// ---------------------------------------------------------------------
bool conectarWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  unsigned long inicio = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - inicio < 15000) delay(200);
  return WiFi.status() == WL_CONNECTED;
}

void sincronizarHora() {
  configTime(0, 0, "pool.ntp.org", "time.google.com");  // UTC; el backend convierte a hora de Lima
  struct tm t;
  getLocalTime(&t, 5000);
}

void alRecibir(char* topico, byte* payload, unsigned int largo) {
  if (topicoConfig != topico) return;
  JsonDocument cfg;
  if (deserializeJson(cfg, payload, largo)) return;
  if (cfg["intervalo_s"].is<uint32_t>()) intervaloS = constrain(cfg["intervalo_s"].as<uint32_t>(), 60, 86400);
  if (cfg["muestras"].is<uint8_t>())     muestras   = constrain(cfg["muestras"].as<uint8_t>(), 3, 15);
  Serial.printf("Configuración recibida: intervalo=%us muestras=%u\n", intervaloS, muestras);
}

bool conectarMQTT() {
  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setBufferSize(512);
  mqtt.setCallback(alRecibir);
  // Last Will: si el equipo se cae, el broker publica "offline" por él
  bool ok = mqtt.connect(DEVICE_ID, MQTT_USER, MQTT_PASSWORD,
                         topicoEstado.c_str(), 1, true, "offline");
  if (ok) {
    mqtt.publish(topicoEstado.c_str(), "online", true);
    mqtt.subscribe(topicoConfig.c_str(), 1);
  }
  return ok;
}

void dormir() {
  Serial.printf("Durmiendo %u s…\n", intervaloS);
  Serial.flush();
  mqtt.disconnect();
  WiFi.disconnect(true);
  esp_sleep_enable_timer_wakeup((uint64_t)intervaloS * 1000000ULL);
  esp_deep_sleep_start();
}

// ---------------------------------------------------------------------
void setup() {
  Serial.begin(115200);
  delay(100);
  arranques++;
  pinMode(PIN_TRIG, OUTPUT);
  pinMode(PIN_ECHO, INPUT);
  Serial.printf("\nEcoHuánuco %s · %s · arranque #%u\n", FW_VERSION, DEVICE_ID, arranques);

  // 1. Medir ANTES de encender el WiFi (menos ruido eléctrico y menos consumo)
  float temperatura = TEMPERATURA_DEFECTO_C;
  float distancia = medirDistancia(temperatura, muestras);
  int bateria = leerBateria();
  Serial.printf("Distancia: %.1f cm · batería: %d %%\n", distancia, bateria);

  if (distancia < 0) {
    Serial.println("Sin lectura válida (¿sensor desconectado u obstruido?)");
    dormir();
  }

  // 2. Conectar y publicar
  if (!conectarWiFi()) { Serial.println("WiFi no disponible"); dormir(); }
  sincronizarHora();
  if (!conectarMQTT()) { Serial.printf("MQTT falló (estado %d)\n", mqtt.state()); dormir(); }

  JsonDocument doc;
  doc["device_id"]    = DEVICE_ID;
  doc["ts"]           = (uint32_t)time(nullptr);
  doc["distancia_cm"] = roundf(distancia * 10) / 10.0f;
  doc["temp_c"]       = temperatura;
  doc["bateria"]      = bateria;
  doc["rssi"]         = WiFi.RSSI();
  doc["fw"]           = FW_VERSION;

  char cuerpo[256];
  size_t n = serializeJson(doc, cuerpo);
  bool enviado = mqtt.publish(topicoTelemetria.c_str(), (const uint8_t*)cuerpo, n, false);
  Serial.printf("%s %s\n", enviado ? "Publicado:" : "Error al publicar:", cuerpo);

  // 3. Dar tiempo a recibir la configuración retenida y a vaciar el buffer
  unsigned long inicio = millis();
  while (millis() - inicio < 1500) { mqtt.loop(); delay(10); }

  dormir();
}

void loop() {
  // No se usa: el equipo duerme entre lecturas para ahorrar batería
}
