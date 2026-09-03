# El post

Un artículo sobre los tres proyectos —[riksi](../), [riksi-radar] y [yachaq]—,
escrito alrededor de lo único que tenían en común: **cada vez que medí algo en
serio, la cifra bajó.**

| | |
|---|---|
| [`post.md`](post.md) | español, el original |
| [`post-en.md`](post-en.md) | inglés |
| [`imagenes/`](imagenes) | ocho figuras, en claro y en oscuro, generadas desde los datos |

Los dos Markdown llevan cabecera de Dev.to con `published: false`, así que se
pueden importar sin que salgan publicados por accidente.

## Los términos del título, en corto

Por si el titular académico despista:

**Micro y macro-promedio** son dos formas de resumir 400 resultados en un número.
El conjunto tiene 20 especies pero muy desigual: 128 observaciones de iguana
marina y una sola de *Brachyotum*.

- **Micro**: aciertos totales entre observaciones totales — 337/400 = 84,2 %.
  Cada **fotografía** pesa igual, así que la iguana decide un tercio del
  resultado ella sola.
- **Macro**: el acierto de cada especie por separado, y la media de esas 20
  cifras — 78,7 %. Cada **especie** pesa igual.

Los 5,5 puntos de diferencia salen de que la iguana, además de dominar el
conjunto, es de las que mejor se clasifican (94,5 %). Con un conjunto equilibrado
los dos números coincidirían.

**Sesgo de muestreo**: el conjunto de evaluación no representa el problema. Nadie
lo eligió mal; es que la gente fotografía iguanas y no arbustos de páramo.

**Fuera de distribución**: se evalúa con datos de otras fuentes y fechas que los
de entrenamiento. Lo contrario —evaluar con fotos parecidas a las de
entrenamiento— siempre da mejor y engaña.

## Tres títulos para el mismo texto

No es un descuido: cada uno se lee en un sitio y compite contra cosas distintas.

| dónde | cuál | por qué |
|---|---|---|
| Dev.to y Medium | «Cuatro cifras que publiqué antes de medirlas bien» | el feed premia lo concreto y la primera línea decide si se abre |
| titular de la página | «Sesgo de muestreo en la evaluación fuera de distribución…» | es la que se cita y la que aparece en un perfil; nombra el objeto de estudio con el vocabulario del campo |
| etiqueta `<title>` | «Sesgo de muestreo en evaluación fuera de distribución» | los buscadores cortan sobre los 60 caracteres |

El titular académico describe el **hallazgo**, no el sistema. Un «desarrollo de
un clasificador de especies para…» prometería un artículo de aplicación, y tres
cuartas partes de éste hablan de errores de medición.

Los tres viven en `ver.py` salvo el de Dev.to, que está en el frontmatter de cada
`.md`. `ver.py --comprobar` falla si el `<title>` pasa de 62 caracteres o si el
titular se descuadra.

## Los dos scripts

```bash
python graficos.py     # las figuras, desde DuckDB y los .json
python ver.py          # post.html, post-en.html y docs/articulo.html
```

`ver.py` hace tres cosas: los dos HTML para leer en local —de ahí sale el PDF
imprimiendo con Ctrl+P, que la hoja ya trae las reglas—, copia las figuras a
`docs/articulo/` y genera **`docs/articulo.html`**, que es la versión publicada
con la plantilla del sitio y el enlace canónico al que apuntan Dev.to y Medium.

**El conversor de Markdown va a mano, sin dependencias.** El post usa siete
cosas —titulares, tablas, código, cita, imágenes, negrita y enlaces— y traerse
un paquete entero obliga a instalarlo en cualquier máquina donde se quiera
releer el texto. Si el post creciera hasta necesitar Markdown de verdad,
entonces sí toca `pip install markdown`.

## De dónde sale cada número

Ninguno está escrito a mano. Todos salen de un fichero que está en un repo, y
`graficos.py --comprobar` verifica que sigan cuadrando antes de dibujar nada:

| en el post | de dónde |
|---|---|
| 79,8 % top-1 · 3,8 MB · coste de int8 | [`docs/modelo/metricas.json`](../docs/modelo/metricas.json) |
| 400 observaciones, 337 aciertos, 20 especies | `datos/radar.duckdb` en riksi-radar, cacheado en [`por-especie.json`](por-especie.json) |
| 39 / 16 / 8 del contraste con iNaturalist | [`contraste.json`][contraste], versionado a propósito |
| los pares de confusión y los 44 en top-3 | [`desacuerdos.json`](desacuerdos.json), exportado del mismo almacén |
| el hueco de 0,075 y el corte en 0,44 | [`calibracion.json`](calibracion.json), medido con `indice.py --calibrar` |
| la tabla de poda del vocabulario | `indice.py` en yachaq |
| 671 → 467 → 154 MB | `codificador.py` y el README de yachaq |

Las dos últimas filas son las únicas que salen de un comentario y no de un
fichero de datos: son mediciones que no dejaron rastro en disco. Están marcadas
como tales en la función que las dibuja.

## Los dos temas

Cada figura se genera en claro y en oscuro desde la misma función —un objeto
`Tema` con los colores, no un `if oscuro` repartido por el fichero— y la página
sirve la que toque con `<picture>` y `prefers-color-scheme`. Una figura de fondo
claro sobre una página oscura deslumbra, y es lo primero que delata que las
imágenes se pegaron sin mirarlas en su sitio.

Si se reentrena o se vuelve a correr el radar, estas cifras cambian y el post
queda viejo. `graficos.py --comprobar` lo detecta —falla si el DuckDB ya no dice
400 y 337—, pero el texto hay que repasarlo a mano.

[riksi-radar]: https://github.com/DiegoFernandoLojanTenesaca/riksi-radar
[yachaq]: https://github.com/DiegoFernandoLojanTenesaca/yachaq
[contraste]: https://github.com/DiegoFernandoLojanTenesaca/riksi-radar/blob/main/contraste.json
