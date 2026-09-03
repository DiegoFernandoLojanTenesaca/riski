# El post

Un artículo sobre los tres proyectos —[riksi](../), [riksi-radar] y [yachaq]—,
escrito alrededor de lo único que tenían en común: **cada vez que medí algo en
serio, la cifra bajó.**

| | |
|---|---|
| [`post.md`](post.md) | español, el original |
| [`post-en.md`](post-en.md) | inglés |

Los dos llevan cabecera de Dev.to con `published: false`, así que se pueden
importar sin que salgan publicados por accidente.

## De dónde sale cada número

Ninguno está escrito de memoria. Todos salen de un fichero que está en un repo:

| en el post | de dónde |
|---|---|
| 79,8 % top-1 · 3,8 MB · coste de int8 | [`docs/modelo/metricas.json`](../docs/modelo/metricas.json) |
| 400 observaciones, 337 aciertos, 20 especies | `datos/radar.duckdb`, en riksi-radar |
| 39 / 16 / 8 del contraste con iNaturalist | [`contraste.json`][contraste], versionado a propósito |
| 0,44 y la tabla de poda del vocabulario | `indice.py` en yachaq, medido con `--calibrar` |
| 671 → 457 → 154 MB | `codificador.py` en yachaq |

Si se reentrena o se vuelve a correr el radar, estas cifras cambian y el post
queda viejo. No hay CI que lo vigile —es un texto, no código— así que conviene
repasarlo antes de publicarlo en otro sitio.

[riksi-radar]: https://github.com/DiegoFernandoLojanTenesaca/riksi-radar
[yachaq]: https://github.com/DiegoFernandoLojanTenesaca/yachaq
[contraste]: https://github.com/DiegoFernandoLojanTenesaca/riksi-radar/blob/main/contraste.json
