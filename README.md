<div align="center">
  <img src="icono.svg" width="96" alt="Riksi">
  <h1>Riksi</h1>
  <p><strong>Reconoce la naturaleza del Ecuador, sin conexión.</strong></p>

  <p>
    <a href="https://diegofernandolojantenesaca.github.io/riski/"><b>Abrir la app</b></a>
    ·
    <a href="https://github.com/DiegoFernandoLojanTenesaca/yachaq">Yachaq, el agente</a>
  </p>
</div>

---

Apuntas la cámara a un animal o una planta y te dice qué es. Sin cuenta, sin
instalar nada y **sin internet**: el modelo se descarga una vez y a partir de ahí
corre entero dentro del navegador.

*Riksiy*, en kichwa, es reconocer. Saber quién es alguien.

## Y un chat, que es lo contrario

En la página hay una burbuja: [Yachaq](https://github.com/DiegoFernandoLojanTenesaca/yachaq),
un agente que responde por qué el piquero tiene los pies azules o dónde se ha
registrado el cóndor. Toma el mismo modelo de aquí y le añade consultas a GBIF
en vivo y 691 fichas de especies.

**Es lo contrario de esta página y hay que decirlo:** el identificador corre en
tu navegador y funciona en el páramo; el chat habla con un servidor y sin señal
no hay chat. Por eso el widget se apaga solo cuando no hay red, en vez de dejar
un botón que falla al pulsarlo.

Cada respuesta enseña qué herramientas usó. No es depuración: es la diferencia
entre algo que consultó los registros y algo que se lo inventó.

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
| **el modelo publicado** | **3,8 MB** | **79,8%** | **92,3%** |

Dataset: 25.878 fotos, 20.778 de entrenamiento y 5.100 de validación, partidas
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

### Más fotos casi no suben el acierto, pero sí la confianza

El dataset pasó de 16.872 a 25.878 fotos, un 53% más. El resultado:

| | 16.872 fotos | 25.878 fotos |
|---|---|---|
| acierta | 79,2% | **79,8%** |
| entre tres | 91,5% | **92,3%** |
| umbral calibrado | 0,30 | **0,20** |
| casos en los que responde | 82% | **93%** |

**Medio punto de acierto por un 53% más de datos.** Ahí no está el problema: el
techo lo pone lo mucho que se parecen entre sí las especies, no la cantidad de
ejemplos. Seguir descargando fotos no iba a arreglarlo, y ahora está medido en
vez de supuesto.

Lo que sí mejoró de verdad no aparece en el top1: **el modelo quedó mejor
calibrado**. Con el umbral recalculado responde en el 93% de los casos en vez
del 82%, acertando lo mismo. Once puntos más de preguntas contestadas es un
cambio que se nota usándolo, y el porcentaje de acierto ni se entera.

(La validación creció con el dataset, así que las dos columnas no se miden sobre
exactamente las mismas fotos. La diferencia es demasiado pequeña para que eso
importe, y demasiado pequeña para justificar más descargas.)

**Promediar la imagen con su espejo no compensa**: 0,2 puntos por duplicar el
tiempo de respuesta, sobre 500 imágenes. Medido con `comprobar.py --espejo` y no
implementado.

## Cuándo dice "no lo sé"

El umbral no está puesto a ojo. `comprobar.py --calibrar` mide, para cada corte
de confianza, cuántas respuestas se dan y cuántas de esas aciertan, y elige el
corte más bajo que llega al 85%:

| umbral | responde | acierta |
|---|---|---|
| 0,15 | 96% | 84% |
| **0,20** | **93%** | **86%** |
| 0,25 | 89% | 88% |
| 0,30 | 87% | 89% |

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
| v1 | 100 | hasta 200 | 16.872 |
| **v1.1 (la publicada)** | 100 | hasta 600 | **25.878** |
| v2 (descartada) | 300 | 300 | no existen los datos |

**No hay 300 especies del Ecuador que se puedan entrenar.** Se intentó, y la
propia descarga lo dijo: de las 175 candidatas más fotografiadas solo 79 llegan
a 50 fotos utilizables, y las descartadas dejan una mediana de **4**.
*Nephrolepis pectinata* anuncia 212 y deja 0. El techo real ronda las 110-130
especies, y subir de ahí exige bajar el mínimo a 25 fotos por clase, aceptar
licencias no comerciales o admitir fotos de cámara trampa. Ninguna de las tres
sale gratis.

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
- [x] **5 · El oído**. 60 aves del Ecuador, 6,9 MB, publicado con una licencia
      distinta al de fotos: ver más abajo.

## El oído

**74 aves, 4.307 grabaciones, 7,0 MB.** Acierta el 52,2% a la primera y el 69,0%
entre tres. Con su umbral calibrado en 0,50 responde en el 35% de los casos,
acertando el 86% de esas veces: es bastante menos seguro que el de fotos
y la aplicación lo dice con su `cf.` en vez de disimularlo. Un canto suelto, con
viento y otras aves de fondo, es mucho más difícil que una foto.

### Aquí los 8 bits no sirven

| variante | tamaño | acierta | coste |
|---|---|---|---|
| float32 | 13,6 MB | 55,2% | |
| **float16 · el publicado** | **6,9 MB** | **54,5%** | 0,7 pts |
| int8 | 4,2 MB | 41,2% | **14,0 pts** |

Justo lo contrario que en las fotos, donde el int8 salía gratis. Y no es la
calibración: se probaron activaciones con y sin signo y cuatro veces más
muestras, y las cuatro combinaciones pierden entre 9 y 10 puntos. Con el modelo mejor
entrenado la brecha se ensancha todavía más, hasta 14 puntos.

**Un canto se distingue por diferencias finas en el espectro** y la resolución
de 8 bits no da para tanto; una textura de plumaje tolera mucho más redondeo. La
lección general se mantiene, solo que al revés de como se aprendió: el formato
se elige midiendo sobre el problema concreto, no por lo que funcionó en el
anterior.

### Bajar el listón de calidad trajo catorce especies más

Al aceptar también grabaciones de calidad B, el material pasó de 2.753 a 4.307 y
**entraron 14 especies nuevas** que antes no llegaban al mínimo:

| | 60 aves | 74 aves |
|---|---|---|
| grabaciones | 2.753 | 4.307 |
| acierta | 54,5% | 52,2% |
| entre tres | 70,5% | 69,0% |

Dos puntos menos por reconocer catorce aves más. Es el mismo cambio que se hizo
en las fotos al pasar de 56 a 100 especies, y se resuelve igual: **en el campo
sirve más cubrir lo que te vas a encontrar que afinar en una lista corta**. Una
especie que el modelo no conoce no falla poco, falla siempre.

### Entrenar el doble valió diez puntos

| épocas | acierta | entre tres |
|---|---|---|
| 12 | 45,3% | 61,0% |
| **24** | **55,2%** | **70,3%** |
| 40 | 56,4% | 70,0% |

Casi diez puntos por dejarlo correr el doble. Pero de 24 a 40 no hay nada:
exportados a 16 bits, los dos dan el mismo 54,5%, así que se publica el de 24 y
la otra mitad del cómputo se ahorra. Las doce épocas venían heredadas del modelo de fotos, donde sí bastan:
con 25.878 imágenes se ve cada ejemplo muchas veces, pero con 2.228 grabaciones
el modelo apenas había empezado. **Los ajustes no se heredan entre problemas
aunque el código sea el mismo.**

### Cómo está hecho

Misma receta que las fotos, con una diferencia de fondo: **el espectrograma va
dentro del modelo**. El `.onnx` recibe el audio crudo y él mismo lo convierte en
la imagen de tiempo por frecuencia que la red sabe leer.

Si se calculara fuera, el navegador tendría que reproducir en JavaScript la
misma transformada, la misma ventana y la misma escala mel. Y ahí una diferencia
no da error: da otro resultado. Metiéndolo en el grafo solo existe una
implementación. Hace falta el exportador nuevo de PyTorch (`dynamo=True`); el
antiguo no sabe exportar el STFT porque trabaja con números complejos.

Lo demás se hereda: partición **por grabación** en vez de por observación (dos
trozos del mismo audio son casi el mismo sonido), y cuantización **parcial**,
solo `Conv` y `Gemm`. El banco de filtros mel se queda en coma flotante, porque
redondear a enteros una transformada de Fourier estropea justo la información
fina que separa dos cantos y encima no ahorra nada.

```bash
python audio.py --licencias                 # qué hay antes de bajar nada
python audio.py --permiso todo --especies 60
python entrenar_audio.py
python exportar_audio.py
```

### El fallo que no daba ningún error

La primera corrida entrenó con la pérdida en NaN y el acierto clavado en el azar,
sin una sola excepción por ninguna parte.

Un canto de ave es un tono casi puro: concentra la energía en muy pocas
frecuencias. Medido, un silbido de 4 kHz llega a **55.000** en el espectrograma
y revienta el techo de la media precisión (**65.504**) en los pasos intermedios
del STFT. De ahí sale `inf`, luego `log(inf)`, luego NaN, y el entrenamiento
entero a la basura en silencio.

El espectrograma va ahora siempre en float32 y solo la red entrena en media
precisión. Con el arreglo, tres épocas sobre datos a medio descargar pasan de
3,5% (el azar con 42 clases) a **34,9%**.

Lo interesante es por qué la comprobación no lo detectó: probaba con
`torch.randn`, o sea ruido, y el ruido reparte la energía por todo el espectro y
nunca desborda. **Estaba probando con la única señal que no podía fallar.** Ahora
prueba con un tono.

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

## Licencias

Código bajo **MIT**.

**El modelo de fotos, CC-BY 4.0.** Las imágenes son de sus autores, bajo CC0 o
CC-BY 4.0 según cada caso, y el detalle está en el `creditos.csv` que genera
`datos.py`. Se filtró a esas dos licencias justamente para poder publicar
dataset y modelo sin ataduras.

**El modelo de cantos, CC-BY-NC 4.0.** Aquí no hubo elección. Medido sobre las
17.857 grabaciones de aves de Ecuador con calidad A que hay en xeno-canto,
**ninguna** tiene licencia libre:

| familia | grabaciones | qué permite |
|---|---|---|
| no comercial | 12.546 | usar y derivar, sin fines comerciales |
| sin derivadas | 3.812 | **nada**: prohíbe obras derivadas, y un modelo lo es |
| compartir igual | 1.499 | uso comercial, pero el derivado hereda la licencia |
| libre | **0** | |

Quedarse solo con las de compartir igual dejaba **una** especie con suficientes
grabaciones, así que no era una opción real. Se aceptan las no comerciales y el
modelo de audio se publica como tal, separado del de fotos. Las de sin derivadas
no se tocan.

Es la decisión que toma también BirdNET y casi toda la bioacústica, por el mismo
motivo. `python audio.py --licencias` recalcula este reparto cuando se quiera,
sin descargar nada.
