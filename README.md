<div align="center">
  <img src="icono.svg" width="96" alt="Riksi">
  <h1>Riksi</h1>
  <p><strong>Reconoce la naturaleza del Ecuador, sin conexión.</strong></p>
</div>

---

Apuntas la cámara a un animal o una planta y te dice qué es. Sin cuenta, sin
instalar nada y **sin internet**: el modelo se descarga una vez y a partir de ahí
corre entero dentro del navegador.

*Riksiy*, en kichwa, es reconocer — saber quién es alguien.

## Por qué sin conexión

En Galápagos, en el Yasuní o en el páramo no hay señal. Es exactamente donde
alguien necesita identificar lo que está viendo, y exactamente donde falla
cualquier herramienta que dependa de un servidor. Por eso el modelo va dentro del
dispositivo y no en la nube: no es una restricción técnica, es el punto.

## Cómo funciona

El modelo es pequeño a propósito: **EfficientNet-Lite0, 3,4 millones de
parámetros, 3,8 MB cuantizado a 8 bits**. Se ejecuta con ONNX Runtime Web sobre
WebAssembly, así que va fluido incluso en un teléfono modesto. La página es
estática: no hay backend, no hay coste, no hay nada que se caiga dentro de un
año.

## Estado: v1 entrenada, 100 especies

16.872 fotos, 13.485 de entrenamiento y 3.387 de validación, partidas por
observación. El modelo que corre en la web:

| | int8 | top1 | top3 |
|---|---|---|---|
| **EfficientNet-Lite0 · 288 px · 100 especies** | **3,8 MB** | **79,2%** | **91,5%** |

Las cifras salen de `metricas.json`, que escribe `exportar.py` en cada corrida.

### Lo que se probó para llegar ahí

Mismas 100 especies y mismas imágenes de validación para todos:

| configuración | int8 | top1 | top3 | coste de cuantizar |
|---|---|---|---|---|
| EfficientNet-Lite0 · 320 px | 3,8 MB | 79,6% | 92,3% | 0,2 pts |
| **EfficientNet-Lite0 · 288 px** | **3,8 MB** | **79,2%** | **91,5%** | 0,1 pts |
| EfficientNet-Lite0 · 224 px | 3,8 MB | 75,0% | 89,6% | 0 |
| MobileNetV4-conv-small · 224 px | 2,9 MB | 63,3% | 81,2% | **8,9 pts** |

**La curva se aplana en 288.** De 224 a 288 hay 4,2 puntos; de 288 a 320, solo
0,4, y eso cuesta un 23% más de cómputo. Se publica el de 288: 320 gana dentro
del margen de ruido y se paga en cada foto que alguien haga en el campo.

**Subir la resolución salió gratis en descarga.** Los pesos son los mismos 3,8 MB
a 224 que a 288, porque una CNN no cambia de tamaño con la entrada: solo cuesta
cómputo, un 65% más, que en un teléfono son unos 100 ms en vez de 61. Cuatro
puntos por eso es el mejor cambio de todo el proyecto.

**MobileNetV4 es de 2024 y quedó último**, con 8,9 puntos perdidos al cuantizar.
Repite lo que ya pasó con MobileNetV3: las arquitecturas que buscan precisión en
coma flotante meten capas que el int8 destroza. Cuando el entregable es un modelo
cuantizado, eso pesa más que el año de publicación.

**Promediar la imagen con su espejo no compensa**: +0,2 puntos por duplicar el
tiempo de respuesta, medido sobre 500 imágenes con `comprobar.py --espejo`.

### Cuándo dice "no lo sé"

El umbral no está puesto a ojo. `comprobar.py --calibrar` mide, para cada corte
de confianza, cuántas respuestas se dan y cuántas de esas aciertan, y elige el
corte más bajo que llega al 85%:

| umbral | responde | acierta |
|---|---|---|
| 0,20 | 92% | 82% |
| **0,30** | **82%** | **86%** |
| 0,40 | 71% | 90% |

Bajo es mejor, porque cada punto de umbral de más es un acierto que la
aplicación se calla. La web lee ese valor de `umbral.json`, así que al
reentrenar se ajusta solo.

### Por qué esta arquitectura

Comparación con las mismas 56 especies para las tres, que es la única forma de
que signifique algo:

| arquitectura | int8 | top1 | top3 | coste de cuantizar |
|---|---|---|---|---|
| **EfficientNet-Lite0** | **3,8 MB** | **79,2%** | **90,9%** | **0,0 pts** |
| MobileNetV2 | 2,7 MB | 75,2% | 90,2% | −1,1 pts |
| MobileNetV3-Large | 4,7 MB | 69,5% | 85,5% | −7,1 pts |

Las tres rondan el 76-79% en float32: para la precisión pura da casi igual cuál
elijas. La diferencia aparece **al cuantizar**. EfficientNet-Lite0 está diseñado
justo para eso, sin *squeeze-excite* y con ReLU6 en lugar de *hard-swish*, que
son las capas que peor se llevan con int8. Cuando lo que se entrega es un modelo
cuantizado, la arquitectura se elige por cómo cuantiza, no por su precisión en
coma flotante.

## La web

```bash
python comprobar.py            # copia el modelo a web/ y deja la prueba de referencia
python -m http.server 8080 -d docs
```

`http://127.0.0.1:8080` es la portada; `/app.html` la cámara, con tres candidatos con su confianza y un
`?test=1` que compara el resultado del navegador contra el de Python.

### Lo que mide el navegador

`banco.html` pasa un lote de validación por el modelo dentro del navegador y lo
compara con lo que dio Python sobre esas mismas fotos. Medido con 200 imágenes a
288 px:

| | |
|---|---|
| acierta Python | 78,0% |
| acierta el navegador | **80,5%** |
| coinciden entre sí | 93,0% |
| desvío medio de confianza | 5,1 pts |
| mediana por foto | **99 ms** |

**El `canvas` no cuesta precisión.** Las discrepancias se concentran en
predicciones de confianza baja, donde el modelo duda y un píxel decide el
ganador; de hecho en ocho de las catorce el que acertó fue el navegador. El
banco se genera con `--banco N` y no se publica.

Esa comprobación existe por un motivo: si el preprocesado del navegador no
replica exactamente el del entrenamiento (otro *resize*, otro orden de canales,
la normalización olvidada), **el modelo no falla, solo acierta menos** — y eso se
confunde con "el modelo es malo". Se toleran 5 puntos de diferencia, que es lo
que separa la interpolación del `canvas` de la de PIL.

Todo se sirve desde la propia carpeta `docs/` —`onnxruntime-web` incluido— y un
*service worker* cachea el conjunto en la primera visita. Sin eso, "funciona sin
conexión" sería falso: el modelo se volvería a pedir en cada carga.

## Los datos

De GBIF, filtrando a **licencias CC0 y CC-BY** — 749.952 fotos de Ecuador sin
restricción de uso comercial, de un total de 1.445.889 con foto. Cada imagen
conserva su autor y su licencia en el fichero de créditos: en CC-BY la atribución
no es opcional.

| Versión | Especies | Fotos por especie | Total |
|---|---|---|---|
| **v1 (hecha)** | 100 | hasta 200 | 16.872 |
| v2 | 300 | 300 | ~90.000 |
| v3 | 500+ | 300 | ~150.000 |

**Las especies no se eligen por lo que anuncia GBIF.** El conteo del facet es de
ocurrencias, no de fotos utilizables, y no sobrevive al filtro por proveedor ni
al de licencia por imagen. Para llenar 100 plazas hubo que **descartar 118
candidatas**: *Anthurium microspadix* anuncia 181 fotos y deja 0, *Cinchona
pubescens* 179 y deja 4. `datos.py` pide el triple de candidatas y acepta solo
las que de verdad llegan al mínimo.

## Plan

- [x] **1 · Dataset** — Consultar GBIF, filtrar por licencia, bajar las fotos en
      paralelo, dejarlas por especie con sus créditos.
- [x] **2 · Modelo de visión** — Fine-tuning de EfficientNet-Lite0. Partición por
      observación, no por foto.
- [x] **3 · ONNX** — Exportar, cuantizar a 8 bits y medir cuánta precisión cuesta.
- [x] **4 · La web** — Página estática con cámara, publicada en GitHub Pages.
- [ ] **5 · El oído** — Lo mismo para cantos de aves, con xeno-canto.

## Decisiones tomadas

**La partición de datos va por observación, no por foto.** Varias fotos del mismo
animal en el mismo sitio son casi duplicados; repartidas entre entrenamiento y
prueba inflarían el resultado y lo volverían mentira.

**El modelo tiene que poder decir "no lo sé".** Umbral de confianza y clase de
rechazo. En una herramienta de campo, una identificación equivocada dada con
seguridad hace más daño que no dar ninguna.

**Se empieza con cien clases y se crece midiendo.** Distinguir una iguana marina
de un lobo marino es trivial; separar dos atrapamoscas pardos es difícil hasta
para un ornitólogo. Estirar el número de especies degrada el modelo, así que cada
salto se valida antes de darlo.

## Entorno

```bash
python -m venv .venv
source .venv/Scripts/activate
pip install -r requirements.txt
```

PyTorch va con la variante **cu128**: la GPU de desarrollo es una RTX 5060
(Blackwell) y la rueda genérica de PyPI puede no traer el kernel de esa
arquitectura.

```python
import torch
print(torch.cuda.is_available(), torch.cuda.get_device_capability(0))  # (12, 0)
```

## Licencia

Código bajo MIT. Las fotos son de sus autores, bajo CC0 o CC-BY 4.0 según cada
caso — el detalle está en `datos/creditos.csv`. El dataset y el modelo derivados
se publican bajo CC-BY 4.0.
