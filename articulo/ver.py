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

/* Para el PDF: que nada se parta por la mitad al imprimir. */
@media print {
  body { max-width: none; padding: 0; font-size: 11.5pt }
  h1, h2, h3 { break-after: avoid }
  pre, table, blockquote { break-inside: avoid }
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

        if L.startswith("```"):                       # bloque de código
            idioma, i = L[3:].strip(), i + 1
            trozo = []
            while i < len(lineas) and not lineas[i].startswith("```"):
                trozo.append(lineas[i])
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

        elif L.startswith("- "):
            puntos = []
            while i < len(lineas) and (lineas[i].startswith("- ")
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


def generar(abrir=True):
    hechos = []
    for origen, idioma in (("post.md", "es"), ("post-en.md", "en")):
        md = (AQUI / origen).read_text(encoding="utf-8")
        destino = AQUI / origen.replace(".md", ".html")
        destino.write_text(pagina(md, idioma), encoding="utf-8")
        hechos.append(destino)
        print(f"  {destino.name}  ({destino.stat().st_size // 1024} KB)")
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

    ok = generar(abrir=False)
    for f in ok:
        t = f.read_text(encoding="utf-8")
        assert t.count("<table") >= 4, f"{f.name}: faltan tablas"
        assert "```" not in t and "**" not in t, f"{f.name}: quedó Markdown sin convertir"
        # El título sale del frontmatter, no del cuerpo: sin esto la página se
        # generaba entera y sin titular, y el fallo no se veía en el HTML.
        assert t.count("<h1>") == 1, f"{f.name}: la página se quedó sin titular"
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
