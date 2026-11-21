#!/usr/bin/env sh
# Crea el archivo de contraseñas para mosquitto.prod.conf.
# Uso (con Docker):  docker compose exec mosquitto sh /mosquitto/config/crear_usuarios.sh
# Uso (Linux):       sh crear_usuarios.sh   (requiere mosquitto_passwd)
set -e
ARCHIVO="${PASSWD_FILE:-/mosquitto/config/passwd}"

echo "Contraseña para el usuario 'backend':"
mosquitto_passwd -c "$ARCHIVO" backend
echo "Contraseña para el usuario 'panel':"
mosquitto_passwd "$ARCHIVO" panel

# Un usuario por dispositivo (agregue más según se instalen)
for ID in ESP32-0001 ESP32-0002 ESP32-0003; do
  echo "Contraseña para el dispositivo $ID:"
  mosquitto_passwd "$ARCHIVO" "$ID"
done
chmod 0700 "$ARCHIVO"
echo "Listo: $ARCHIVO"
