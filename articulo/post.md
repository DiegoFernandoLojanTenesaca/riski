---
title: "Tres proyectos, una lección: casi todas mis cifras estaban infladas"
published: false
tags: machinelearning, python, mlops, datascience
---

Entrené un clasificador de 100 especies de fauna ecuatoriana, monté un pipeline
para verlo trabajar sobre observaciones reales, y le puse un agente encima. Tres
repositorios, unos tres meses.

Este post no va de cómo los construí. Va de que **cada vez que medí algo en
serio, el número bajó** — y de que ese es el trabajo, no un contratiempo.

Van cuatro casos. En los cuatro la primera cifra era defendible, estaba publicada
y era engañosa.

---

## El montaje

Lo justo para que se entienda el resto:

| | |
|---|---|
| **[riksi](https://github.com/DiegoFernandoLojanTenesaca/riksi)** | EfficientNet-Lite0, 100 especies, 3,8 MB en int8. Corre en el navegador con ONNX Runtime Web |
| **[riksi-radar](https://github.com/DiegoFernandoLojanTenesaca/riksi-radar)** | Kafka → el modelo → DuckDB → dbt. Trae observaciones nuevas de [GBIF](https://www.gbif.org/) y las clasifica sin ver la etiqueta |
| **[yachaq](https://github.com/DiegoFernandoLojanTenesaca/yachaq)** | Un agente sobre lo anterior: RAG, memoria, servidor MCP |

El modelo acierta **79,8 %** top-1 sobre 1000 imágenes de validación. Esa cifra
está bien medida y no es ninguna de las que van a caerse.

---

## Caso 1 · «El modelo mejora fuera de su reparto»

Las imágenes de validación salen del mismo reparto que las de entrenamiento:
mismas fuentes, mismos fotógrafos, mismo sesgo de encuadre. Un 79,8 % ahí
responde a una pregunta bastante estrecha.

Por eso monté el radar: coger observaciones que se subieron a GBIF **después**,
de gente distinta, sin que nadie las eligiera, y pasar cada foto por el modelo.

400 observaciones. **337 aciertos: 84,2 %.**

Seis puntos por encima del banco de validación. Lo escribí en el README con la
palabra «sube» en negrita.

Está mal. No la aritmética — el sesgo.

```
Amblyrhynchus cristatus (iguana marina)   128 de 400   32 %
las tres primeras especies juntas         198 de 400   50 %
especies distintas, de las 100 que conoce          20
```

La ciencia ciudadana no muestrea uniformemente. La gente fotografía lo que ve, y
en Galápagos ve iguanas marinas. Ese 84,2 % es sobre todo la nota del modelo en
una especie, repetida 128 veces.

Promediando por especie en vez de por observación —dando el mismo peso a la
iguana que a la tortuga que sale tres veces:

| | acierto |
|---|---|
| por observación | 84,2 % |
| **promediando especies** | **78,7 %** |

Y ahí está lo interesante: **78,7 % en campo contra 78,0 % en el banco.** El
modelo no mejora fuera de su reparto. Se comporta igual.

Que es una conclusión más aburrida y mucho más creíble. «No hay deriva» es un
resultado; «mejora en producción» era un artefacto de cómo promedié.

> Si vas a publicar una sola cifra sobre datos de ciencia ciudadana, promedia por
> clase. La media por observación mide la distribución de tus datos tanto como tu
> modelo.

---

## Caso 2 · Los desacuerdos que no eran del modelo

Quedaban 63 observaciones donde el modelo y GBIF discrepaban. Tres explicaciones
posibles: falló el modelo, la observación está mal identificada, o la foto no
muestra lo que dice el registro.

Escribí en el README que el pipeline no decide cuál, y que las tortugas de
Galápagos que salían repetidas eran «taxonomía en disputa entre biólogos».

Me lo inventé. Sonaba plausible y no lo comprobé.

Resulta que hay una cuarta explicación, y es comprobable: **GBIF publica
instantáneas periódicas, no un espejo en vivo de iNaturalist.** Una observación
que iNaturalist ya corrigió puede seguir en GBIF con la identificación vieja.

Se verifica en dos saltos. GBIF guarda el identificador de iNaturalist en
`catalogNumber`, así que se puede preguntar cuál es la identificación **de hoy**:

```python
def _en_inaturalist(clave_gbif):
    oc = _pedir(f"{GBIF}/occurrence/{clave_gbif}")
    id_inat = oc.get("catalogNumber")          # el enlace a la fuente
    d = _pedir(f"{INAT}/observations/{id_inat}")
    o = d["results"][0]
    return {"taxon_hoy": (o.get("taxon") or {}).get("name"),
            "grado": o.get("quality_grade"),
            "identificaciones": o.get("identifications_count", 0)}
```

Los 63, dos minutos de peticiones. 24 tienen hoy otra etiqueta.

Pero ahí hay una trampa que casi me como. No todos los cambios significan lo
mismo:

| cambio | qué es |
|---|---|
| `Anous stolidus` → `Anous stolidus galapagensis` | **refinamiento**: se precisó la población, la especie es la misma, el modelo falló igual |
| `Chelonoidis porteri` → `Chelonoidis niger porteri` | **otra especie**: pasó a colgar de *C. niger* |

En el segundo caso el modelo había dicho `Chelonoidis niger`. Bajo la taxonomía
de hoy, **acertó**. La tortuga de Santa Cruz pasó a ser subespecie de *C. niger*
y GBIF aún tenía la versión anterior.

Contarlos por separado es toda la diferencia entre un hallazgo y un
autoengaño, así que la lógica que juzga es lo único con test de verdad:

```python
def _juzgar(caso, hoy):
    gbif, dice, ahora = caso["gbif"], caso["modelo"], hoy["taxon_hoy"]
    if ahora == gbif:                          return "sigue igual"
    if _es_hijo(ahora, gbif):                  return "precisada"
    if ahora == dice or _es_hijo(ahora, dice):  return "el modelo tenía razón"
    return "cambió de especie"
```

`_es_hijo` compara por palabras y no con `startswith`, que daría por buena una
coincidencia a media palabra:

```python
assert not _es_hijo("Anous stolidusa", "Anous stolidus")
assert not _es_hijo("Anous stolidus", "Anous stolidus")   # ni hija de sí misma
assert     _es_hijo("Chelonoidis niger porteri", "Chelonoidis niger")
```

El resultado:

| de los 63 desacuerdos | |
|---|---|
| la etiqueta sigue igual | 39 |
| precisada a subespecie → falló igual | 16 |
| **la etiqueta era vieja: el modelo acertaba** | **8** |

Ocho de 63 no eran fallos. Y los 63 son de grado *research* en iNaturalist —
identificaciones que la comunidad ya confirmó—, así que los otros 55 no tienen
dónde escudarse.

**Y aun así hay que rebajarlo.** Las ocho son del mismo taxón. Descontarlas sube
la media por especie de 78,7 % a 81,2 %, pero eso arregla una especie de veinte y
ninguna otra: es el sesgo del caso 1 entrando por otra puerta. La cifra que
seguiría publicando es 78,7 %.

---

## Caso 3 · El umbral que había puesto a ojo

El agente tiene un RAG sobre las fichas de las 100 especies. La pregunta de
siempre: ¿a partir de qué similitud una ficha recuperada es relevante?

Puse 0,5. Número redondo, sin ninguna razón.

Lo que hay que medir no es la similitud media, sino **si las dos poblaciones se
separan**: las preguntas que el corpus puede responder contra las que no. Si sus
distribuciones se solapan, no hay umbral bueno — el problema no es el número.

Se separaban, con un hueco de 0,075 entre ellas. El punto medio cae en **0,44**,
no en 0,5.

El bonus fue intentar recortar el índice, que ocupaba 235 MB:

```
vocabulario   disco    hueco entre las dos poblaciones
   250.037    235 MB    +0,075   ← el de ahora
   200.000    204 MB    +0,084   31 MB menos; no compensa el riesgo
   120.000    140 MB    SE SOLAPAN
    80.000    108 MB    SE SOLAPAN
    40.000     75 MB    +0,017   sobrevive por los pelos
```

Podando a 120.000 términos el índice adelgaza un 40 % y **el umbral deja de
existir**: ya no hay hueco que partir. Sin medir la separación, ese recorte
parece gratis — el sistema sigue respondiendo, solo que ya no sabe cuándo callar.

---

## Caso 4 · 671 MB en un contenedor de 512

Este no es de medición, pero es el que más me enseñó.

El agente tenía que caber en un plan gratuito: 512 MB. Con `fastembed`, el
proceso se iba a **671 MB** solo por cargar el codificador. Fuera.

La causa: `fastembed` carga los pesos del modelo en RAM y los deja ahí.

Reescribí la inferencia con ONNX Runtime a mano. Dos cosas la arreglaron. La
primera, guardar los pesos como *external data*, que hace que se mapeen en
memoria en vez de copiarse:

```python
onnx.save(modelo, str(LIGERO / "modelo.onnx"), save_as_external_data=True, ...)

opciones = ort.SessionOptions()
opciones.enable_cpu_mem_arena = False      # sin arena que crece y no vuelve
ort.InferenceSession(ruta, sess_options=opciones)
```

La segunda, soltar la sesión al terminar cada tanda en vez de retenerla:

```python
def vectorizar(textos):
    with _candado:
        try:
            return _vectorizar(textos)
        finally:
            if SOLTAR:
                _sesion.cache_clear()
                gc.collect()
```

671 → 457 → **154 MB**, con margen de sobra.

Dos trampas por el camino, ambas silenciosas:

- **El *mean pooling* va ponderado por la máscara de atención.** Si promedias
  incluyendo el relleno, los vectores salen desplazados. No falla nada: el RAG
  simplemente recupera algo peor y le echas la culpa al modelo.
- **`enable_padding()` sin argumentos rellena hasta 512 tokens.** Una inferencia
  que tarda 0,2 s pasa a tardar un minuto. Hay que pasarle
  `direction="right", pad_id=1, pad_token="<pad>"`.

---

## Lo que sí funcionó a la primera (poco)

Para no dar la impresión de que todo se cayó:

- **Cuantizar a int8** cuesta 0,4 puntos de top-1 y baja el modelo de 13,5 a 3,8
  MB. La mejor relación del proyecto.
- **Promediar la imagen con su espejo** da 0,2 puntos por duplicar el tiempo de
  respuesta. Medido, y **no implementado** — medir para descartar también cuenta.
- **LangGraph contra una orquestación a mano**: 95 sentencias contra 55, 31,0 s
  contra 18,4 s. Pero LangGraph reanuda desde el checkpoint en 0,0 s y la mía no.
  Con dos nodos no compensa; con quince y trabajo caro que no quieres repetir,
  sí. Me quedé con la mía y dejé la comparación en el repo.

---

## Lo que me llevo

**Una cifra que sube es sospechosa.** Las cuatro veces que un número me gustó,
estaba midiendo mi conjunto de datos y no mi modelo.

**Promedia por clase.** En datos de ciencia ciudadana, la media por observación
es casi una descripción de qué animales son fotogénicos.

**Comprueba la anécdota que suena bien.** «Taxonomía en disputa entre biólogos»
sonaba a que yo sabía de qué hablaba. Eran dos peticiones HTTP averiguar que era
falso, y la verdad resultó más interesante.

**Distingue tipos de cambio antes de contarlos.** 24 etiquetas cambiadas parecían
24 fallos ajenos. Eran 8. Los otros 16 eran míos y se disfrazaban de iguales.

**Un umbral sin la separación medida es decoración.** Y si el sistema aguanta con
un umbral inútil, nadie va a enterarse.

---

## Trabajo futuro

Lo honesto es decir dónde no llega:

- **400 observaciones y 20 especies** no bastan para las otras 80. El radar
  tendría que correr semanas para tener algo por especie.
- **Un solo modelo, un solo país.** Nada de esto dice si el patrón se repite en
  otro conjunto.
- **La verificación contra iNaturalist es de un día.** Rehacerla dentro de seis
  meses diría cuál es el desfase típico de GBIF, que sería un dato de verdad
  útil para cualquiera que use esos datos.

Los tres repos están abiertos, con los `--comprobar` que sostienen las cifras:
[riksi](https://github.com/DiegoFernandoLojanTenesaca/riksi) ·
[riksi-radar](https://github.com/DiegoFernandoLojanTenesaca/riksi-radar) ·
[yachaq](https://github.com/DiegoFernandoLojanTenesaca/yachaq)
