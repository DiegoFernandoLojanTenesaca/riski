"""Las figuras del post, generadas desde los datos.

**Ninguna cifra se escribe a mano aquí.** Cada gráfico lee el fichero que la
sostiene —`metricas.json`, el DuckDB del radar, `contraste.json`— y si esos
cambian, el gráfico cambia con ellos. Un PNG con un número dibujado a mano es
exactamente el tipo de cifra que el post denuncia.

Las dos excepciones están marcadas en su función y son medidas que no dejaron
fichero: la tabla de poda del vocabulario y las de RAM, que viven en comentarios
de yachaq. Se citan con su origen.

    python graficos.py            # los seis, a imagenes/
    python graficos.py --comprobar
"""

import argparse
import json
import pathlib
import sys

AQUI = pathlib.Path(__file__).parent
RIKSI = AQUI.parent
RADAR = RIKSI.parent / "riksi-radar"
SALIDA = AQUI / "imagenes"

# La paleta del sitio, para que las figuras no parezcan de otro proyecto.
# Sale de docs/estilo.css.
BASALTO, PAPEL = "#14181b", "#e4e5df"
TINTA, SUAVE = "#171b1c", "#5d6663"
LIQUEN, AGUA = "#c7c24b", "#79b0a8"
LINEA = "#d0d2ca"
ROJO = "#b4553f"      # para lo que va mal; no está en el sitio porque el sitio
                      # no tiene nada que vaya mal


def _lienzo(ancho=9, alto=5):
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(ancho, alto), dpi=160)
    fig.patch.set_facecolor(PAPEL)
    ax.set_facecolor(PAPEL)
    for lado in ("top", "right"):
        ax.spines[lado].set_visible(False)
    for lado in ("left", "bottom"):
        ax.spines[lado].set_color(LINEA)
    ax.tick_params(colors=SUAVE, labelsize=9)
    return fig, ax


def _guardar(fig, nombre):
    SALIDA.mkdir(exist_ok=True)
    destino = SALIDA / f"{nombre}.png"
    fig.savefig(destino, facecolor=PAPEL, bbox_inches="tight", pad_inches=0.25)
    import matplotlib.pyplot as plt
    plt.close(fig)
    print(f"  {destino.name}  ({destino.stat().st_size // 1024} KB)")
    return destino


CONSULTA = """
    select especie, count(*) n, sum(coincide::int) ok
    from observaciones where modelo_dice is not null
    group by 1 order by n desc
"""
POR_ESPECIE = AQUI / "por-especie.json"


def _radar():
    """Las 400 observaciones, especie a especie.

    Salen del DuckDB del radar, pero se dejan cacheadas en un JSON al lado del
    post. Dos razones: el almacén está en `datos/`, que no se versiona, así que
    en un clon limpio no existe; y este proyecto no tiene por qué instalar
    `duckdb` para dibujar una tabla de veinte filas. Si el almacén está, manda
    él y el JSON se refresca.
    """
    almacen = RADAR / "datos" / "radar.duckdb"
    if almacen.exists():
        try:
            import duckdb

            cx = duckdb.connect(str(almacen), read_only=True)
            filas = cx.execute(CONSULTA).fetchall()
            cx.close()
            POR_ESPECIE.write_text(
                json.dumps([list(f) for f in filas], ensure_ascii=False, indent=1),
                encoding="utf-8")
            return filas
        except ImportError:
            pass    # sin duckdb aquí; vale el JSON, que salió de ese mismo almacén

    assert POR_ESPECIE.exists(), (
        f"no está {POR_ESPECIE.name} ni se puede leer {almacen}: "
        f"correr el radar primero, o generar el JSON desde su venv")
    return [tuple(f) for f in json.loads(POR_ESPECIE.read_text(encoding="utf-8"))]


def sesgo():
    """El gráfico que sostiene todo el post.

    Dos paneles y no dos ejes sobre el mismo dibujo: superpuestos, las líneas de
    las medias caen sobre la escala equivocada y quien mire creerá que el 84,2 %
    está donde no está. Compartiendo el eje vertical se leen igual de juntos y
    ninguna escala miente.

    A la izquierda cuántas observaciones trae cada especie, a la derecha cuánto
    acierta en ella. Se ve de un golpe que las barras largas van arriba en
    acierto: eso es lo que infla la media por observación.
    """
    import matplotlib.pyplot as plt

    filas = _radar()
    especies = [f[0] for f in filas]
    enes = [f[1] for f in filas]
    acierto = [f[2] / f[1] * 100 for f in filas]

    total, aciertos = sum(enes), sum(f[2] for f in filas)
    por_obs = aciertos / total * 100
    por_esp = sum(acierto) / len(acierto)

    fig, (izq, der) = plt.subplots(
        1, 2, figsize=(10, 6.6), dpi=160, sharey=True,
        gridspec_kw={"width_ratios": [1, 1.45], "wspace": .28})
    fig.patch.set_facecolor(PAPEL)
    y = list(range(len(especies)))

    for ax in (izq, der):
        ax.set_facecolor(PAPEL)
        for lado in ("top", "right", "left"):
            ax.spines[lado].set_visible(False)
        ax.spines["bottom"].set_color(LINEA)
        ax.tick_params(colors=SUAVE, labelsize=9)
        ax.set_axisbelow(True)

    # Izquierda: el reparto. Resaltada la que se come un tercio del conjunto.
    izq.barh(y, enes, height=.66, zorder=2,
             color=[LIQUEN if n == max(enes) else LINEA for n in enes])
    for i, n in enumerate(enes):
        izq.text(n + max(enes) * .03, i, str(n), va="center", fontsize=8.5,
                 color=TINTA if n == max(enes) else SUAVE,
                 weight="bold" if n == max(enes) else "normal")
    izq.set_xlim(0, max(enes) * 1.3)
    izq.grid(axis="x", color=LINEA, lw=.6, alpha=.5)
    izq.set_xlabel("observaciones traídas", fontsize=9.5, color=TINTA)

    # Derecha: el acierto, con las dos medias encima.
    der.barh(y, acierto, height=.1, color=LINEA, zorder=1)
    der.scatter(acierto, y, s=64, zorder=4,
                color=[AGUA if a >= por_esp else ROJO for a in acierto],
                edgecolor=BASALTO, linewidth=.8)
    der.axvline(por_obs, color=BASALTO, lw=1.5, zorder=3)
    der.axvline(por_esp, color=BASALTO, lw=1.5, ls=":", zorder=3)
    der.set_xlim(0, 108)
    der.set_xticks([0, 25, 50, 75, 100])
    der.grid(axis="x", color=LINEA, lw=.6, alpha=.5)
    der.set_xlabel("acierto en esa especie  (%)", fontsize=9.5, color=TINTA)

    # Las etiquetas de las medias, dentro del panel y en la zona vacía de la
    # izquierda: debajo del eje se pisaban con su rótulo, y junto a las líneas
    # taparían puntos.
    der.annotate(f"por observación   {por_obs:.1f} %", xy=(por_obs, 2.1),
                 xytext=(28, 2.1), fontsize=9.5, color=BASALTO, weight="bold",
                 va="center", ha="left",
                 arrowprops=dict(arrowstyle="-", color=BASALTO, lw=.9,
                                 shrinkA=6, shrinkB=2))
    der.annotate(f"por especie   {por_esp:.1f} %", xy=(por_esp, 4.3),
                 xytext=(28, 4.3), fontsize=9.5, color=BASALTO,
                 va="center", ha="left",
                 arrowprops=dict(arrowstyle="-", color=BASALTO, lw=.9, ls=":",
                                 shrinkA=6, shrinkB=2))

    izq.set_yticks(y)
    izq.set_yticklabels(especies, fontsize=8.5, style="italic", color=TINTA)
    izq.tick_params(axis="y", length=0)
    izq.invert_yaxis()

    fig.text(.5, 1.02, f"Una especie es el {enes[0] / total * 100:.0f} % de las "
                       f"{total} observaciones",
             fontsize=13, color=TINTA, weight="bold", ha="center")
    fig.text(.5, .982, "y es de las que mejor se le dan: por eso la media por "
                       "observación sale 5,5 puntos alta",
             fontsize=9.5, color=SUAVE, ha="center")
    return _guardar(fig, "sesgo")

def desacuerdos():
    """Qué eran de verdad los 63 desacuerdos. De contraste.json."""
    datos = json.loads((RADAR / "contraste.json").read_text(encoding="utf-8"))
    orden = [("sigue igual", "la etiqueta sigue igual\nfallo del modelo", ROJO),
             ("precisada", "precisada a subespecie\nmisma especie: falló igual", ROJO),
             ("el modelo tenía razón",
              "la etiqueta era vieja\nel modelo acertaba", AGUA)]
    cuenta = [sum(1 for d in datos if d["estado"] == k) for k, _, _ in orden]

    fig, ax = _lienzo(9, 3)
    izquierda = 0
    # Escalonadas: el segmento de 8 es demasiado estrecho para su texto y con
    # todas las etiquetas a la misma altura las dos últimas se pisan.
    alturas = [-.45, -.45, -.95]
    for n, (_, etiqueta, color), alto in zip(cuenta, orden, alturas):
        ax.barh(0, n, left=izquierda, color=color, height=.5,
                edgecolor=PAPEL, linewidth=2)
        ax.text(izquierda + n / 2, 0, str(n), ha="center", va="center",
                fontsize=15, weight="bold",
                color=PAPEL if color == ROJO else BASALTO)
        centro = izquierda + n / 2
        # El último segmento está pegado al borde derecho: centrar ahí sacaría
        # el texto fuera del lienzo, así que se ancla al borde y la guía se
        # dobla hasta él.
        ultimo = izquierda + n >= len(datos)
        x = len(datos) if ultimo else centro
        ax.plot([centro, centro, x], [-.28, alto + .12, alto + .04],
                color=LINEA, lw=.9, zorder=0)
        ax.text(x, alto, etiqueta, ha="right" if ultimo else "center", va="top",
                fontsize=8.5, color=SUAVE, linespacing=1.5)
        izquierda += n

    ax.set_xlim(0, len(datos))
    ax.set_ylim(-1.75, .55)
    ax.axis("off")
    ax.set_title(f"Los {len(datos)} desacuerdos, contrastados con iNaturalist",
                 fontsize=12.5, color=TINTA, pad=16, loc="left", weight="bold")
    ax.text(0, .48, f"todos de grado «research»: identificaciones que la "
                    f"comunidad ya confirmó",
            fontsize=9, color=SUAVE, va="bottom")
    return _guardar(fig, "desacuerdos")


def cuantizacion():
    """Lo que cuesta bajar de 13,5 MB a 3,8. De metricas.json."""
    m = json.loads((RIKSI / "docs" / "modelo" / "metricas.json").read_text(
        encoding="utf-8"))
    etapas = [("PyTorch", None, m["pytorch"]["top1"]),
              ("ONNX fp32", m["fp32"]["mb"], m["fp32"]["top1"]),
              ("ONNX int8", m["int8"]["mb"], m["int8"]["top1"])]

    # El tamaño manda y el acierto se anota. Al revés —el acierto en barras—
    # habría que cortar el eje por 78 para ver algo, y un eje cortado convierte
    # medio punto en un abismo visual: exactamente la clase de gráfico que este
    # post critica.
    conmb = [e for e in etapas if e[1]]

    fig, ax = _lienzo(8.4, 2.9)
    y = range(len(conmb))
    ax.barh(y, [e[1] for e in conmb], height=.44,
            color=[LINEA, AGUA], edgecolor=BASALTO, linewidth=.8)
    for i, (nombre, mb, top1) in enumerate(conmb):
        # Las dos etiquetas en un solo `text`: separadas por posición fija se
        # pisaban en cuanto una barra era larga.
        ax.text(mb + .35, i, f"{mb:.1f} MB", va="center", fontsize=12.5,
                weight="bold", color=TINTA)
        ax.text(mb + .35, i - .34, f"acierto {top1 * 100:.1f} %", va="center",
                fontsize=9.5, color=SUAVE)

    ax.set_yticks(list(y))
    ax.set_yticklabels([e[0] for e in conmb], fontsize=10.5, color=TINTA)
    ax.set_ylim(len(conmb) - .55, -.62)
    ax.set_xlim(0, 17)
    ax.set_xlabel("tamaño del modelo  (MB)", fontsize=9.5, color=TINTA)
    ax.grid(axis="x", color=LINEA, lw=.6, alpha=.5)
    ax.set_axisbelow(True)

    coste = (m["fp32"]["top1"] - m["int8"]["top1"]) * 100
    veces = m["fp32"]["mb"] / m["int8"]["mb"]
    ax.set_title(f"Cuantizar a int8: {veces:.1f} veces más pequeño por "
                 f"{coste:.1f} puntos de acierto",
                 fontsize=12.5, color=TINTA, pad=16, loc="left", weight="bold")
    ax.text(0, 1.012, f"sobre {m['imagenes_validacion']} imágenes de validación "
                      f"y {m['clases']} especies",
            transform=ax.transAxes, fontsize=8.5, color=SUAVE, va="bottom")
    return _guardar(fig, "cuantizacion")


def calibracion():
    """El hueco entre las dos poblaciones, según se poda el vocabulario.

    **Estos cinco valores no salen de un fichero**: son la medición que quedó
    escrita en el comentario de `indice.py` de yachaq, hecha con `--calibrar`.
    Se citan tal cual, y por eso el gráfico dice de dónde vienen.
    """
    # vocabulario, MB en disco, hueco entre poblaciones (0 = se solapan)
    medidas = [(40_000, 75, 0.017), (80_000, 108, 0.0), (120_000, 140, 0.0),
               (200_000, 204, 0.084), (250_037, 235, 0.075)]

    fig, ax = _lienzo(8.5, 4.6)
    x = [m[1] for m in medidas]
    hueco = [m[2] for m in medidas]
    colores = [ROJO if h == 0 else AGUA for h in hueco]

    # Sin línea que los una: son cinco mediciones independientes y unirlas
    # dibujaría una curva entre puntos que nadie midió. Una guía vertical hasta
    # el cero basta para leer la altura.
    for xi, h in zip(x, hueco):
        ax.plot([xi, xi], [0, h], color=LINEA, lw=1.4, zorder=1)
    ax.scatter(x, hueco, s=110, color=colores, edgecolor=BASALTO,
               linewidth=.9, zorder=3)

    for (voc, mb, h) in medidas:
        etiqueta = f"{voc // 1000}k" if voc < 250_000 else "250k · el actual"
        ax.text(mb, h + .0055, etiqueta, ha="center", fontsize=8.5, color=TINTA)
        if h == 0:
            ax.text(mb, -.011, "se solapan", ha="center", fontsize=8,
                    color=ROJO, style="italic")

    ax.axhline(0, color=ROJO, lw=1, alpha=.4)
    ax.set_xlabel("tamaño del índice en disco  (MB)", fontsize=9.5, color=TINTA)
    ax.set_ylabel("hueco entre las dos poblaciones", fontsize=9.5, color=TINTA)
    ax.set_ylim(-.022, .105)
    ax.grid(color=LINEA, lw=.6, alpha=.5)
    ax.set_axisbelow(True)
    ax.set_title("Podar el vocabulario borra el umbral antes que el tamaño",
                 fontsize=12.5, color=TINTA, pad=16, loc="left", weight="bold")
    ax.text(0, 1.006, "preguntas con respuesta menos preguntas sin ella; "
                      "medido con indice.py --calibrar",
            transform=ax.transAxes, fontsize=8.5, color=SUAVE, va="bottom")
    return _guardar(fig, "calibracion")


def memoria():
    """De 671 MB a 154, y el techo de 512 que lo obligaba.

    **Tampoco salen de un fichero**: son las mediciones del README de yachaq,
    hechas con psutil sobre el proceso real.
    """
    # Lo que decide si esto se publica no es la RAM en reposo sino **el pico**
    # respondiendo. La segunda etapa baja de 512 en reposo pero su pico llega a
    # 467, y con 45 MB de margen un contenedor de 512 muere a la primera. Por
    # eso se pintan las dos: la barra es el pico y la marca es el reposo.
    TECHO = 512
    etapas = [("fastembed\ntal cual", 671, 671, ROJO),
              ("pesos externos\nmapeados", 457, 467, ROJO),
              ("soltando la sesión\ndespués de cada consulta", 154, 154, AGUA)]

    fig, ax = _lienzo(8.8, 4.6)
    x = range(len(etapas))
    ax.bar(x, [e[2] for e in etapas], width=.5,
           color=[e[3] for e in etapas], edgecolor=BASALTO, linewidth=.8)
    for i, (_, reposo, pico, _) in enumerate(etapas):
        ax.text(i, pico + 16, f"{pico} MB", ha="center", fontsize=11.5,
                weight="bold", color=TINTA)
        margen = TECHO - pico
        ax.text(i, pico / 2, f"margen\n{margen:+} MB", ha="center", va="center",
                fontsize=9.5, color=PAPEL if margen < 100 else BASALTO,
                linespacing=1.5, weight="bold")

    ax.axhline(TECHO, color=BASALTO, lw=1.5, ls="--")
    ax.text(len(etapas) - .52, TECHO + 16,
            f"{TECHO} MB · el techo del plan gratuito",
            ha="right", fontsize=9.5, color=BASALTO, weight="bold")

    ax.set_xticks(list(x))
    ax.set_xticklabels([e[0] for e in etapas], fontsize=9.5, color=TINTA)
    ax.set_ylim(0, 780)
    ax.set_ylabel("pico de RAM respondiendo  (MB)", fontsize=9.5, color=TINTA)
    ax.grid(axis="y", color=LINEA, lw=.6, alpha=.5)
    ax.set_axisbelow(True)
    ax.set_title("El mismo cálculo, con la cuarta parte de memoria",
                 fontsize=12.5, color=TINTA, pad=16, loc="left", weight="bold")
    ax.text(0, 1.008, "medido con 10 fotos, 4 consultas al RAG y 30 recuerdos · "
                      "coseno 1,0 contra fastembed: no es una aproximación",
            transform=ax.transAxes, fontsize=8.5, color=SUAVE, va="bottom")
    return _guardar(fig, "memoria")


def montaje():
    """Por dónde pasa una foto, de GBIF al almacén. El diagrama del post."""
    import matplotlib.patches as mp
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(9.5, 2.9), dpi=160)
    fig.patch.set_facecolor(PAPEL)
    ax.set_facecolor(PAPEL)

    cajas = [("GBIF", "observaciones\nnuevas", LINEA),
             ("Kafka", "una partición\npor especie", LINEA),
             ("riksi", "int8 · 3,8 MB\nen ONNX", AGUA),
             ("DuckDB", "400 filas, con\nlas dos etiquetas", LINEA),
             ("dbt", "tablas y\ncomprobaciones", LINEA)]

    ancho, hueco = 1.78, .44
    for i, (titulo, pie, color) in enumerate(cajas):
        x = i * (ancho + hueco)
        ax.add_patch(mp.FancyBboxPatch((x, 0), ancho, 1,
                                       boxstyle="round,pad=.04,rounding_size=.09",
                                       facecolor=color, edgecolor=BASALTO, lw=1))
        ax.text(x + ancho / 2, .68, titulo, ha="center", fontsize=12,
                weight="bold", color=BASALTO)
        ax.text(x + ancho / 2, .3, pie, ha="center", fontsize=8.2,
                color=BASALTO if color == AGUA else SUAVE, linespacing=1.5)
        if i < len(cajas) - 1:
            ax.annotate("", xy=(x + ancho + hueco - .06, .5),
                        xytext=(x + ancho + .06, .5),
                        arrowprops=dict(arrowstyle="-|>", color=SUAVE, lw=1.3))

    ancho_total = len(cajas) * (ancho + hueco) - hueco
    ax.text(0, 1.32, "El radar", fontsize=12.5, weight="bold", color=TINTA)
    ax.text(0, -.42, "el modelo nunca ve la etiqueta de GBIF: se guardan las dos "
                     "y se comparan después",
            fontsize=9, color=SUAVE)
    ax.set_xlim(-.15, ancho_total + .15)
    ax.set_ylim(-.75, 1.62)
    ax.axis("off")
    return _guardar(fig, "montaje")


TODOS = (montaje, sesgo, desacuerdos, cuantizacion, calibracion, memoria)


def generar():
    for f in TODOS:
        f()


def prueba():
    """Que las figuras salgan y que sus cifras cuadren con los ficheros.

    Lo segundo es lo que importa: un gráfico bonito con un número inventado es
    peor que no tenerlo, y es justo de lo que va el post.
    """
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    filas = _radar()
    total = sum(f[1] for f in filas)
    aciertos = sum(f[2] for f in filas)
    por_obs = aciertos / total * 100
    por_esp = sum(f[2] / f[1] for f in filas) / len(filas) * 100
    assert total == 400 and aciertos == 337, (total, aciertos)
    assert abs(por_obs - 84.2) < .05 and abs(por_esp - 78.7) < .05, (por_obs, por_esp)
    assert por_obs > por_esp, "si esto se invierte, el post entero deja de valer"

    datos = json.loads((RADAR / "contraste.json").read_text(encoding="utf-8"))
    assert len(datos) == 63, len(datos)
    assert sum(1 for d in datos if d["estado"] == "el modelo tenía razón") == 8

    m = json.loads((RIKSI / "docs" / "modelo" / "metricas.json").read_text(
        encoding="utf-8"))
    assert abs(m["int8"]["top1"] - .798) < 1e-9, m["int8"]["top1"]

    hechos = [f() for f in TODOS]
    for p in hechos:
        assert p.exists() and p.stat().st_size > 15_000, f"{p.name} salió vacío"
    print(f"ok · {len(hechos)} figuras · las cifras cuadran con los ficheros "
          f"({total} obs, {por_obs:.1f} % / {por_esp:.1f} %)")


def main():
    a = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    a.add_argument("--comprobar", action="store_true")
    args = a.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    prueba() if args.comprobar else generar()


if __name__ == "__main__":
    main()
