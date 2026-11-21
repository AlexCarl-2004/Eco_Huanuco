# 📏 Protocolo de calibración ultrasónica en campo (ECO-8 · T-107)

Objetivo: comprobar que cada sensor mide la distancia con la exactitud necesaria para estimar
el nivel de llenado y obtener sus **coeficientes de corrección** (factor de escala y offset),
que la plataforma aplica automáticamente a cada lectura.

## 1. Materiales

- Sensor instalado en su soporte definitivo (tapa del contenedor), con el firmware cargado.
- Wincha metálica de 3 m (resolución de 1 mm).
- Superficie plana de cartón o tecnopor de 40 × 40 cm, como blanco.
- Termómetro ambiental.
- Laptop con el **Monitor Serie** del Arduino IDE (115200 baudios) o el panel de lecturas.
- Plantilla `datos_ejemplo.csv` (como formato) y una hoja de registro.

## 2. Preparación

1. Dejar el equipo encendido **5 minutos** antes de medir, para que se estabilice.
2. Anotar la temperatura ambiente. La velocidad del sonido cambia alrededor de 0,6 m/s por °C.
3. Verificar que no haya objetos dentro del cono de emisión del sensor (unos 75°) que
   produzcan ecos falsos: paredes del contenedor, cables, bolsas colgando.
4. Medir con la wincha desde la **cara frontal del transductor**, no desde la carcasa.

## 3. Procedimiento

1. Colocar el blanco perpendicular al eje del sensor en cada distancia de referencia:
   **25, 40, 60, 80, 100 y 120 cm**. Cubren todo el rango de un contenedor de 1100 L; 25 cm
   está justo por encima de la zona ciega del JSN-SR04T (unos 20 cm).
2. En cada distancia tomar **5 lecturas** separadas por al menos 2 segundos.
3. Si el sensor no devuelve eco, registrar la celda **vacía**. No repetir la medición para
   "completar": la tasa de lecturas fallidas también se evalúa.
4. Repetir con el sensor **dentro del contenedor real**, con bolsas de residuos como blanco,
   en al menos 3 niveles (vacío, mitad, casi lleno). Esto valida el efecto de las paredes y de
   superficies irregulares.
5. Registrar todo en un CSV con estas columnas:

```csv
device_id,distancia_real_cm,distancia_medida_cm,temperatura_c,repeticion
ESP32-0001,25,26.1,21.5,1
ESP32-0001,25,,21.5,2        ← lectura sin eco
```

## 4. Cálculo de coeficientes

```bash
cd iot/calibracion
python calibrar.py mediciones_campo.csv --salida reportes/
```

El script ajusta por **mínimos cuadrados** la recta

$$
\text{distancia}_{\text{real}} = \text{factor\_escala} \times \text{distancia}_{\text{medida}} + \text{offset}
$$

y genera `reporte_calibracion.html` (con gráficos) y `resultados_calibracion.csv`.

## 5. Criterios de aceptación

Un sensor se **aprueba** sólo si cumple **todos** los criterios después de aplicar la corrección:

| # | Criterio | Umbral | Justificación |
|---|---|---|---|
| C1 | Error absoluto máximo | ≤ 2,0 cm | En un contenedor de 120 cm equivale a ±1,7 % de nivel. Es suficiente para decidir con el umbral del 75 % |
| C2 | Error absoluto medio (MAE) | ≤ 1,0 cm | Exactitud promedio del sensor ya corregido |
| C3 | Repetibilidad (σ por punto) | ≤ 1,0 cm | Lecturas estables: la mediana del firmware filtra el ruido puntual |
| C4 | Linealidad (R²) | ≥ 0,995 | La corrección lineal es válida en todo el rango |
| C5 | Lecturas válidas | ≥ 95 % | Un sensor que pierde ecos deja al contenedor sin datos |
| C6 | Cobertura | ≥ 4 distancias | La recta se ajusta con puntos de todo el rango |
| — | Factor de escala | entre 0,5 y 1,5 | Un valor fuera de rango indica un sensor dañado o mal montado |

Si un sensor es **rechazado**:

1. Revisar el montaje (perpendicularidad, obstrucciones, humedad en el transductor).
2. Repetir el procedimiento completo.
3. Si vuelve a fallar, reemplazar el sensor y registrar el número de serie en la incidencia.

## 6. Aplicar los coeficientes en la plataforma

Opción A, automática (sólo se aplican los sensores aprobados):

```bash
python calibrar.py mediciones_campo.csv --aplicar http://localhost:8000
```

Opción B, manual: en el panel `/admin` → **Dispositivos** → sección *Calibración*, o con la API:

```http
POST /api/dispositivos/ESP32-0001/calibracion/
Content-Type: application/json

{ "factor_escala": 1.0155, "offset_cm": -1.18 }
```

Desde ese momento, cada lectura nueva guarda la distancia cruda y la corregida, y el nivel
se calcula con la corregida.

## 7. Verificación posterior

Una semana después de instalar el sensor, comparar su nivel con una medición manual en
3 visitas del camión. La diferencia debe ser **≤ 5 %** de nivel. Si no, volver a calibrar.

## 8. Registro

Guardar en la carpeta del sprint:

- el CSV de mediciones de campo,
- `reporte_calibracion.html` y `resultados_calibracion.csv`,
- fotos del montaje de cada sensor.
