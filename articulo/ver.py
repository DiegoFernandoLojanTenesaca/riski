"""Convierte el post a HTML para leerlo y para imprimirlo a PDF.

**Sin dependencias.** El post usa seis cosas de Markdown —titulares, tablas,
bloques de código, cita, negrita y enlaces— y traerse un paquete entero para eso
son 40 líneas de conversor contra una dependencia que hay que instalar en
cualquier máquina donde se quiera releer el texto. Si el post creciera hasta
necesitar Markdown de verdad, entonces sí toca `pip install markdown`.

El PDF sale del navegador: Ctrl+P → «Guardar como PDF». La hoja de estilo ya
trae las reglas de impresión, así que no hace falta ni wkhtmltopdf ni un Chrome
headless, que en Windows son media hora de pelea por un fichero que se genera en
dos segundos.

    python ver.py            # los dos, y abre el español
    python ver.py --comprobar
"""

import argparse
import html
import json
import pathlib
import re
import sys
import webbrowser

AQUI = pathlib.Path(__file__).parent

ESTILO = """
:root { --tinta:#1a1a1a; --suave:#666; --linea:#e2e2e2; --fondo:#fff;
        --acento:#0f766e; --codigo:#f6f8fa; }
* { box-sizing: border-box }
body { max-width: 46rem; margin: 0 auto; padding: 3rem 1.5rem 6rem;
       font: 17px/1.7 Georgia, "Times New Roman", serif;
       color: var(--tinta); background: var(--fondo); }
h1 { font-size: 2.1rem; line-height: 1.2; margin: 0 0 .4em;
     letter-spacing: -.02em; }
h2 { font-size: 1.45rem; margin: 2.6em 0 .6em; padding-top: .3em;
     letter-spacing: -.01em; }
h3 { font-size: 1.15rem; margin: 2em 0 .5em; color: var(--suave); }
p, li { margin: 0 0 1.1em }
a { color: var(--acento) }
strong { font-weight: 700 }
hr { border: 0; border-top: 1px solid var(--linea); margin: 2.6em 0 }
blockquote { margin: 1.6em 0; padding: .2em 0 .2em 1.2em;
             border-left: 3px solid var(--acento); color: var(--suave);
             font-style: italic; }
code { font: 14px/1.5 "Cascadia Code", Consolas, monospace;
       background: var(--codigo); padding: .12em .35em; border-radius: 3px; }
pre { background: var(--codigo); border: 1px solid var(--linea);
      border-radius: 6px; padding: 1rem 1.1rem; overflow-x: auto;
      margin: 1.4em 0; }
pre code { background: none; padding: 0; font-size: 13.5px; line-height: 1.55 }
table { border-collapse: collapse; width: 100%; margin: 1.5em 0; font-size: 15px;
        font-family: -apple-system, "Segoe UI", sans-serif; }
th, td { border-bottom: 1px solid var(--linea); padding: .6em .7em;
         text-align: left; vertical-align: top; }
th { font-weight: 600; border-bottom-width: 2px }
tr:last-child td { border-bottom: none }
.cabecera { color: var(--suave); font-size: .92rem; margin: 0 0 3em;
            font-family: -apple-system, "Segoe UI", sans-serif; }
figure { margin: 2em 0; }
figure img { width: 100%; height: auto; display: block;
             border: 1px solid var(--linea); border-radius: 6px; }
figcaption { margin-top: .6em; font-size: .85rem; color: var(--suave);
             text-align: center;
             font-family: -apple-system, "Segoe UI", sans-serif; }

/* Para el PDF: que nada se parta por la mitad al imprimir. */
@media print {
  body { max-width: none; padding: 0; font-size: 11.5pt }
  h1, h2, h3 { break-after: avoid }
  pre, table, blockquote, figure { break-inside: avoid }
  a { color: var(--tinta); text-decoration: none }
  a[href^="http"]::after { content: " (" attr(href) ")";
                           font-size: .8em; color: var(--suave) }
}
"""


def _linea(t):
    """Lo que va dentro de un párrafo: código, negrita, cursiva y enlaces.

    El código se saca antes de escapar y se devuelve al final, porque si no los
    `<` y `&` de dentro se escaparían dos veces.
    """
    trozos = []

    def guardar(m):
        trozos.append(html.escape(m.group(1)))
        return f"\x00{len(trozos) - 1}\x00"

    t = re.sub(r"`([^`]+)`", guardar, t)
    t = html.escape(t)
    # La imagen antes que el enlace: `![x](y)` es un enlace con `!` delante, y
    # si se convierte primero el enlace queda un `!` suelto y un `<a>` con un
    # PNG dentro.
    t = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)",
               r'<figure><img src="\2" alt="\1"><figcaption>\1</figcaption></figure>', t)
    t = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', t)
    # La negrita, antes que la cursiva y aceptando `*` dentro: el post tiene
    # negritas que envuelven un nombre científico en cursiva, y con `[^*]+` esas
    # se quedaban sin convertir.
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", t)
    return re.sub(r"\x00(\d+)\x00", lambda m: f"<code>{trozos[int(m.group(1))]}</code>", t)


def convertir(md):
    """Markdown a HTML. Solo lo que el post usa; ver el docstring de arriba."""
    cuerpo, cabecera, titulo = [], "", ""

    # La cabecera de Dev.to no se pinta como texto: se saca y se usa aparte. El
    # título vive solo ahí —el post no repite un `#` en el cuerpo, porque Dev.to
    # lo pintaría dos veces—, así que si no se recupera de aquí la página se
    # queda sin titular.
    if md.startswith("---"):
        fin = md.index("\n---", 3)
        frontal = md[3:fin]
        t = re.search(r'title:\s*"?([^"\n]+?)"?\s*$', frontal, re.M)
        titulo = t.group(1) if t else ""
        etiquetas = re.search(r"tags:\s*(.+)", frontal)
        cabecera = etiquetas.group(1).strip() if etiquetas else ""
        md = md[fin + 4:]

    lineas, i = md.split("\n"), 0
    while i < len(lineas):
        L = lineas[i]

        if L.lstrip().startswith("```"):              # bloque de código
            # `lstrip` y no `startswith` a secas: el post mete bloques dentro de
            # elementos de lista, y esos van sangrados. Sin esto se colaban tal
            # cual, con las comillas incluidas, dentro de un párrafo.
            sangria = len(L) - len(L.lstrip())
            idioma, i = L.lstrip()[3:].strip(), i + 1
            trozo = []
            while i < len(lineas) and not lineas[i].lstrip().startswith("```"):
                trozo.append(lineas[i][sangria:] if lineas[i][:sangria].isspace()
                             else lineas[i])
                i += 1
            clase = f' class="lenguaje-{idioma}"' if idioma else ""
            cuerpo.append(f"<pre><code{clase}>"
                          f"{html.escape(chr(10).join(trozo))}</code></pre>")

        elif L.startswith("|"):                       # tabla
            filas = []
            while i < len(lineas) and lineas[i].startswith("|"):
                filas.append([c.strip() for c in lineas[i].strip("|").split("|")])
                i += 1
            i -= 1
            # La segunda fila es el separador (|---|---|) y no se pinta.
            sep = len(filas) > 1 and set("".join(filas[1])) <= set("-: ")
            datos = filas[2:] if sep else filas[1:]
            t = ["<table>"]
            if any(c for c in filas[0]):              # hay títulos de columna
                t.append("<tr>" + "".join(f"<th>{_linea(c)}</th>"
                                          for c in filas[0]) + "</tr>")
            elif not sep:
                datos = filas
            for f in datos:
                t.append("<tr>" + "".join(f"<td>{_linea(c)}</td>" for c in f) + "</tr>")
            cuerpo.append("\n".join(t) + "</table>")

        elif L.startswith("> "):
            cita = []
            while i < len(lineas) and lineas[i].startswith(">"):
                cita.append(lineas[i].lstrip("> ").rstrip())
                i += 1
            i -= 1
            cuerpo.append(f"<blockquote><p>{_linea(' '.join(cita))}</p></blockquote>")

        elif L.startswith("#"):
            n = len(L) - len(L.lstrip("#"))
            cuerpo.append(f"<h{n}>{_linea(L[n:].strip())}</h{n}>")

        elif L.strip() == "---":
            cuerpo.append("<hr>")

        elif L.startswith("!["):
            # Rama propia: por la de párrafo saldría un <figure> dentro de un
            # <p>, que no es HTML válido y que los navegadores desanidan
            # dejando párrafos vacíos por medio.
            cuerpo.append(_linea(L.strip()))

        elif L.startswith("- "):
            puntos = []
            # Se corta en un bloque de código sangrado: si no, se tragaría el
            # ``` como si fuera continuación del punto anterior.
            while i < len(lineas) and not lineas[i].lstrip().startswith("```") \
                    and (lineas[i].startswith("- ")
                         or (puntos and lineas[i].startswith("  "))):
                if lineas[i].startswith("- "):
                    puntos.append(lineas[i][2:])
                else:                                  # continuación indentada
                    puntos[-1] += " " + lineas[i].strip()
                i += 1
            i -= 1
            cuerpo.append("<ul>" + "".join(f"<li>{_linea(p)}</li>"
                                           for p in puntos) + "</ul>")

        elif L.strip():                                # párrafo
            # La primera línea entra siempre. Si se comprobara la condición
            # también sobre ella, una que empiece por `-` o `` ` `` sin ser
            # lista ni código no entraría en ninguna rama, `i` no avanzaría y
            # esto se quedaría dando vueltas para siempre.
            parrafo = [L.strip()]
            i += 1
            while i < len(lineas) and lineas[i].strip() and \
                    lineas[i][0] not in "#|>-`":
                parrafo.append(lineas[i].strip())
                i += 1
            i -= 1
            cuerpo.append(f"<p>{_linea(' '.join(parrafo))}</p>")

        i += 1

    return titulo, cabecera, "\n".join(cuerpo)


def pagina(md, idioma="es"):
    titulo, cabecera, cuerpo = convertir(md)
    aviso = ("Ctrl+P para guardar en PDF" if idioma == "es"
             else "Ctrl+P to save as PDF")
    encabezado = ""
    if titulo:
        encabezado = (f"<h1>{_linea(titulo)}</h1>"
                      f'<p class="cabecera">{html.escape(cabecera)} · {aviso}</p>')
    return (f'<!doctype html>\n<html lang="{idioma}">\n<meta charset="utf-8">\n'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">\n'
            f'<title>{html.escape(titulo) if titulo else "post"}</title>\n'
            f"<style>{ESTILO}</style>\n{encabezado}\n{cuerpo}\n</html>\n")


# La del sitio: mismo texto, pero dentro de la plantilla de riksi.github.io para
# que no parezca una página de otro proyecto. Es el enlace canónico propio, al
# que apuntan Dev.to y Medium.
SITIO = AQUI.parent / "docs" / "articulo.html"
BASE = "https://diegofernandolojantenesaca.github.io/riski"

# **Tres títulos para el mismo texto, y no es una inconsistencia.** Cada uno se
# lee en un sitio distinto y compite contra cosas distintas:
#
# - el de `post.md` va a Dev.to, donde el feed premia lo concreto;
# - éste encabeza la página propia, que es la que se cita y la que aparece en un
#   perfil o un currículum, así que nombra el objeto de estudio con el
#   vocabulario del campo;
# - y `TITULO_BREVE` es el de la etiqueta `<title>`, porque los buscadores
#   cortan sobre los 60 caracteres y con el largo se ve media frase.
#
# El titular académico describe el **hallazgo** —el sesgo de evaluación— y no el
# sistema construido. Un «desarrollo de un clasificador de especies…» prometería
# un artículo de aplicación, y tres cuartas partes de éste hablan de errores de
# medición.
TITULO_SITIO = ("Sesgo de muestreo en la evaluación fuera de distribución de un "
                "clasificador de especies: micro frente a macro-promedio sobre "
                "datos de ciencia ciudadana")
TITULO_BREVE = "Sesgo de muestreo en evaluación fuera de distribución"
# El titular académico nombra el problema como lo nombra el campo; esta línea lo
# dice en castellano llano, justo debajo. Quien conozca los términos se salta la
# bajada; quien no, no se queda fuera en la primera línea.
BAJADA_SITIO = ("O dicho sin jerga: cuatro cifras que publiqué sobre un "
                "clasificador de especies, y qué pasó cuando las medí bien.")

AUTOR = "Diego Fernando Lojan Tenesaca"
# El mismo rótulo que la sección «Acerca de» del sitio, en inglés y con el país,
# porque es como se nombra el puesto en las ofertas y en los perfiles. La
# traducción al español lo hace menos buscable, no más claro.
OFICIO = "Data & AI Engineer"
LUGAR = "Ecuador"

# Lo que se hace, no lo que se sabe. Copiado de la ficha del índice para que las
# dos digan lo mismo: dos versiones distintas del mismo perfil en el mismo sitio
# es lo primero que resta credibilidad.
ESPECIALIDADES = [
    "Modelos de lenguaje, RAG y agentes",
    "Embeddings y búsqueda vectorial",
    "Visión por computador e inferencia con ONNX",
    "Datos: ingesta, limpieza y publicación",
]

CABEZA_SITIO = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="theme-color" content="#14181b">
<title>{titulo_corto} · Riksi</title>
<meta name="description" content="{resumen}">
<meta name="author" content="{autor}">
<link rel="canonical" href="{base}/articulo.html">
<meta property="og:type" content="article">
<meta property="og:title" content="{titulo}">
<meta property="og:description" content="{resumen}">
<meta property="og:image" content="{base}/articulo/sesgo.png">
<meta name="twitter:card" content="summary_large_image">
<link rel="icon" href="icono.svg">
<link rel="stylesheet" href="estilo.css">
<script type="application/ld+json">
{{
  "@context": "https://schema.org",
  "@type": "TechArticle",
  "headline": "{titulo}",
  "description": "{resumen}",
  "image": "{base}/articulo/sesgo.png",
  "author": {{
    "@type": "Person",
    "name": "{autor}",
    "jobTitle": "{oficio_json}",
    "url": "https://github.com/DiegoFernandoLojanTenesaca"
  }},
  "inLanguage": "es",
  "keywords": "evaluación fuera de distribución, macro-promedio, sesgo de muestreo, ciencia ciudadana, GBIF, ONNX"
}}
</script>
<style>
/* **El sitio es de fondo oscuro.** Estas reglas estaban escritas para papel
   blanco —`--tinta` es #171b1c— y dejaban la entradilla en negro sobre negro,
   ilegible. Aquí se usa la paleta clara del tema: `--texto` para el cuerpo,
   `--suave` para lo secundario y `--papel` para lo que va sobre fondo. */
.escrito {{ max-width: 44rem; margin: 0 auto; padding: 0 20px 90px;
            color: var(--texto); }}
/* Más contenido que un titular corto: el tamaño baja y el interlineado sube,
   porque tres líneas a 2,6rem ocupan media pantalla en un móvil. */
.escrito h1 {{ font-size: clamp(1.6rem, 3.6vw, 2.1rem); line-height: 1.28;
               margin: 0 0 .55em; letter-spacing: -.01em; color: var(--papel);
               font-weight: 600; }}
.escrito h2 {{ margin: 2.4em 0 .5em; font-size: 1.5rem; color: var(--papel);
               font-weight: 600; }}
.escrito h3 {{ margin: 2em 0 .4em; font-size: 1.15rem; color: var(--suave);
               font-weight: 600; }}
.escrito p, .escrito li {{ font-size: 1.05rem; line-height: 1.75;
                           color: var(--texto); }}
.escrito strong {{ color: var(--papel); font-weight: 600; }}
.escrito em {{ color: var(--suave); }}
.escrito a {{ color: var(--agua); text-decoration-color: rgba(121,176,168,.4);
              text-underline-offset: 2px; }}
.escrito a:hover {{ color: var(--liquen); }}
.escrito figure {{ margin: 2.4em 0; }}
.escrito figure img {{ width: 100%; height: auto; display: block;
                       border: 1px solid var(--marea); border-radius: 10px; }}
.escrito figcaption {{ margin-top: .7em; font-size: .85rem; color: var(--tenue);
                       text-align: center; }}
/* El fondo del código va un paso por debajo del de la página, no por encima:
   sobre fondo oscuro, un bloque más claro pesa demasiado en la lectura. */
.escrito pre {{ background: var(--basalto-3); color: var(--texto);
                border: 1px solid var(--marea); border-radius: 10px;
                padding: 1rem 1.2rem; overflow-x: auto; margin: 1.5em 0;
                font-size: .86rem; line-height: 1.62; }}
.escrito pre code {{ background: none; padding: 0; color: inherit; }}
.escrito code {{ background: rgba(220,224,218,.09); color: var(--papel);
                 padding: .12em .38em; border-radius: 4px; font-size: .9em; }}
.escrito table {{ width: 100%; border-collapse: collapse; margin: 1.7em 0;
                  font-size: .95rem; }}
.escrito th, .escrito td {{ border-bottom: 1px solid var(--marea);
                            padding: .62em .7em; text-align: left;
                            vertical-align: top; color: var(--texto); }}
.escrito th {{ color: var(--suave); font-weight: 600; }}
.escrito blockquote {{ margin: 1.9em 0; padding: .35em 0 .35em 1.3rem;
                       border-left: 3px solid var(--liquen-2);
                       color: var(--suave); font-style: italic; }}
.escrito hr {{ border: 0; border-top: 1px solid var(--marea); margin: 2.8em 0; }}
.bajada-art {{ font-size: 1.2rem; line-height: 1.55; color: var(--suave);
               margin: -.2em 0 1.5em; font-weight: 400; }}
.resumen {{ font-size: 1.15rem; line-height: 1.65; color: var(--papel);
            margin: 0 0 1.3em; padding-left: 1.1rem;
            border-left: 3px solid var(--liquen); }}
.entradilla {{ color: var(--tenue); font-size: .95rem; margin: 0 0 3.2em;
               line-height: 1.75; }}
.entradilla b {{ color: var(--suave); font-weight: 600; }}
.entradilla a {{ color: var(--suave); }}
</style>
</head>
<body>

<header class="barra">
  <a class="marca" href="index.html"><img src="icono.svg" alt="">Riksi</a>
  <nav class="menu">
    <a href="index.html#como">Cómo usarla</a>
    <a href="especies.html">Las especies</a>
    <a href="index.html#herramientas">Herramientas</a>
    <a href="articulo.html">El artículo</a>
    <a href="index.html#colaborar">Colaborar</a>
  </nav>
  <a class="boton" href="app.html">Abrir la cámara</a>
</header>

<div class="envoltura">
<article class="escrito">
<h1>{titulo}</h1>
<p class="bajada-art">{bajada}</p>
<p class="resumen">{resumen}</p>
<p class="entradilla">{autor} · {oficio} · {aviso}</p>
"""

# La autoría va al pie y no en una línea bajo el titular: en un texto de tres mil
# palabras, quien quiere saber quién lo firma llega abajo, y arriba solo estorba
# entre el titular y la primera frase. Reutiliza `.tarjeta` del sitio para que
# sea la misma ficha que hay en la portada, no una variante.
PIE_SITIO = """
<hr>
<div class="ficha-autor" style="margin-top:44px">
  <div class="tarjeta">
    <b>{autor}</b>
    <span>{oficio} · {lugar}</span>
    <ul>{especialidades}</ul>
    <a href="https://github.com/DiegoFernandoLojanTenesaca">github.com/DiegoFernandoLojanTenesaca</a>
  </div>
  <div class="relato">
    <p>Riksi empezó por un problema concreto: casi todas las herramientas para
      identificar naturaleza dan por sentado que hay internet, y en el Ecuador
      rural eso casi nunca se cumple. El reto no era entrenar un clasificador
      —eso lo hace cualquiera con un tutorial— sino que <b>cupiera en un
      teléfono modesto y siguiera acertando</b>.</p>
    <p>Este artículo es la continuación de esa idea aplicada a la medición: si
      cada decisión de ingeniería se justifica con números, esos números también
      tienen que aguantar que los revisen. Cuatro no aguantaron.</p>
    <p>De paso toca lo que hay debajo: <b>evaluación fuera de distribución</b>
      sin conjunto de prueba disponible, <b>calidad de datos</b> en fuentes
      públicas que se actualizan a distinta velocidad, <b>calibración</b> de un
      sistema de recuperación, e <b>inferencia con recursos limitados</b> —un
      clasificador de 3,8 MB en el navegador y un codificador que tenía que
      caber en 512 MB de RAM.</p>
    <p><a href="index.html">Riksi</a> ·
      <a href="https://github.com/DiegoFernandoLojanTenesaca/riksi-radar">riksi-radar</a> ·
      <a href="https://github.com/DiegoFernandoLojanTenesaca/yachaq">yachaq</a></p>
  </div>
</div>
</article>
</div>
</body>
</html>
"""


def _con_tema_oscuro(cuerpo):
    """Cada figura, en su variante oscura.

    **El sitio de Riksi es oscuro siempre**, no según la preferencia del sistema,
    así que aquí no vale `prefers-color-scheme`: quien navegue con el sistema en
    claro vería figuras de fondo blanco sobre una página negra, que es justo lo
    que se quería evitar. La variante clara existe para los HTML sueltos y para
    el PDF, que sí se leen sobre papel.
    """
    def cambiar(m):
        ruta, resto = m.group(1), m.group(2)
        oscura = ruta.replace(".png", "-oscuro.png")
        if not (AQUI.parent / "docs" / oscura).exists():
            return m.group(0)
        return f'<img src="{oscura}"{resto}>'

    return re.sub(r'<img src="(articulo/[^"]+\.png)"([^>]*)>', cambiar, cuerpo)


def para_el_sitio():
    """El post dentro de la plantilla de riksi.github.io.

    Las imágenes se referencian desde `docs/articulo/`, que es donde GitHub
    Pages las va a servir: un `imagenes/x.png` relativo al Markdown apunta fuera
    de `docs/` y no se publicaría.
    """
    md = (AQUI / "post.md").read_text(encoding="utf-8")
    _, _, cuerpo = convertir(md)      # el título del frontmatter es el de Dev.to
    cuerpo = cuerpo.replace('src="imagenes/', 'src="articulo/')
    cuerpo = _con_tema_oscuro(cuerpo)
    # Doble uso: es la meta-descripción que sale en los buscadores y la
    # entradilla que se lee bajo el titular, así que tiene que funcionar como
    # frase suelta y como primer párrafo. Da las dos cifras del hallazgo, porque
    # quien solo lea esto debería llevarse el resultado.
    resumen = ("Un clasificador de cien especies evaluado sobre 400 "
               "observaciones que nadie seleccionó acierta el 84,2 % de las "
               "veces. Dando el mismo peso a cada especie en vez de a cada "
               "fotografía, el 78,7 %. Esos 5,5 puntos no son el modelo: son "
               "que una sola especie aporta un tercio del conjunto. Es una de "
               "las cuatro cifras que publiqué antes de medirlas bien.")
    # Sobre 200 palabras por minuto, que es lo habitual en prosa técnica.
    minutos = round(len(md.split()) / 200)
    aviso = f"{minutos} min de lectura"

    SITIO.write_text(
        CABEZA_SITIO.format(titulo=html.escape(TITULO_SITIO), resumen=resumen,
                            titulo_corto=html.escape(TITULO_BREVE),
                            autor=AUTOR, oficio=html.escape(OFICIO),
                            # dentro del JSON-LD el `&` no va escapado: ahí no
                            # es HTML, y un buscador leería «&amp;» literal.
                            oficio_json=OFICIO, bajada=BAJADA_SITIO,
                            aviso=aviso, base=BASE) + cuerpo
        + PIE_SITIO.format(
            autor=AUTOR, oficio=html.escape(OFICIO), lugar=LUGAR,
            especialidades="".join(f"<li>{e}</li>" for e in ESPECIALIDADES)),
        encoding="utf-8")
    print(f"  docs/{SITIO.name}  ({SITIO.stat().st_size // 1024} KB)")
    return SITIO


def copiar_imagenes():
    """Las figuras, a `docs/articulo/`, que es lo que GitHub Pages publica."""
    import shutil

    destino = AQUI.parent / "docs" / "articulo"
    destino.mkdir(exist_ok=True)
    copiadas = 0
    for png in sorted((AQUI / "imagenes").glob("*.png")):
        shutil.copy2(png, destino / png.name)
        copiadas += 1
    print(f"  docs/articulo/  ({copiadas} figuras)")
    return copiadas


def generar(abrir=True):
    hechos = []
    for origen, idioma in (("post.md", "es"), ("post-en.md", "en")):
        md = (AQUI / origen).read_text(encoding="utf-8")
        destino = AQUI / origen.replace(".md", ".html")
        destino.write_text(pagina(md, idioma), encoding="utf-8")
        hechos.append(destino)
        print(f"  {destino.name}  ({destino.stat().st_size // 1024} KB)")
    copiar_imagenes()
    para_el_sitio()
    if abrir:
        webbrowser.open(hechos[0].as_uri())
    return hechos


def prueba():
    """Que lo que el post usa se convierta bien. Es todo lo que tiene que hacer."""
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    *_, h = convertir("## Un título\n\nCon **negrita** y `código`.\n")
    assert "<h2>Un título</h2>" in h and "<strong>negrita</strong>" in h, h
    assert "<code>código</code>" in h, h

    # Negrita envolviendo cursiva. El post lo hace con nombres científicos, y
    # convertir la cursiva primero dejaba la negrita sin aplicar.
    *_, h = convertir("**El *mean pooling* va ponderado.**\n")
    assert "<strong>El <em>mean pooling</em> va ponderado.</strong>" in h, h

    # Una tabla con títulos y otra sin ellos: el post usa las dos formas.
    *_, h = convertir("| a | b |\n|---|---|\n| 1 | 2 |\n")
    assert h.count("<tr>") == 2 and "<th>a</th>" in h and "<td>1</td>" in h, h
    *_, h = convertir("| | |\n|---|---|\n| x | y |\n")
    assert "<th>" not in h and "<td>x</td>" in h, "una tabla sin cabecera no lleva th"

    # El código no se escapa dos veces: es el fallo clásico de hacer esto a mano.
    *_, h = convertir("```python\nif a < b & c:\n    pass\n```\n")
    assert "&amp;amp;" not in h and "a &lt; b &amp; c" in h, h
    *_, h = convertir("Esto es `x < 1 & y` en línea.\n")
    assert "&amp;amp;" not in h and "<code>x &lt; 1 &amp; y</code>" in h, h

    # Un enlace dentro de una celda, que es como está el montaje del post.
    *_, h = convertir("| [r](http://e) | ok |\n|---|---|\n| 1 | 2 |\n")
    assert '<a href="http://e">r</a>' in h, h

    # Y la cabecera de Dev.to no se pinta como si fuera texto del post.
    _, cab, h = convertir('---\ntitle: "T"\ntags: a, b\n---\n\n# T\n\nHola.\n')
    assert cab == "a, b" and "title:" not in h, (cab, h[:120])

    # Este colgó el conversor: una línea que empieza por `-` sin ser lista no
    # entraba en ninguna rama y el bucle no avanzaba nunca.
    *_, h = convertir("-x no es una lista\n")
    assert "-x no es una lista" in h, h

    # Un bloque de código dentro de una lista, sangrado. Este se colaba entero
    # como texto, con las comillas incluidas, dentro de un párrafo.
    *_, h = convertir("- un punto\n\n  ```python\n  x = 1\n  ```\n")
    assert "```" not in h and "<pre><code" in h, h
    assert ">x = 1<" in h, "la sangría del bloque tenía que quitarse"

    # Las imágenes: fuera de un <p>, y sin que el enlace se las coma antes.
    *_, h = convertir("![pie del gráfico](imagenes/x.png)\n")
    assert '<img src="imagenes/x.png"' in h and "<p>" not in h, h
    assert "<figcaption>pie del gráfico</figcaption>" in h, h
    assert "!<a" not in h, "el enlace se comió la imagen y dejó el ! suelto"

    ok = generar(abrir=False)
    for f in ok:
        t = f.read_text(encoding="utf-8")
        assert t.count("<table") >= 3, f"{f.name}: faltan tablas"
        assert t.count("<img") >= 6, f"{f.name}: faltan figuras"
        assert "```" not in t and "**" not in t, f"{f.name}: quedó Markdown sin convertir"
        # El título sale del frontmatter, no del cuerpo: sin esto la página se
        # generaba entera y sin titular, y el fallo no se veía en el HTML.
        assert t.count("<h1>") == 1, f"{f.name}: la página se quedó sin titular"

    # La del sitio: dentro de `docs/`, con las imágenes donde Pages las sirve.
    s = SITIO.read_text(encoding="utf-8")
    assert 'src="articulo/' in s and 'src="imagenes/' not in s, (
        "las figuras apuntan fuera de docs/: en Pages saldrían rotas")
    assert "estilo.css" in s and 'class="barra"' in s, "no lleva el envoltorio del sitio"
    for ref in re.findall(r'src(?:set)?="(articulo/[^"]+)"', s):
        assert (AQUI.parent / "docs" / ref).exists(), f"falta {ref}"
    # Todas las figuras en su variante oscura: una clara sobre la página negra
    # del sitio es un rectángulo que deslumbra a plena anchura.
    claras = [r for r in re.findall(r'<img src="(articulo/[^"]+\.png)"', s)
              if "-oscuro" not in r]
    assert not claras, f"figuras con fondo claro sobre página oscura: {claras}"
    assert s.count('src="articulo/') == s.count("<figure>")

    # Los tres títulos: el académico encabeza la página, el breve va en la
    # etiqueta que cortan los buscadores, y el de Dev.to no debe colarse aquí.
    assert f"<h1>{TITULO_SITIO}</h1>" in s, "la página no lleva el titular académico"
    breve = re.search(r"<title>(.*?)</title>", s).group(1)
    assert len(breve) <= 62, f"<title> de {len(breve)}: los buscadores lo cortan"
    assert TITULO_SITIO in re.search(r'og:title" content="(.*?)"', s).group(1), (
        "al compartir se vería el título corto en vez del completo")

    # La autoría, en los tres sitios donde se lee: la firma visible, la meta que
    # usan los agregadores y los datos estructurados de los buscadores.
    oficio = html.escape(OFICIO)      # «Data & AI» lleva un & que va escapado
    assert f"{AUTOR} · {oficio}" in s, "falta el oficio bajo el titular"
    assert f"<b>{AUTOR}</b>" in s and f"{oficio} · {LUGAR}" in s, (
        "falta la ficha de autor al pie")
    for e in ESPECIALIDADES:
        assert f"<li>{e}</li>" in s, f"falta «{e}» en la ficha"

    # La misma ficha que la portada. Dos versiones del mismo perfil en el mismo
    # sitio es lo primero que resta credibilidad, y se descuadran en cuanto se
    # toca una y se olvida la otra.
    portada = (AQUI.parent / "docs" / "index.html").read_text(encoding="utf-8")
    for e in ESPECIALIDADES:
        assert e in portada, f"«{e}» no está en la ficha de index.html"
    assert f"{oficio} · {LUGAR}" in portada, (
        "el oficio del artículo no coincide con el de la portada")
    assert f'name="author" content="{AUTOR}"' in s
    ficha = json.loads(re.search(r'type="application/ld\+json">\s*(\{.*?\})\s*</script>',
                                 s, re.S).group(1))
    assert ficha["author"]["jobTitle"] == OFICIO, ficha["author"]
    assert ficha["headline"] == TITULO_SITIO

    # Y que el texto sea legible: el sitio es de fondo oscuro, y estas reglas
    # estaban escritas para papel blanco. `--tinta` es #171b1c: negro sobre
    # negro, invisible.
    estilos = s[s.index("<style>"):s.index("</style>")]
    claros = [v for v in re.findall(r"var\(--([\w-]+)\)", estilos)
              if v in ("tinta", "tinta-2")]
    assert not claros, (
        f"colores del tema claro sobre el fondo oscuro del sitio: {set(claros)}")
    print(f"ok · tablas, código, enlaces y cita · {len(ok)} páginas generadas")


def main():
    a = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    a.add_argument("--comprobar", action="store_true")
    a.add_argument("--no-abrir", action="store_true")
    args = a.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    prueba() if args.comprobar else generar(not args.no_abrir)


if __name__ == "__main__":
    main()
