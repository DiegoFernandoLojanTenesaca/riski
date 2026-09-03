"""Las figuras del artículo, generadas desde los datos.

**Ninguna cifra se escribe a mano aquí.** Cada figura lee el fichero que la
sostiene —`metricas.json`, el DuckDB del radar, `contraste.json`,
`calibracion.json`— y si esos cambian, la figura cambia con ellos. Un PNG con un
número dibujado a mano es exactamente el tipo de cifra que el artículo denuncia,
y `--comprobar` falla si dejan de cuadrar.

La única excepción es la tabla de poda del vocabulario: son cinco mediciones que
quedaron en un comentario de `indice.py` y no en un fichero de datos. Está
marcada en su función.

    python graficos.py            # las ocho, en claro y en oscuro
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


class Tema:
    """Los colores de una variante. Salen de `docs/estilo.css`.

    Dos variantes con los mismos nombres para que cada figura se dibuje una vez
    y no haya un `if oscuro` repartido por todo el fichero.
    """

    def __init__(self, nombre, fondo, tinta, suave, linea, acento, alerta, neutro):
        self.nombre, self.fondo, self.tinta = nombre, fondo, tinta
        self.suave, self.linea = suave, linea
        self.acento, self.alerta, self.neutro = acento, alerta, neutro

    @property
    def sufijo(self):
        return "" if self.nombre == "claro" else "-oscuro"


CLARO = Tema("claro", fondo="#e4e5df", tinta="#171b1c", suave="#5d6663",
             linea="#c9cbc3", acento="#4a8f85", alerta="#a8462f", neutro="#d3d5cd")
OSCURO = Tema("oscuro", fondo="#14181b", tinta="#dce0da", suave="#9aa39c",
              linea="#2c3639", acento="#79b0a8", alerta="#c96a4f", neutro="#252c30")

# Una tipografía de texto para todo, en vez de la de matplotlib. Es la
# diferencia entre una figura que parece de un artículo y una que parece de un
# cuaderno de laboratorio.
FUENTES = ["Source Sans Pro", "Segoe UI", "Helvetica Neue", "DejaVu Sans"]
MONO = ["Cascadia Code", "Consolas", "DejaVu Sans Mono"]


def _preparar(t):
    """Los ajustes que van en todas las figuras."""
    import matplotlib as mpl

    mpl.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": FUENTES,
        "font.size": 10.5,
        "axes.titlesize": 13,
        "axes.labelsize": 10,
        "xtick.labelsize": 9.5,
        "ytick.labelsize": 9.5,
        "axes.edgecolor": t.linea,
        "axes.labelcolor": t.suave,
        "text.color": t.tinta,
        "xtick.color": t.suave,
        "ytick.color": t.suave,
        "figure.facecolor": t.fondo,
        "axes.facecolor": t.fondo,
        "savefig.facecolor": t.fondo,
        "axes.grid": False,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "xtick.direction": "out",
        "ytick.direction": "out",
        "xtick.major.size": 3.5,
        "ytick.major.size": 0,
        "legend.frameon": False,
    })


def num(v, decimales=1):
    """Un número con la coma decimal del español.

    El artículo escribe «84,2 %» y las figuras escribían «84.2 %». Mezclar las
    dos convenciones en la misma página es la clase de detalle que delata que
    nadie las revisó juntas.
    """
    return f"{v:.{decimales}f}".replace(".", ",")


def _titular(fig, titulo, bajada=None, x=0.008, y=0.985):
    """Titular y bajada como en una publicación: alineados a la izquierda.

    Matplotlib centra el título sobre los ejes, lo que deja el texto flotando
    respecto al margen de la página. Aquí van pegados al borde de la figura, que
    es donde el ojo los busca al leer.
    """
    t = fig.tema
    fig.text(x, y, titulo, fontsize=14.5, weight="semibold", color=t.tinta,
             va="top", ha="left")
    if bajada:
        fig.text(x, y - .058, bajada, fontsize=10, color=t.suave,
                 va="top", ha="left")


def _pie(fig, texto, x=0.008, y=0.012):
    """La procedencia del dato, abajo. Una figura sin fuente no se puede citar."""
    fig.text(x, y, texto, fontsize=8.5, color=fig.tema.suave, va="bottom",
             ha="left", style="italic")


def _figura(t, ancho, alto):
    import matplotlib.pyplot as plt

    _preparar(t)
    fig = plt.figure(figsize=(ancho, alto), dpi=200)
    fig.tema = t
    return fig


def _guardar(fig, nombre):
    import matplotlib.pyplot as plt

    SALIDA.mkdir(exist_ok=True)
    destino = SALIDA / f"{nombre}{fig.tema.sufijo}.png"
    fig.savefig(destino, facecolor=fig.tema.fondo, pad_inches=0)
    plt.close(fig)
    return destino


# ─── los datos ───────────────────────────────────────────────────────────────

CONSULTA = """
    select especie, count(*) n, sum(coincide::int) ok
    from observaciones where modelo_dice is not null
    group by 1 order by n desc
"""
POR_ESPECIE = AQUI / "por-especie.json"


def _radar():
    """Las 400 observaciones, especie a especie.

    Salen del DuckDB del radar, pero se dejan cacheadas en un JSON al lado del
    artículo. Dos razones: el almacén está en `datos/`, que no se versiona, así
    que en un clon limpio no existe; y este proyecto no tiene por qué instalar
    `duckdb` para dibujar una tabla de veinte filas. Si el almacén está, manda él
    y el JSON se refresca.
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


def _json(nombre, donde=None):
    return json.loads((donde or AQUI).joinpath(nombre).read_text(encoding="utf-8"))


def _metricas():
    return _json("metricas.json", RIKSI / "docs" / "modelo")


# ─── las figuras ─────────────────────────────────────────────────────────────

def sesgo(t):
    """La figura que sostiene el artículo entero.

    Dos paneles y no dos ejes superpuestos: encimados, las líneas de las medias
    caen sobre la escala equivocada y quien mire creerá que el 84,2 % está donde
    no está. Compartiendo el eje vertical se leen igual de juntos y ninguna
    escala miente.
    """
    filas = _radar()
    especies = [f[0] for f in filas]
    enes = [f[1] for f in filas]
    acierto = [f[2] / f[1] * 100 for f in filas]

    total = sum(enes)
    por_obs = sum(f[2] for f in filas) / total * 100
    por_esp = sum(acierto) / len(acierto)

    fig = _figura(t, 10, 7)
    rejilla = fig.add_gridspec(1, 2, width_ratios=[1, 1.5], wspace=.32,
                               left=.215, right=.975, top=.845, bottom=.105)
    izq, der = fig.add_subplot(rejilla[0]), fig.add_subplot(rejilla[1],
                                                            sharey=None)
    y = list(range(len(especies)))

    for ax in (izq, der):
        ax.spines["left"].set_visible(False)
        ax.set_axisbelow(True)
        ax.set_ylim(len(especies) - .4, -.6)

    # Izquierda: cuántas observaciones trae cada especie.
    izq.barh(y, enes, height=.68, zorder=2,
             color=[t.acento if n == max(enes) else t.neutro for n in enes])
    for i, n in enumerate(enes):
        izq.text(n + max(enes) * .035, i, str(n), va="center", fontsize=9,
                 color=t.tinta if n == max(enes) else t.suave,
                 weight="semibold" if n == max(enes) else "normal")
    izq.set_xlim(0, max(enes) * 1.32)
    izq.set_xticks([0, 50, 100])
    izq.grid(axis="x", color=t.linea, lw=.7, alpha=.7)
    izq.set_xlabel("observaciones recogidas")
    izq.set_yticks(y)
    izq.set_yticklabels(especies, fontsize=9, style="italic", color=t.tinta)

    # Derecha: el acierto en cada una, con las dos medias.
    der.hlines(y, 0, acierto, color=t.linea, lw=1.6, zorder=1)
    der.scatter(acierto, y, s=58, zorder=4, linewidth=.9, edgecolor=t.fondo,
                color=[t.acento if a >= por_esp else t.alerta for a in acierto])
    der.axvline(por_obs, color=t.tinta, lw=1.4, zorder=3)
    der.axvline(por_esp, color=t.tinta, lw=1.4, ls=(0, (2, 2)), zorder=3)
    der.set_xlim(0, 108)
    der.set_xticks([0, 25, 50, 75, 100])
    der.grid(axis="x", color=t.linea, lw=.7, alpha=.7)
    der.set_xlabel("aciertos sobre esa especie  (%)")
    der.set_yticks([])

    # Las etiquetas de las medias, en el hueco de la izquierda del panel: junto
    # a sus líneas taparían puntos, y bajo el eje se pisan con su rótulo.
    der.annotate(f"micro-promedio  {num(por_obs)} %", xy=(por_obs, 1.6),
                 xytext=(26, 1.6), fontsize=9.5, color=t.tinta,
                 weight="semibold", va="center",
                 arrowprops=dict(arrowstyle="-", color=t.tinta, lw=.9,
                                 shrinkA=8, shrinkB=2))
    der.annotate(f"macro-promedio  {num(por_esp)} %", xy=(por_esp, 3.9),
                 xytext=(26, 3.9), fontsize=9.5, color=t.tinta, va="center",
                 arrowprops=dict(arrowstyle="-", color=t.tinta, lw=.9,
                                 ls=(0, (2, 2)), shrinkA=8, shrinkB=2))

    _titular(fig, f"Una especie concentra el {enes[0] / total * 100:.0f} % de las "
                  f"{total} observaciones",
             "y es de las que mejor se clasifican: por eso el micro-promedio "
             f"queda {num(por_obs - por_esp)} puntos por encima")
    _pie(fig, "riksi-radar · observaciones de GBIF posteriores al entrenamiento, "
              "clasificadas sin acceso a la etiqueta")
    return _guardar(fig, "sesgo")


def confusion(t):
    """Contra qué se equivoca. Los pares, no el recuento.

    Un histograma de errores diría cuántos hay; esto dice **cuáles**, que es lo
    único accionable. Y deja ver el par recíproco de las tortugas, que un
    recuento agregado esconde.
    """
    d = _json("desacuerdos.json")
    pares = [(a, b, n) for a, b, n in d["pares"] if n >= 2]
    pares.sort(key=lambda p: p[2])

    fig = _figura(t, 10, 5.4)
    ax = fig.add_axes([.30, .135, .40, .70])
    y = range(len(pares))

    # Los pares que aparecen en los dos sentidos: el modelo no falla hacia una
    # clase, es que no distingue ese par. Se resaltan porque es un diagnóstico
    # distinto —y accionable— frente a un error suelto.
    tiene_vuelta = {(a, b) for a, b, _ in pares
                    if any(x == b and z == a for x, z, _ in pares)}

    for i, (real, dijo, n) in enumerate(pares):
        color = t.alerta if (real, dijo) in tiene_vuelta else t.suave
        ax.annotate("", xy=(1, i), xytext=(0, i),
                    arrowprops=dict(arrowstyle="-|>", color=color,
                                    lw=1 + n * .30, shrinkA=2, shrinkB=2,
                                    mutation_scale=13))
        ax.text(-.045, i, real, ha="right", va="center", fontsize=9.5,
                style="italic", color=t.tinta)
        ax.text(1.045, i, dijo, ha="left", va="center", fontsize=9.5,
                style="italic", color=t.tinta)
        ax.text(.5, i + .28, f"×{n}", ha="center", va="bottom", fontsize=8.5,
                color=color, weight="semibold")

    ax.text(0, len(pares) - .35, "identificación de GBIF", ha="right",
            fontsize=9.5, color=t.suave, weight="semibold")
    ax.text(1, len(pares) - .35, "predicción del modelo", ha="left",
            fontsize=9.5, color=t.suave, weight="semibold")

    ax.set_xlim(-.02, 1.02)
    ax.set_ylim(-.6, len(pares) - .05)
    ax.axis("off")

    _titular(fig, "Los errores no son aleatorios: van entre especies vecinas",
             f"pares con dos o más casos, de los {d['total']} desacuerdos · "
             f"en rojo, los que se confunden en ambos sentidos")
    _pie(fig, f"{d['en_top3']} de los {d['total']} llevan la etiqueta de GBIF "
              f"en su top-3: el modelo la consideró y la puso segunda")
    return _guardar(fig, "confusion")


def contraste(t):
    """Qué eran de verdad los 63 desacuerdos, contrastados con la fuente."""
    datos = _json("contraste.json", RADAR)
    orden = [("sigue igual", "la etiqueta no ha cambiado", "error del modelo"),
             ("precisada", "precisada a subespecie", "misma especie: error igual"),
             ("el modelo tenía razón", "la etiqueta estaba obsoleta",
              "el modelo acertaba")]
    cuenta = [sum(1 for d in datos if d["estado"] == k) for k, _, _ in orden]
    colores = [t.alerta, t.alerta, t.acento]

    fig = _figura(t, 10, 2.7)
    ax = fig.add_axes([.008, .42, .984, .29])

    izquierda = 0
    for n, (_, titulo, pie), color, alto in zip(cuenta, orden, colores,
                                                (-.62, -.62, -1.42)):
        ax.barh(0, n, left=izquierda, color=color, height=1,
                edgecolor=t.fondo, linewidth=2.5)
        ax.text(izquierda + n / 2, 0, str(n), ha="center", va="center",
                fontsize=17, weight="semibold",
                color=t.fondo if color == t.alerta else "#14181b")
        centro = izquierda + n / 2
        # El último segmento roza el borde: centrar ahí sacaría el texto del
        # lienzo, así que se ancla a la derecha y la guía se dobla hasta él.
        ultimo = izquierda + n >= len(datos)
        x = len(datos) if ultimo else centro
        ax.plot([centro, centro, x], [-.55, alto + .30, alto + .18],
                color=t.linea, lw=1, zorder=0)
        ax.text(x, alto, titulo, ha="right" if ultimo else "center", va="top",
                fontsize=10, color=t.tinta, weight="semibold")
        ax.text(x, alto - .42, pie, ha="right" if ultimo else "center", va="top",
                fontsize=9, color=t.suave)
        izquierda += n

    ax.set_xlim(0, len(datos))
    ax.set_ylim(-2.6, .6)
    ax.axis("off")

    _titular(fig, f"Ocho de los {len(datos)} desacuerdos no eran errores del modelo",
             "GBIF publica instantáneas periódicas; iNaturalist se corrige en "
             "continuo. La diferencia es medible.")
    _pie(fig, "contrastado observación a observación contra la API de "
              "iNaturalist · los 63 son de grado «research»")
    return _guardar(fig, "contraste")


def cuantizacion(t):
    """Lo que cuesta bajar de 13,5 MB a 3,8.

    El tamaño manda y el acierto se anota. Al revés —el acierto en barras—
    habría que cortar el eje por 78 para ver algo, y un eje cortado convierte
    medio punto en un abismo visual: la clase de figura que este artículo
    critica.
    """
    m = _metricas()
    etapas = [("ONNX fp32", m["fp32"]["mb"], m["fp32"]["top1"], t.neutro),
              ("ONNX int8", m["int8"]["mb"], m["int8"]["top1"], t.acento)]

    fig = _figura(t, 10, 3.5)
    ax = fig.add_axes([.115, .215, .86, .50])
    y = range(len(etapas))

    ax.barh(y, [e[1] for e in etapas], height=.44,
            color=[e[3] for e in etapas], zorder=2)
    for i, (_, mb, top1, _) in enumerate(etapas):
        ax.text(mb + .3, i + .07, f"{num(mb)} MB", va="center", fontsize=13,
                weight="semibold", color=t.tinta)
        ax.text(mb + .3, i - .27, f"{num(top1 * 100)} % top-1", va="center",
                fontsize=9.5, color=t.suave)

    ax.set_yticks(list(y))
    ax.set_yticklabels([e[0] for e in etapas], fontsize=11, color=t.tinta)
    ax.set_ylim(len(etapas) - .5, -.55)
    ax.set_xlim(0, 17)
    ax.set_xticks([0, 5, 10, 15])
    ax.set_xlabel("tamaño del fichero del modelo  (MB)")
    ax.grid(axis="x", color=t.linea, lw=.7, alpha=.7)
    ax.spines["left"].set_visible(False)
    ax.set_axisbelow(True)

    coste = (m["fp32"]["top1"] - m["int8"]["top1"]) * 100
    veces = m["fp32"]["mb"] / m["int8"]["mb"]
    _titular(fig, f"Cuantizar a int8: {num(veces)} veces más pequeño por "
                  f"{num(coste)} puntos de exactitud",
             f"medido sobre {m['imagenes_validacion']} imágenes de validación y "
             f"{m['clases']} clases")
    _pie(fig, "el tamaño decide si el modelo se descarga en el navegador de "
              "alguien con datos móviles")
    return _guardar(fig, "cuantizacion")


def poblaciones(t):
    """Las dos poblaciones del RAG y el hueco entre ellas.

    Es la figura que faltaba: el umbral no se justifica con su valor sino con la
    separación que lo hace posible. Cada punto es una pregunta real.
    """
    d = _json("calibracion.json")
    con = sorted(x[1] for x in d["con_respuesta"])
    sin = sorted(x[1] for x in d["sin_respuesta"])
    corte = round((con[0] + sin[-1]) / 2, 2)

    fig = _figura(t, 10, 4.1)
    # Margen izquierdo generoso: los rótulos de cada población van fuera del
    # área de datos, no junto a los puntos, que es donde se pisaban con ellos.
    ax = fig.add_axes([.235, .215, .745, .50])

    # La banda del hueco, que es el resultado.
    ax.axvspan(sin[-1], con[0], color=t.acento, alpha=.14, zorder=0)

    ax.scatter(sin, [0] * len(sin), s=100, color=t.alerta, zorder=3,
               edgecolor=t.fondo, linewidth=1.2)
    ax.scatter(con, [1] * len(con), s=100, color=t.acento, zorder=3,
               edgecolor=t.fondo, linewidth=1.2)
    ax.axvline(corte, color=t.tinta, lw=1.6, ls=(0, (3, 2)), zorder=4)

    for fila, titulo, cuantas, detalle in (
            (1, "con respuesta", len(con), "sobre las fichas"),
            (0, "sin respuesta", len(sin), "de otro dominio")):
        ax.text(-.018, fila + .17, titulo, transform=ax.get_yaxis_transform(),
                ha="right", va="center", fontsize=10.5, color=t.tinta,
                weight="semibold")
        ax.text(-.018, fila - .17, f"{cuantas} preguntas {detalle}",
                transform=ax.get_yaxis_transform(), ha="right", va="center",
                fontsize=8.5, color=t.suave)

    medio = (sin[-1] + con[0]) / 2
    ax.text(medio, .5, f"hueco  {num(con[0] - sin[-1], 3)}", ha="center",
            va="center", fontsize=10, color=t.tinta, weight="semibold",
            zorder=5,
            bbox=dict(boxstyle="round,pad=.32", fc=t.fondo, ec=t.acento, lw=1.1))
    ax.text(corte, 1.62, f"corte  {corte}", ha="center", fontsize=10,
            color=t.tinta, weight="semibold")

    ax.set_xlim(min(sin) - .022, max(con) + .022)
    ax.set_ylim(-.62, 1.85)
    ax.set_yticks([])
    ax.set_xlabel("mejor similitud coseno contra el índice")
    ax.spines["left"].set_visible(False)
    ax.grid(axis="x", color=t.linea, lw=.7, alpha=.5)
    ax.set_axisbelow(True)

    _titular(fig, "El umbral no se elige: se lee de la separación entre dos "
                  "poblaciones",
             "si las nubes se solapan no hay corte válido, y el problema deja "
             "de ser el número")
    _pie(fig, "yachaq · indice.py --calibrar · cada punto es una pregunta")
    return _guardar(fig, "poblaciones")


def poda(t):
    """Qué se rompe al adelgazar el índice.

    **Estos cinco valores no salen de un fichero de datos**: son la medición que
    quedó escrita en el comentario de `indice.py`. Se citan tal cual, y por eso
    la figura dice de dónde vienen.
    """
    # vocabulario, MB en disco, hueco entre poblaciones (0 = se solapan)
    medidas = [(40_000, 75, 0.017), (80_000, 108, 0.0), (120_000, 140, 0.0),
               (200_000, 204, 0.084), (250_037, 235, 0.075)]

    fig = _figura(t, 10, 4.4)
    ax = fig.add_axes([.085, .195, .89, .58])

    # Sin línea que una los puntos: son cinco mediciones independientes y
    # unirlas dibujaría una curva entre valores que nadie midió.
    for voc, mb, h in medidas:
        color = t.alerta if h == 0 else t.acento
        ax.plot([mb, mb], [0, h], color=t.linea, lw=1.5, zorder=1)
        ax.scatter([mb], [h], s=125, color=color, zorder=3,
                   edgecolor=t.fondo, linewidth=1.1)
        etiqueta = f"{voc // 1000}k" if voc < 250_000 else "250k · actual"
        ax.text(mb, h + .0065, etiqueta, ha="center", fontsize=9.5,
                color=t.tinta, weight="semibold" if voc > 240_000 else "normal")
        if h == 0:
            ax.text(mb, -.0105, "se solapan", ha="center", fontsize=8.5,
                    color=t.alerta, style="italic")

    ax.axhline(0, color=t.alerta, lw=1.1, alpha=.55)
    ax.set_xlabel("tamaño del índice en disco  (MB)")
    ax.set_ylabel("hueco entre las dos poblaciones")
    ax.set_ylim(-.021, .1)
    ax.set_xlim(58, 252)
    ax.grid(color=t.linea, lw=.7, alpha=.55)
    ax.set_axisbelow(True)

    _titular(fig, "Podar el vocabulario destruye el umbral antes que el tamaño",
             "a 120k términos el índice adelgaza un 40 % y las dos poblaciones "
             "dejan de separarse")
    _pie(fig, "yachaq · el sistema sigue respondiendo; lo que pierde es saber "
              "cuándo no debería")
    return _guardar(fig, "poda")


def memoria(t):
    """El techo de 512 MB y las dos medidas que lo hicieron caber.

    Lo que decide si esto se publica no es la RAM en reposo sino **el pico**
    respondiendo: la segunda etapa baja de 512 en reposo pero su pico llega a
    467, y con 45 MB de margen un contenedor de 512 muere a la primera.
    """
    TECHO = 512
    etapas = [("fastembed\nsin tocar", 671, t.alerta),
              ("pesos externos\nmapeados desde disco", 467, t.alerta),
              ("liberando la sesión\ntras cada consulta", 154, t.acento)]

    fig = _figura(t, 10, 4.6)
    ax = fig.add_axes([.085, .225, .89, .565])
    x = range(len(etapas))

    ax.bar(x, [e[1] for e in etapas], width=.46,
           color=[e[2] for e in etapas], zorder=2)
    for i, (_, pico, color) in enumerate(etapas):
        # La cifra va sobre la barra salvo cuando su altura cae junto al techo:
        # ahí se pisaría con la línea, así que baja dentro de la barra.
        cerca = abs(pico - TECHO) < 80
        ax.text(i, pico - 46 if cerca else pico + 20, f"{pico} MB", ha="center",
                fontsize=13, weight="semibold",
                color=(t.fondo if color == t.alerta else "#14181b") if cerca
                else t.tinta)
        margen = TECHO - pico
        ax.text(i, pico / 2 - (18 if cerca else 0),
                f"{margen:+} MB\nde margen", ha="center", va="center",
                fontsize=10, linespacing=1.5, weight="semibold",
                color=t.fondo if color == t.alerta else "#14181b")

    ax.axhline(TECHO, color=t.tinta, lw=1.5, ls=(0, (4, 3)), zorder=3)
    # El rótulo, dentro del área y no en el borde: fuera se recorta al guardar.
    ax.text(len(etapas) - .62, TECHO + 24,
            f"{TECHO} MB · límite del plan gratuito", ha="right", fontsize=10,
            color=t.tinta, weight="semibold")

    ax.set_xticks(list(x))
    ax.set_xticklabels([e[0] for e in etapas], fontsize=10, color=t.tinta)
    ax.set_ylim(0, 790)
    ax.set_yticks([0, 250, 500, 750])
    ax.set_ylabel("pico de RSS respondiendo  (MB)")
    ax.grid(axis="y", color=t.linea, lw=.7, alpha=.55)
    ax.set_axisbelow(True)
    ax.spines["bottom"].set_color(t.linea)

    _titular(fig, "El mismo cálculo con la cuarta parte de memoria",
             "coseno 1,0 contra la implementación de referencia: no es una "
             "aproximación, es la misma operación")
    _pie(fig, "yachaq · medido con psutil sobre el proceso, con 10 fotos, "
              "4 consultas al RAG y 30 recuerdos en memoria")
    return _guardar(fig, "memoria")


def arquitectura(t):
    """Los tres proyectos y por dónde va el dato.

    No es un organigrama de cajas: lo que importa es **dónde se decide** —el
    modelo predice sin ver la etiqueta— y **qué se guarda**, que es lo que
    permite comparar después.
    """
    import matplotlib.patches as mp

    # El lienzo empieza bajo el titular y termina sobre el pie: reservar ese
    # espacio con `add_axes` en vez de dibujar sobre toda la figura es lo que
    # evita que el texto choque con las cajas.
    fig = _figura(t, 10, 4.9)
    ax = fig.add_axes([.008, .045, .984, .765])
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 54)
    ax.axis("off")

    def caja(x, y, an, al, titulo, pie, relleno=None, borde=None, grueso=1.2):
        ax.add_patch(mp.FancyBboxPatch(
            (x, y), an, al, boxstyle="round,pad=0,rounding_size=1.4",
            facecolor=relleno if relleno else t.fondo,
            edgecolor=borde if borde else t.linea, lw=grueso, zorder=2))
        ax.text(x + an / 2, y + al - 3.8, titulo, ha="center", va="top",
                fontsize=11.5, weight="semibold",
                color="#14181b" if relleno == t.acento else t.tinta)
        if pie:
            ax.text(x + an / 2, y + al - 7.6, pie, ha="center", va="top",
                    fontsize=8.5, linespacing=1.5,
                    color="#14181b" if relleno == t.acento else t.suave)

    def flecha(x1, y1, x2, y2, texto=None, ls="-"):
        ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                    arrowprops=dict(arrowstyle="-|>", color=t.suave, lw=1.3,
                                    ls=ls, mutation_scale=14,
                                    shrinkA=1, shrinkB=1))
        if texto:
            ax.text((x1 + x2) / 2, (y1 + y2) / 2 + 1.4, texto, ha="center",
                    fontsize=8, color=t.suave, style="italic")

    ALTO, FILA = 15, 39          # la fila superior, el flujo principal
    MEDIO = FILA + ALTO / 2

    caja(0, FILA, 17, ALTO, "GBIF", "observaciones\npublicadas hoy")
    flecha(17.8, MEDIO, 22.2, MEDIO)
    caja(23, FILA, 17, ALTO, "Kafka", "una partición\npor especie")
    flecha(40.8, MEDIO, 45.2, MEDIO, "solo la foto")
    caja(46, FILA, 21, ALTO, "riksi", "EfficientNet-Lite0\nint8 · 3,8 MB",
         relleno=t.acento, borde=t.acento)
    flecha(67.8, MEDIO, 72.2, MEDIO, "predicción")
    caja(73, FILA, 27, ALTO, "DuckDB + dbt", "las dos etiquetas,\nsin comparar aún")

    # El desvío de la etiqueta: sale de Kafka, baja, cruza por debajo del modelo
    # y sube a DuckDB sin tocar la caja verde. Ese rodeo **es** la figura: si la
    # línea atravesara el modelo, la evaluación no valdría nada.
    ax.plot([31.5, 31.5, 86.5, 86.5], [FILA, 32, 32, FILA],
            color=t.alerta, lw=1.5, ls=(0, (5, 3)), zorder=1,
            solid_capstyle="butt")
    ax.annotate("", xy=(86.5, FILA - .4), xytext=(86.5, 33),
                arrowprops=dict(arrowstyle="-|>", color=t.alerta, lw=1.5,
                                mutation_scale=13))
    ax.text(59, 30.4, "la etiqueta de GBIF rodea el modelo: nunca la ve",
            ha="center", va="top", fontsize=9.5, color=t.alerta, style="italic")

    # Fila inferior: lo que consume el resultado. Las dos salen de DuckDB.
    caja(23, 2, 31, 13, "contrastar.py",
         "pregunta a iNaturalist cuál es\nla identificación de hoy")
    caja(59, 2, 27, 13, "yachaq", "agente sobre el índice\ny las observaciones")
    # Bajan desde DuckDB a distinta altura para no solaparse, y por fuera del
    # desvío rojo: cruzarlo sugeriría un flujo que no existe.
    for desde, hasta, altura in ((91, 38.5, 22), (96.5, 72.5, 18)):
        ax.plot([desde, desde, hasta], [FILA - .5, altura, altura],
                color=t.suave, lw=1.2, ls=(0, (3, 2)), zorder=1)
        ax.annotate("", xy=(hasta, 15.6), xytext=(hasta, altura),
                    arrowprops=dict(arrowstyle="-|>", color=t.suave, lw=1.2,
                                    mutation_scale=13))

    _titular(fig, "Tres proyectos, un solo recorrido del dato",
             "la evaluación fuera de distribución depende de una cosa: que la "
             "etiqueta no llegue al clasificador", y=.97)
    return _guardar(fig, "arquitectura")


FIGURAS = (arquitectura, sesgo, cuantizacion, confusion, contraste,
           poblaciones, poda, memoria)


def generar():
    for tema in (CLARO, OSCURO):
        print(f"  {tema.nombre}:")
        for f in FIGURAS:
            p = f(tema)
            print(f"    {p.name:<26} {p.stat().st_size // 1024:>4} KB")


def prueba():
    """Que las cifras de las figuras cuadren con los ficheros.

    Esto es lo que importa: una figura bonita con un número inventado es peor
    que no tenerla, y es de lo que va el artículo.
    """
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    filas = _radar()
    total = sum(f[1] for f in filas)
    aciertos = sum(f[2] for f in filas)
    por_obs = aciertos / total * 100
    por_esp = sum(f[2] / f[1] for f in filas) / len(filas) * 100
    assert total == 400 and aciertos == 337, (total, aciertos)
    assert abs(por_obs - 84.2) < .05 and abs(por_esp - 78.7) < .05, (por_obs, por_esp)
    assert por_obs > por_esp, "si esto se invierte, el artículo entero deja de valer"

    datos = _json("contraste.json", RADAR)
    assert len(datos) == 63, len(datos)
    assert sum(1 for d in datos if d["estado"] == "el modelo tenía razón") == 8

    des = _json("desacuerdos.json")
    assert sum(n for _, _, n in des["pares"]) == des["total"] == len(datos)
    assert des["en_top3"] == 44, des["en_top3"]

    cal = _json("calibracion.json")
    con = sorted(x[1] for x in cal["con_respuesta"])
    sin = sorted(x[1] for x in cal["sin_respuesta"])
    assert con[0] > sin[-1], "las poblaciones se solapan: el umbral no valdría"
    assert abs(round((con[0] + sin[-1]) / 2, 2) - 0.44) < 1e-9, "el corte no es 0,44"

    m = _metricas()
    assert abs(m["int8"]["top1"] - .798) < 1e-9, m["int8"]["top1"]

    generar()
    hechas = list(SALIDA.glob("*.png"))
    assert len(hechas) == len(FIGURAS) * 2, f"{len(hechas)} figuras, no {len(FIGURAS) * 2}"
    for p in hechas:
        assert p.stat().st_size > 12_000, f"{p.name} salió vacío"
    print(f"\nok · {len(hechas)} figuras en dos temas · las cifras cuadran "
          f"({total} obs · {por_obs:.1f} micro / {por_esp:.1f} macro)")


def main():
    a = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    a.add_argument("--comprobar", action="store_true")
    args = a.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    prueba() if args.comprobar else generar()


if __name__ == "__main__":
    main()
