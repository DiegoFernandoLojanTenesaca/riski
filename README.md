<div align="center">
  <img src="icono.svg" width="96" alt="Riksi">
  <h1>Riksi</h1>
  <p><strong>Reconoce la naturaleza del Ecuador, sin conexión.</strong></p>
</div>

---

Apuntas la cámara a un animal o una planta y te dice qué es. Sin cuenta, sin
instalar nada y **sin internet**: el modelo se descarga una vez y a partir de ahí
corre entero dentro del navegador.

*Riksiy*, en kichwa, es reconocer. Saber quién es alguien.

## Por qué sin conexión

En Galápagos, en el Yasuní o en el páramo no hay señal. Es exactamente donde
alguien necesita identificar lo que está viendo, y exactamente donde falla
cualquier herramienta que dependa de un servidor. Por eso el modelo va dentro del
dispositivo y no en la nube: no es una restricción técnica, es el punto.

## Estado

**EfficientNet-Lite0 a 288 px, 100 especies, 3,8 MB cuantizado a 8 bits.**
Medido sobre 1.000 imágenes de validación que el modelo no vio al entrenar:

| | int8 | acierta | entre tres |
|---|---|---|---|
| **el modelo publicado** | **3,8 MB** | **79,2%** | **91,5%** |

Dataset: 16.872 fotos, 13.485 de entrenamiento y 3.387 de validación, partidas
por observación. Las cifras salen de `metricas.json`, que escribe `exportar.py`
en cada corrida, y la web las lee de ahí: no se copian a mano a ningún sitio.

## Lo que se probó para llegar ahí

Todo con las mismas 100 especies y las mismas imágenes de validación, que es la
única forma de que la comparación signifique algo:

| configuración | int8 | acierta | entre tres | coste de cuantizar |
|---|---|---|---|---|
| EfficientNet-Lite0 · 320 px | 3,8 MB | 79,6% | 92,3% | 0,2 pts |
| **EfficientNet-Lite0 · 288 px** | **3,8 MB** | **79,2%** | **91,5%** | 0,1 pts |
| EfficientNet-Lite0 · 224 px | 3,8 MB | 75,0% | 89,6% | 0 |
| MobileNetV4-conv-small · 224 px | 2,9 MB | 63,3% | 81,2% | **8,9 pts** |

**Subir la resolución salió gratis en descarga.** Los pesos son los mismos 3,8 MB
a 224 que a 288, porque una CNN no cambia de tamaño con la entrada: solo cuesta
cómputo, un 65% más, que en el banco del navegador son 99 ms por foto en vez de
61. Cuatro puntos por eso es el mejor cambio de todo el proyecto.

**La curva se aplana en 288.** De 224 a 288 hay 4,2 puntos; de 288 a 320, solo
0,4, y eso cuesta un 23% más de cómputo en cada foto que alguien haga en el
campo. Se publica el de 288.

**MobileNetV4 es de 2024 y quedó último**, con 8,9 puntos perdidos al cuantizar.
Es la tercera vez que pasa lo mismo: las arquitecturas que persiguen precisión en
coma flotante meten capas que el int8 destroza. Con MobileNetV3 fueron 7,1
puntos. Cuando el entregable es un modelo cuantizado, **la arquitectura se elige
por cómo cuantiza, no por su año ni por su precisión en float**.

<details>
<summary>La comparación de arquitecturas que llevó a EfficientNet-Lite0 (56 especies)</summary>

Hecha antes de completar el dataset, con las 56 especies que había entonces:

| arquitectura | int8 | acierta | entre tres | coste de cuantizar |
|---|---|---|---|---|
| **EfficientNet-Lite0** | **3,8 MB** | **79,2%** | **90,9%** | **0,0 pts** |
| MobileNetV2 | 2,7 MB | 75,2% | 90,2% | 1,1 pts |
| MobileNetV3-Large | 4,7 MB | 69,5% | 85,5% | 7,1 pts |

Las tres rondaban el 76-79% en float32: para la precisión pura daba casi igual
cuál elegir, y la diferencia aparecía solo al cuantizar. EfficientNet-Lite0 está
diseñado justo para eso, sin *squeeze-excite* y con ReLU6 en lugar de
*hard-swish*, que son las capas más hostiles al int8.
</details>

**Promediar la imagen con su espejo no compensa**: 0,2 puntos por duplicar el
tiempo de respuesta, sobre 500 imágenes. Medido con `comprobar.py --espejo` y no
implementado.

## Cuándo dice "no lo sé"

El umbral no está puesto a ojo. `comprobar.py --calibrar` mide, para cada corte
de confianza, cuántas respuestas se dan y cuántas de esas aciertan, y elige el
corte más bajo que llega al 85%:

| umbral | responde | acierta |
|---|---|---|
| 0,20 | 92% | 82% |
| **0,30** | **82%** | **86%** |
| 0,40 | 71% | 90% |

Bajo es mejor, porque cada punto de umbral de más es un acierto que la
aplicación se calla. Por debajo del corte la ficha sale marcada con **cf.**, que
es lo que escribe un taxónomo cuando la determinación es probable pero no firme.
La web lee ese valor de `umbral.json`, así que al reentrenar se ajusta solo.

## La web

```bash
python comprobar.py                  # deja docs/ listo y la prueba de referencia
python -m http.server 8080 -d docs
```

| página | qué es |
|---|---|
| `index.html` | portada: qué es, cómo funciona, las cifras y de dónde salen los datos |
| `app.html` | la cámara. `?test=1` compara el resultado del navegador con el de Python |
| `especies.html` | catálogo de las 100 especies, con buscador y filtro por grupo |
| `banco.html` | herramienta interna: mide el navegador contra Python sobre un lote |

Todo se sirve desde la propia carpeta `docs/`, incluido `onnxruntime-web`, y un
*service worker* guarda el conjunto en la primera visita. Sin eso, "funciona sin
conexión" sería falso: el modelo se volvería a pedir en cada carga. El reparto es
por peso: modelo, wasm y fotos van de caché primero; el código y los JSON van de
red primero con la copia local de respaldo, porque con caché primero una
corrección nunca llega a quien ya visitó la página.

`docs/` y no `web/` porque GitHub Pages publica esa carpeta directamente, sin
workflow de Actions.

### Lo que mide el navegador

`banco.html` pasa un lote de validación por el modelo dentro del navegador y lo
compara con lo que dio Python sobre esas mismas fotos. Con 200 imágenes a 288 px:

| | |
|---|---|
| acierta Python | 78,0% |
| acierta el navegador | **80,5%** |
| coinciden entre sí | 93,0% |
| desvío medio de confianza | 5,1 pts |
| mediana por foto | **99 ms** |

**El `canvas` no cuesta precisión.** Las discrepancias se concentran en
predicciones de confianza baja, donde el modelo duda y un píxel decide el
ganador; en ocho de las catorce el que acertó fue el navegador.

Esta comprobación existe porque es el único fallo del proyecto que no da error:
si el preprocesado del navegador no replica el del entrenamiento (otro *resize*,
otro orden de canales, la normalización olvidada), **el modelo no falla, solo
acierta menos**, y eso se confunde con "el modelo es malo". El banco se genera
con `--banco N` y no se publica.

## Los datos

De GBIF, filtrando a **licencias CC0 y CC-BY**: 749.952 fotos de Ecuador sin
restricción de uso comercial, de un total de 1.445.889 con foto. Cada imagen
conserva su autor y su licencia en `creditos.csv`, porque en CC-BY la atribución
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

Además, solo se quedan las fotos de iNaturalist. GBIF mezcla proveedores muy
distintos y una cuarta parte son cámaras trampa: fotos nocturnas en infrarrojo o
pliegos de herbario prensados son otro dominio, y meterlos empeora el modelo en
vez de mejorarlo.

## Los comandos

```bash
python datos.py --especies 100 --fotos 200      # fase 1: dataset desde GBIF
python datos.py --prueba                        # comprobación de las consultas

python entrenar.py --tam 288                    # fase 2: fine-tuning
python entrenar.py --prueba                     # comprobación de la partición

python exportar.py --modelo modelo/riksi.pt     # fase 3: ONNX, int8 y medición

python comprobar.py --calibrar 1000             # elige el umbral del cf.
python comprobar.py --banco 200                 # lote para medir el navegador
python comprobar.py --espejo 500                # ¿compensa promediar con el espejo?
```

`datos.py` reanuda: las fotos ya descargadas no se vuelven a pedir, y las
candidatas se guardan en disco porque son unas 900 consultas que no cambian de un
día para otro.

## Plan

- [x] **1 · Dataset**. Consultar GBIF, filtrar por licencia, bajar las fotos en
      paralelo y dejarlas por especie con sus créditos.
- [x] **2 · Modelo de visión**. Fine-tuning de EfficientNet-Lite0, con partición
      por observación y no por foto.
- [x] **3 · ONNX**. Exportar, cuantizar a 8 bits y medir cuánta precisión cuesta.
- [x] **4 · La web**. Página estática con cámara, publicada en GitHub Pages.
- [ ] **5 · El oído**. Lo mismo para cantos de aves, con xeno-canto.

## Decisiones tomadas

**La partición de datos va por observación, no por foto.** Varias fotos del mismo
animal en el mismo sitio son casi duplicados; repartidas entre entrenamiento y
prueba inflarían el resultado y lo volverían mentira.

**El modelo tiene que poder decir "no lo sé".** En una herramienta de campo, una
identificación equivocada dada con seguridad hace más daño que no dar ninguna.

**Se empieza con cien clases y se crece midiendo.** Distinguir una iguana marina
de un lobo marino es trivial; separar dos atrapamoscas pardos es difícil hasta
para un ornitólogo. Estirar el número de especies degrada el modelo, así que cada
salto se valida antes de darlo.

**Cada cifra publicada viene de un fichero medido.** Ni el README ni la web
tienen números escritos a mano: salen de `metricas.json` y `umbral.json`, que se
regeneran al reentrenar. Es la única manera de que no se queden desfasados sin
que nadie se entere.

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

Windows: la consola viene en cp1252 y tumba el proceso al imprimir cualquier
carácter fuera de esa tabla. Los scripts llaman a
`sys.stdout.reconfigure(encoding="utf-8", errors="replace")` al arrancar; una
flecha en un `print` costó doce épocas de entrenamiento.

## Licencia

Código bajo MIT. Las fotos son de sus autores, bajo CC0 o CC-BY 4.0 según cada
caso, y el detalle está en el `creditos.csv` que genera `datos.py`. El dataset y
el modelo derivados se publican bajo CC-BY 4.0.
