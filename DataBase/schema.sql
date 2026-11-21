-- =====================================================================
--  EcoHuánuco AI · Esquema de base de datos para MySQL 8.x
--  ECO-2 (T-101) contenedores, dispositivos y lecturas
--  ECO-9 (T-201) red vial, vehículos e itinerarios
-- ---------------------------------------------------------------------
--  Este script documenta el diseño y permite crear la base sin Django.
--  En el día a día las tablas las crea Django con:  python manage.py migrate
--  (los nombres de tablas y columnas son los mismos).
-- =====================================================================

CREATE DATABASE IF NOT EXISTS ecohuanuco
  CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
USE ecohuanuco;

SET time_zone = '+00:00';  -- las fechas se guardan en UTC; Django las muestra en hora de Lima

-- ---------------------------------------------------------------------
-- 1. MONITOREO IoT
-- ---------------------------------------------------------------------

-- Punto físico de acopio de residuos
CREATE TABLE monitoreo_contenedor (
  id                BIGINT       NOT NULL AUTO_INCREMENT,
  codigo            VARCHAR(20)  NOT NULL COMMENT 'Ej.: CNT-001',
  nombre            VARCHAR(120) NOT NULL COMMENT 'Referencia del lugar',
  direccion         VARCHAR(200) NOT NULL DEFAULT '',
  sector            VARCHAR(80)  NOT NULL DEFAULT '' COMMENT 'Huánuco, Amarilis, Pillco Marca…',
  latitud           DECIMAL(9,6) NOT NULL,
  longitud          DECIMAL(9,6) NOT NULL,
  tipo_residuo      VARCHAR(20)  NOT NULL DEFAULT 'general'
                    COMMENT 'general | organico | reciclable | peligroso',
  capacidad_litros  INT UNSIGNED NOT NULL DEFAULT 1100,
  altura_util_cm    DOUBLE       NOT NULL DEFAULT 120 COMMENT 'Distancia sensor → fondo vacío',
  estado            VARCHAR(20)  NOT NULL DEFAULT 'activo'
                    COMMENT 'activo | mantenimiento | inactivo',
  nivel_actual_pct  DOUBLE       NULL     COMMENT 'Copia de la última lectura (consulta rápida)',
  ultima_lectura_en DATETIME(6)  NULL,
  creado_en         DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  actualizado_en    DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  UNIQUE KEY uq_contenedor_codigo (codigo),
  KEY idx_cont_estado_nivel (estado, nivel_actual_pct),
  CONSTRAINT ck_cont_lat   CHECK (latitud BETWEEN -90 AND 90),
  CONSTRAINT ck_cont_lon   CHECK (longitud BETWEEN -180 AND 180),
  CONSTRAINT ck_cont_cap   CHECK (capacidad_litros >= 1),
  CONSTRAINT ck_cont_alt   CHECK (altura_util_cm >= 1),
  CONSTRAINT ck_cont_nivel CHECK (nivel_actual_pct IS NULL OR nivel_actual_pct BETWEEN 0 AND 100)
) ENGINE=InnoDB COMMENT='Contenedores de residuos sólidos';

-- Nodo IoT (ESP32 + sensor ultrasónico) instalado en un contenedor
CREATE TABLE monitoreo_dispositivo (
  id              BIGINT        NOT NULL AUTO_INCREMENT,
  device_id       VARCHAR(40)   NOT NULL COMMENT 'Identificador usado en MQTT. Ej.: ESP32-0001',
  contenedor_id   BIGINT        NULL     COMMENT 'Un dispositivo por contenedor como máximo',
  modelo_sensor   VARCHAR(20)   NOT NULL DEFAULT 'JSN-SR04T',
  firmware        VARCHAR(20)   NOT NULL DEFAULT '',
  activo          TINYINT(1)    NOT NULL DEFAULT 1,
  factor_escala   DOUBLE        NOT NULL DEFAULT 1.0 COMMENT 'Calibración ECO-8: pendiente',
  offset_cm       DOUBLE        NOT NULL DEFAULT 0.0 COMMENT 'Calibración ECO-8: intercepto',
  calibrado_en    DATETIME(6)   NULL,
  ultima_conexion DATETIME(6)   NULL,
  bateria_pct     SMALLINT UNSIGNED NULL,
  rssi_dbm        SMALLINT      NULL,
  creado_en       DATETIME(6)   NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  actualizado_en  DATETIME(6)   NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  UNIQUE KEY uq_dispositivo_device_id (device_id),
  UNIQUE KEY uq_dispositivo_contenedor (contenedor_id),
  CONSTRAINT fk_disp_contenedor FOREIGN KEY (contenedor_id)
    REFERENCES monitoreo_contenedor (id) ON DELETE SET NULL,
  CONSTRAINT ck_disp_bateria CHECK (bateria_pct IS NULL OR bateria_pct <= 100),
  CONSTRAINT ck_disp_factor  CHECK (factor_escala BETWEEN 0.5 AND 1.5)
) ENGINE=InnoDB COMMENT='Sensores IoT';

-- Cada medición recibida (por MQTT o HTTP)
CREATE TABLE monitoreo_lectura (
  id                     BIGINT        NOT NULL AUTO_INCREMENT,
  dispositivo_id         BIGINT        NOT NULL,
  contenedor_id          BIGINT        NOT NULL,
  distancia_cm           DOUBLE        NOT NULL COMMENT 'Valor crudo enviado por el sensor',
  distancia_corregida_cm DOUBLE        NOT NULL COMMENT 'Tras aplicar factor y offset',
  nivel_pct              DOUBLE        NOT NULL,
  temperatura_c          DOUBLE        NULL,
  bateria_pct            SMALLINT UNSIGNED NULL,
  rssi_dbm               SMALLINT      NULL,
  medido_en              DATETIME(6)   NOT NULL COMMENT 'Hora de medición del sensor',
  recibido_en            DATETIME(6)   NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  origen                 VARCHAR(12)   NOT NULL DEFAULT 'mqtt' COMMENT 'mqtt | http | simulador',
  payload                JSON          NOT NULL COMMENT 'Mensaje original, para auditoría',
  PRIMARY KEY (id),
  UNIQUE KEY uq_lectura_disp_fecha (dispositivo_id, medido_en) COMMENT 'Evita duplicados QoS 1',
  KEY idx_lect_cont_fecha (contenedor_id, medido_en DESC),
  KEY idx_lect_medido_en (medido_en),
  CONSTRAINT fk_lect_dispositivo FOREIGN KEY (dispositivo_id)
    REFERENCES monitoreo_dispositivo (id) ON DELETE CASCADE,
  CONSTRAINT fk_lect_contenedor FOREIGN KEY (contenedor_id)
    REFERENCES monitoreo_contenedor (id) ON DELETE CASCADE,
  CONSTRAINT ck_lect_nivel CHECK (nivel_pct BETWEEN 0 AND 100)
) ENGINE=InnoDB COMMENT='Telemetría de nivel de llenado';

-- ---------------------------------------------------------------------
-- 2. RED VIAL Y RUTAS
-- ---------------------------------------------------------------------

-- Intersecciones / puntos de la red vial; uno o más son depósitos
CREATE TABLE rutas_nodo (
  id          BIGINT       NOT NULL AUTO_INCREMENT,
  nombre      VARCHAR(120) NOT NULL,
  latitud     DECIMAL(9,6) NOT NULL,
  longitud    DECIMAL(9,6) NOT NULL,
  es_deposito TINYINT(1)   NOT NULL DEFAULT 0,
  PRIMARY KEY (id),
  KEY idx_nodo_deposito (es_deposito)
) ENGINE=InnoDB COMMENT='Nodos del grafo vial';

-- Arcos del grafo. sentido = 'unico' sólo permite ir de origen a destino
CREATE TABLE rutas_tramo (
  id            BIGINT       NOT NULL AUTO_INCREMENT,
  origen_id     BIGINT       NOT NULL,
  destino_id    BIGINT       NOT NULL,
  nombre_via    VARCHAR(120) NOT NULL DEFAULT '',
  distancia_m   DOUBLE       NOT NULL,
  velocidad_kmh DOUBLE       NOT NULL DEFAULT 20,
  sentido       VARCHAR(10)  NOT NULL DEFAULT 'doble' COMMENT 'doble | unico',
  habilitado    TINYINT(1)   NOT NULL DEFAULT 1 COMMENT '0 = vía cerrada',
  PRIMARY KEY (id),
  UNIQUE KEY uq_tramo_origen_destino (origen_id, destino_id),
  KEY idx_tramo_destino (destino_id),
  -- RESTRICT (y no CASCADE): MySQL no permite CHECK sobre columnas con acción referencial
  CONSTRAINT fk_tramo_origen  FOREIGN KEY (origen_id)  REFERENCES rutas_nodo (id) ON DELETE RESTRICT,
  CONSTRAINT fk_tramo_destino FOREIGN KEY (destino_id) REFERENCES rutas_nodo (id) ON DELETE RESTRICT,
  CONSTRAINT ck_tramo_no_bucle  CHECK (origen_id <> destino_id),
  CONSTRAINT ck_tramo_distancia CHECK (distancia_m >= 1),
  CONSTRAINT ck_tramo_velocidad CHECK (velocidad_kmh BETWEEN 1 AND 90)
) ENGINE=InnoDB COMMENT='Tramos viales con sentido de circulación';

CREATE TABLE rutas_vehiculo (
  id               BIGINT       NOT NULL AUTO_INCREMENT,
  placa            VARCHAR(10)  NOT NULL,
  descripcion      VARCHAR(120) NOT NULL DEFAULT '',
  capacidad_litros INT UNSIGNED NOT NULL COMMENT 'Volumen útil por viaje (Q)',
  jornada_max_min  INT UNSIGNED NOT NULL DEFAULT 480 COMMENT 'Tiempo máximo por día (T)',
  activo           TINYINT(1)   NOT NULL DEFAULT 1,
  PRIMARY KEY (id),
  UNIQUE KEY uq_vehiculo_placa (placa),
  CONSTRAINT ck_veh_capacidad CHECK (capacidad_litros >= 100)
) ENGINE=InnoDB COMMENT='Flota de recolección';

-- Resultado de una ejecución del algoritmo de optimización
CREATE TABLE rutas_planrecoleccion (
  id                     BIGINT      NOT NULL AUTO_INCREMENT,
  creado_en              DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  deposito_id            BIGINT      NOT NULL,
  umbral_pct             DOUBLE      NOT NULL COMMENT 'Nivel mínimo para incluir un contenedor (75)',
  algoritmo              VARCHAR(60) NOT NULL,
  estado                 VARCHAR(15) NOT NULL DEFAULT 'planificado'
                         COMMENT 'planificado | en_curso | completado | cancelado',
  contenedores_evaluados INT UNSIGNED NOT NULL DEFAULT 0,
  contenedores_atendidos INT UNSIGNED NOT NULL DEFAULT 0,
  distancia_total_m      DOUBLE      NOT NULL DEFAULT 0,
  distancia_referencia_m DOUBLE      NOT NULL DEFAULT 0 COMMENT 'Solución base (vecino más cercano)',
  duracion_total_min     DOUBLE      NOT NULL DEFAULT 0,
  carga_total_litros     DOUBLE      NOT NULL DEFAULT 0,
  tiempo_calculo_ms      DOUBLE      NOT NULL DEFAULT 0,
  advertencias           JSON        NOT NULL,
  PRIMARY KEY (id),
  KEY idx_plan_deposito (deposito_id),
  CONSTRAINT fk_plan_deposito FOREIGN KEY (deposito_id) REFERENCES rutas_nodo (id) ON DELETE RESTRICT
) ENGINE=InnoDB COMMENT='Planes de recolección generados';

-- Un viaje: depósito → paradas → depósito, realizado por un vehículo
CREATE TABLE rutas_itinerario (
  id           BIGINT            NOT NULL AUTO_INCREMENT,
  plan_id      BIGINT            NOT NULL,
  vehiculo_id  BIGINT            NOT NULL,
  numero_viaje SMALLINT UNSIGNED NOT NULL DEFAULT 1,
  distancia_m  DOUBLE            NOT NULL DEFAULT 0,
  duracion_min DOUBLE            NOT NULL DEFAULT 0,
  carga_litros DOUBLE            NOT NULL DEFAULT 0,
  geometria    JSON              NOT NULL COMMENT '[[lat, lon], …] del recorrido por calles',
  PRIMARY KEY (id),
  KEY idx_itin_plan (plan_id),
  KEY idx_itin_vehiculo (vehiculo_id),
  CONSTRAINT fk_itin_plan     FOREIGN KEY (plan_id)     REFERENCES rutas_planrecoleccion (id) ON DELETE CASCADE,
  CONSTRAINT fk_itin_vehiculo FOREIGN KEY (vehiculo_id) REFERENCES rutas_vehiculo (id) ON DELETE RESTRICT
) ENGINE=InnoDB COMMENT='Viajes de cada plan';

CREATE TABLE rutas_paradaitinerario (
  id                    BIGINT            NOT NULL AUTO_INCREMENT,
  itinerario_id         BIGINT            NOT NULL,
  orden                 SMALLINT UNSIGNED NOT NULL,
  contenedor_id         BIGINT            NOT NULL,
  nivel_pct             DOUBLE            NOT NULL COMMENT 'Nivel al momento de planificar',
  carga_litros          DOUBLE            NOT NULL,
  distancia_acumulada_m DOUBLE            NOT NULL DEFAULT 0,
  llegada_estimada_min  DOUBLE            NOT NULL DEFAULT 0,
  PRIMARY KEY (id),
  UNIQUE KEY uq_parada_orden (itinerario_id, orden),
  KEY idx_parada_contenedor (contenedor_id),
  CONSTRAINT fk_parada_itinerario FOREIGN KEY (itinerario_id) REFERENCES rutas_itinerario (id) ON DELETE CASCADE,
  CONSTRAINT fk_parada_contenedor FOREIGN KEY (contenedor_id) REFERENCES monitoreo_contenedor (id) ON DELETE RESTRICT
) ENGINE=InnoDB COMMENT='Paradas ordenadas de cada viaje';

-- ---------------------------------------------------------------------
-- 3. VISTAS DE APOYO
-- ---------------------------------------------------------------------

-- Contenedores listos para recoger (umbral 75 %), del más lleno al menos lleno
CREATE OR REPLACE VIEW v_contenedores_por_recoger AS
SELECT c.id, c.codigo, c.nombre, c.sector, c.latitud, c.longitud,
       c.capacidad_litros, c.nivel_actual_pct,
       ROUND(c.capacidad_litros * c.nivel_actual_pct / 100, 1) AS litros_estimados,
       d.device_id, c.ultima_lectura_en
FROM monitoreo_contenedor c
LEFT JOIN monitoreo_dispositivo d ON d.contenedor_id = c.id
WHERE c.estado = 'activo' AND c.nivel_actual_pct >= 75
ORDER BY c.nivel_actual_pct DESC;

-- Estado de conexión de los sensores (fuera de línea si no reportan en 30 min)
CREATE OR REPLACE VIEW v_estado_dispositivos AS
SELECT d.device_id, c.codigo AS contenedor, d.bateria_pct, d.rssi_dbm, d.ultima_conexion,
       (d.ultima_conexion >= UTC_TIMESTAMP(6) - INTERVAL 30 MINUTE) AS en_linea
FROM monitoreo_dispositivo d
LEFT JOIN monitoreo_contenedor c ON c.id = d.contenedor_id
WHERE d.activo = 1;
