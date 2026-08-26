"""Fase 5: arma el dataset de cantos desde xeno-canto.

    python audio.py --licencias           # qué hay antes de bajar nada
    python audio.py --especies 40 --grabaciones 100

La clave de la API NO va en el código ni en el repositorio. Se lee de la
variable de entorno `XC_CLAVE` o del fichero `xc-clave.txt`, que está en el
.gitignore. Xeno-canto revoca las claves que aparecen publicadas.

Deja la misma estructura que `datos.py`, para que el entrenamiento no tenga que
saber si mira fotos o sonidos:

    <salida>/
        audio/<Genero_especie>/XC<id>.mp3
        creditos.csv      una fila por grabación: autor, licencia, especie
        especies.csv      las clases, con cuántas grabaciones tienen
"""

import argparse
import csv
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

API = "https://xeno-canto.org/api/3/recordings"
AGENTE = "riksi/0.1 (https://github.com/DiegoFernandoLojanTenesaca/riski)"


def clave():
    """La clave, de la variable de entorno o del fichero ignorado por git."""
    if os.environ.get("XC_CLAVE"):
        return os.environ["XC_CLAVE"].strip()
    fichero = Path(__file__).parent / "xc-clave.txt"
    if fichero.exists():
        return fichero.read_text(encoding="utf-8").strip()
    sys.exit("Falta la clave de xeno-canto. Ponla en xc-clave.txt o en XC_CLAVE.\n"
             "Se saca de tu página de cuenta en xeno-canto.org (no es la contraseña).")


def pedir(consulta, pagina=1, por_pagina=500, intentos=4):
    """Una página de resultados. Con reintento, como en datos.py: son miles de
    consultas y cualquier corte de red tiraría horas de trabajo."""
    url = f"{API}?{urllib.parse.urlencode({'query': consulta, 'key': clave(), 'per_page': por_pagina, 'page': pagina})}"
    req = urllib.request.Request(url, headers={"User-Agent": AGENTE})
    for intento in range(intentos):
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                return json.load(r)
        except Exception as err:
            if intento == intentos - 1:
                raise
            espera = 2 ** intento
            print(f"    reintento {intento + 1} en {espera}s ({err})", file=sys.stderr)
            time.sleep(espera)


def todas(consulta, tope=None):
    """Recorre las páginas hasta agotar la consulta o llegar al tope."""
    salida, pagina = [], 1
    while True:
        d = pedir(consulta, pagina)
        salida += d.get("recordings", [])
        if tope and len(salida) >= tope:
            return salida[:tope]
        if pagina >= int(d.get("numPages", 1)):
            return salida
        pagina += 1


def libre(lic):
    """CC0 o CC-BY a secas, el mismo criterio que el dataset de fotos.

    En xeno-canto abundan las licencias con -NC, que obligarían a publicar el
    modelo como no comercial. Antes de bajar nada conviene ver el reparto real
    con `--licencias`: si casi todo es NC, hay que decidir a conciencia y no
    descubrirlo cuando ya está entrenado.
    """
    l = (lic or "").lower()
    return "publicdomain/zero" in l or "/licenses/by/" in l


def nombre_de(r):
    return f"{r['gen']}_{r['sp']}".replace(" ", "_")


def bajar(r, destino):
    req = urllib.request.Request(r["file"], headers={"User-Agent": AGENTE})
    with urllib.request.urlopen(req, timeout=60) as resp:
        datos = resp.read()
    if len(datos) < 5000:                  # errores disfrazados de audio
        raise ValueError(f"archivo sospechosamente pequeño: {len(datos)} B")
    destino.write_bytes(datos)
    return len(datos)


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--pais", default="ecuador")
    p.add_argument("--especies", type=int, default=40)
    p.add_argument("--grabaciones", type=int, default=100, help="máximo por especie")
    p.add_argument("--minimo", type=int, default=30, help="mínimo para aceptar una especie")
    p.add_argument("--calidad", default="A", help="A es la mejor; «>C» acepta A, B y C")
    p.add_argument("--segundos", type=int, default=120, help="descarta las grabaciones más largas")
    p.add_argument("--salida", default="C:/datos/riksi-audio")
    p.add_argument("--hilos", type=int, default=8)
    p.add_argument("--nc", action="store_true", help="acepta también licencias no comerciales")
    p.add_argument("--licencias", action="store_true", help="solo cuenta qué hay, no baja nada")
    args = p.parse_args()

    base = f'cnt:{args.pais} grp:birds q:{args.calidad} len:"<{args.segundos}"'

    if args.licencias:
        print(f"Consultando {base} …")
        rs = todas(base)
        cuenta = Counter(r.get("lic", "") for r in rs)
        especies = Counter(nombre_de(r) for r in rs)
        print(f"\n{len(rs):,} grabaciones · {len(especies)} especies\n")
        for lic, n in cuenta.most_common():
            marca = "libre " if libre(lic) else "atada "
            print(f"  {marca} {n:>6,}  {lic}")
        libres = sum(n for lic, n in cuenta.items() if libre(lic))
        print(f"\n{libres:,} grabaciones sin la atadura de «no comercial» "
              f"({libres / max(1, len(rs)):.0%})")
        sirven = [e for e, n in especies.items() if n >= args.minimo]
        print(f"{len(sirven)} especies llegan a {args.minimo} grabaciones contando todas")
        return

    raiz = Path(args.salida)
    (raiz / "audio").mkdir(parents=True, exist_ok=True)

    print(f"Buscando {base} …")
    rs = todas(base)
    if not args.nc:
        rs = [r for r in rs if libre(r.get("lic"))]
    rs = [r for r in rs if r.get("file")]          # las especies protegidas vienen sin audio

    por_especie = {}
    for r in rs:
        por_especie.setdefault(nombre_de(r), []).append(r)

    elegidas = sorted(por_especie.items(), key=lambda kv: -len(kv[1]))
    elegidas = [(n, g) for n, g in elegidas if len(g) >= args.minimo][:args.especies]
    print(f"{len(rs):,} grabaciones utilizables · {len(elegidas)} especies elegidas\n")

    creditos, especies = [], []
    for i, (nombre, grabaciones) in enumerate(elegidas, 1):
        carpeta = raiz / "audio" / nombre
        carpeta.mkdir(exist_ok=True)
        grabaciones = grabaciones[:args.grabaciones]

        hechas = 0
        with ThreadPoolExecutor(args.hilos) as pool:
            futuros = {}
            for r in grabaciones:
                destino = carpeta / f"XC{r['id']}.mp3"
                if destino.exists():
                    hechas += 1
                    creditos.append({"especie": nombre, "archivo": destino.name,
                                     "autor": r.get("rec", ""), "licencia": r.get("lic", ""),
                                     "url": r.get("url", "")})
                    continue
                futuros[pool.submit(bajar, r, destino)] = (r, destino)
            for fut in as_completed(futuros):
                r, destino = futuros[fut]
                try:
                    fut.result()
                    hechas += 1
                    creditos.append({"especie": nombre, "archivo": destino.name,
                                     "autor": r.get("rec", ""), "licencia": r.get("lic", ""),
                                     "url": r.get("url", "")})
                except Exception as err:
                    destino.unlink(missing_ok=True)
                    print(f"    fallo XC{r['id']}: {err}", file=sys.stderr)

        especies.append({"especie": nombre.replace("_", " "),
                         "comun": grabaciones[0].get("en", ""), "grabaciones": hechas})
        print(f"[{i:>3}/{len(elegidas)}] {nombre.replace('_', ' '):<34} {hechas:>4} grabaciones")

    with open(raiz / "creditos.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, ["especie", "archivo", "autor", "licencia", "url"])
        w.writeheader(); w.writerows(creditos)

    with open(raiz / "especies.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, ["especie", "comun", "grabaciones"])
        w.writeheader(); w.writerows(especies)

    total = sum(e["grabaciones"] for e in especies)
    print(f"\n{total:,} grabaciones en {raiz}")
    print("créditos en creditos.csv · las licencias de xeno-canto piden atribución")


def prueba():
    """Lo único con lógica propia aquí es el filtro de licencias."""
    assert libre("https://creativecommons.org/publicdomain/zero/1.0/")
    assert libre("//creativecommons.org/licenses/by/4.0/")
    assert not libre("https://creativecommons.org/licenses/by-nc-sa/4.0/")
    assert not libre("https://creativecommons.org/licenses/by-nc-nd/4.0/")
    assert not libre("https://creativecommons.org/licenses/by-sa/4.0/")
    assert not libre("")
    assert nombre_de({"gen": "Pheucticus", "sp": "chrysogaster"}) == "Pheucticus_chrysogaster"
    print("ok · filtro de licencias y nombres correctos")


if __name__ == "__main__":
    if "--prueba" in sys.argv:
        prueba()
    else:
        main()
