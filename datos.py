"""Fase 1: arma el dataset de Riksi desde GBIF.

Baja solo fotos con licencia CC0 o CC-BY, para que el dataset y el modelo
derivados se puedan publicar sin la atadura de "no comercial".

    python datos.py --especies 100 --fotos 200

Deja esta estructura:

    <salida>/
        imagenes/<nombre_especie>/<occurrenceKey>_<n>.jpg
        creditos.csv      una fila por foto: autor, licencia, especie, observacion
        especies.csv      las clases, con su clave GBIF y cuántas fotos tienen
"""

import argparse
import csv
import io
import json
import sys
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

API = "https://api.gbif.org/v1"
PAIS = "EC"
# Solo estas dos: CC-BY-NC obligaría a marcar el modelo como no comercial.
LICENCIAS = ["CC0_1_0", "CC_BY_4_0"]
AGENTE = "riksi/0.1 (https://github.com/DiegoFernandoLojanTenesaca/riksi)"


def pedir(ruta, **params):
    pares = []
    for k, v in params.items():
        for item in v if isinstance(v, list) else [v]:
            pares.append((k, item))
    url = f"{API}/{ruta}?{urllib.parse.urlencode(pares)}"
    req = urllib.request.Request(url, headers={"User-Agent": AGENTE})
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.load(r)


def especies_mas_fotografiadas(n):
    """Candidatas, ordenadas por ocurrencias con foto.

    El conteo del facet es de OCURRENCIAS, no de fotos usables, y no predice
    cuántas quedan tras filtrar por proveedor y por licencia de cada imagen:
    *Dasyprocta punctata* anuncia 2.296 y deja 157 (7%) porque casi todo lo suyo
    son cámaras trampa. Por eso esto solo ORDENA candidatas — quién entra al
    dataset lo decide `fotos_de()`, que cuenta lo que de verdad hay.
    """
    d = pedir(
        "occurrence/search",
        country=PAIS, mediaType="StillImage", license=LICENCIAS,
        facet="speciesKey", facetLimit=n, limit=0,
    )
    claves = [(c["name"], c["count"]) for c in d["facets"][0]["counts"]]

    salida = []
    for clave, total in claves:
        t = pedir(f"species/{clave}")
        nombre = t.get("canonicalName")
        if not nombre:          # taxones sin nombre limpio: no sirven como clase
            continue
        salida.append({
            "clave": clave,
            "especie": nombre,
            "grupo": t.get("class") or t.get("phylum") or "?",
            "disponibles": total,
        })
    return salida


def nombre_comun(clave):
    """El nombre en español, si GBIF lo tiene. Para la web: quien está en el
    campo mirando un bicho no busca «Amblyrhynchus cristatus»."""
    try:
        d = pedir(f"species/{clave}/vernacularNames", limit=100)
    except Exception:
        return ""
    for v in d.get("results", []):
        if v.get("language") == "spa" and v.get("vernacularName"):
            return v["vernacularName"]
    return ""


def de_campo(url):
    """Solo fotos de iNaturalist.

    GBIF mezcla proveedores muy distintos, y medido sobre 360 fotos de seis
    especies el reparto es: 70% iNaturalist, 24% cámaras trampa (agouti.eu),
    4% herbario del NYBG, 1% especímenes del Smithsonian.

    Solo el primer grupo se parece a lo que verá la cámara de alguien en el
    campo. Un pliego de herbario prensado o una foto nocturna en infrarrojo son
    otro dominio: meterlos empeora el modelo en vez de mejorarlo. Además
    sweetgum.nybg.org no responde, y cada intento se come el tiempo de espera
    entero.
    """
    return "inaturalist" in urllib.parse.urlparse(url).netloc


def encoger(url, tamano="medium"):
    """iNaturalist sirve varias resoluciones de la misma foto; GBIF apunta a la
    grande.

    `original` son ~1,5 MB y 2048 px: bajar así la v1 entera serían 28 GB para
    entrenar luego a 224 px. `medium` son ~55 KB y 500 px — sobra, y el dataset
    baja a algo más de 1 GB. Las URLs que no reconozco se dejan intactas.
    """
    if "inaturalist-open-data" not in url and "static.inaturalist" not in url:
        return url
    base, _, ext = url.rpartition("/")[2].rpartition(".")
    if base not in ("original", "large", "medium", "small", "square"):
        return url
    return f"{url.rsplit('/', 1)[0]}/{tamano}.{ext}"


def usable(licencia):
    """CC0 o CC-BY a secas.

    El filtro `license` de GBIF se aplica a la OCURRENCIA, no a cada foto: una
    ocurrencia CC-BY puede traer imágenes CC-BY-NC-SA. Medido sobre 2.298 fotos
    de cuatro especies, el 95% pasa el filtro por imagen — pero ese 5% restante
    contaminaría el dataset, y en alguna especie sube al 20% (Microlophus
    albemarlensis: 212 de 266). Barato de comprobar, caro de descubrir tarde.
    """
    l = (licencia or "").lower()
    return "publicdomain/zero" in l or "/licenses/by/" in l


def fotos_de(clave, maximo):
    """Registros con foto de una especie. Una fila por imagen."""
    filas, offset = [], 0
    while len(filas) < maximo and offset < 10000:
        d = pedir(
            "occurrence/search",
            country=PAIS, mediaType="StillImage", license=LICENCIAS,
            speciesKey=clave, limit=300, offset=offset,
        )
        for oc in d["results"]:
            for i, m in enumerate(oc.get("media", [])):
                url = m.get("identifier")
                if not url or m.get("type") != "StillImage" or not de_campo(url):
                    continue
                licencia = m.get("license") or oc.get("license") or ""
                if not usable(licencia):
                    continue
                filas.append({
                    "observacion": oc["key"],
                    "url": encoger(url),
                    "autor": m.get("creator") or oc.get("recordedBy") or "",
                    "licencia": licencia,
                })
                if len(filas) >= maximo:
                    break
            if len(filas) >= maximo:
                break
        if d.get("endOfRecords"):
            break
        offset += 300
    return filas


def bajar(fila, destino):
    req = urllib.request.Request(fila["url"], headers={"User-Agent": AGENTE})
    # 20 s y no 60: un proveedor caído no puede frenar toda la descarga.
    with urllib.request.urlopen(req, timeout=20) as r:
        datos = r.read()
    if len(datos) < 2000:            # respuestas de error disfrazadas de imagen
        raise ValueError(f"imagen sospechosamente pequeña: {len(datos)} B")
    destino.write_bytes(datos)
    return len(datos)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--especies", type=int, default=100)
    p.add_argument("--fotos", type=int, default=200, help="máximo por especie")
    p.add_argument("--minimo", type=int, default=50,
                   help="fotos usables mínimas para aceptar una especie (el umbral del entrenamiento)")
    p.add_argument("--salida", default="C:/datos/riksi", help="va en C:, que tiene sitio")
    p.add_argument("--hilos", type=int, default=16)
    args = p.parse_args()

    raiz = Path(args.salida)
    (raiz / "imagenes").mkdir(parents=True, exist_ok=True)

    print(f"Buscando candidatas de Ecuador para llenar {args.especies} plazas…")
    candidatas = especies_mas_fotografiadas(args.especies * 3)
    print(f"  {len(candidatas)} candidatas, de {candidatas[0]['disponibles']:,} "
          f"a {candidatas[-1]['disponibles']:,} ocurrencias\n")

    creditos, especies, saltadas = [], [], []
    for e in candidatas:
        if len(especies) >= args.especies:
            break
        filas = fotos_de(e["clave"], args.fotos)
        # Se decide con el conteo real, no con el del facet: una especie que deja
        # 20 fotos no da para una clase y el entrenamiento la tiraría igual.
        if len(filas) < args.minimo:
            saltadas.append((e["especie"], len(filas), e["disponibles"]))
            print(f"      salta {e['especie']:<34} {len(filas):>4} usables "
                  f"de {e['disponibles']:,} anunciadas")
            continue
        e["comun"] = nombre_comun(e["clave"])

        carpeta = raiz / "imagenes" / e["especie"].replace(" ", "_")
        carpeta.mkdir(exist_ok=True)

        hechas = 0
        with ThreadPoolExecutor(args.hilos) as pool:
            futuros = {}
            for n, f in enumerate(filas):
                destino = carpeta / f"{f['observacion']}_{n}.jpg"
                if destino.exists():
                    hechas += 1
                    creditos.append({**f, "especie": e["especie"], "archivo": destino.name})
                    continue
                futuros[pool.submit(bajar, f, destino)] = (f, destino)
            for fut in as_completed(futuros):
                f, destino = futuros[fut]
                try:
                    fut.result()
                    hechas += 1
                    creditos.append({**f, "especie": e["especie"], "archivo": destino.name})
                except Exception as err:
                    destino.unlink(missing_ok=True)
                    print(f"    fallo {f['url'][:60]}… {err}", file=sys.stderr)

        e["bajadas"] = hechas
        especies.append(e)
        print(f"[{len(especies):>3}/{args.especies}] {e['especie']:<34} "
              f"{hechas:>4} fotos  ({e['grupo']})")

    with open(raiz / "creditos.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, ["especie", "archivo", "observacion", "autor", "licencia", "url"])
        w.writeheader()
        w.writerows(creditos)

    with open(raiz / "especies.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, ["clave", "especie", "comun", "grupo", "disponibles", "bajadas"])
        w.writeheader()
        w.writerows(especies)

    total = sum(e["bajadas"] for e in especies)
    print(f"\n{len(especies)} especies · {len(saltadas)} saltadas por no llegar "
          f"a {args.minimo} fotos usables")
    print(f"{total:,} fotos en {raiz}")
    print(f"créditos en {raiz / 'creditos.csv'} — la atribución CC-BY no es opcional")


def prueba():
    """Comprobación mínima: que las dos consultas devuelven lo que se espera."""
    es = especies_mas_fotografiadas(3)
    assert len(es) >= 2, es
    assert all(e["especie"] and e["clave"] for e in es), es
    assert es[0]["disponibles"] >= es[-1]["disponibles"], "vienen sin ordenar"

    assert not usable("http://creativecommons.org/licenses/by-nc-sa/4.0/")
    assert not usable("http://creativecommons.org/licenses/by-nc/4.0/")
    assert not usable("http://creativecommons.org/licenses/by-sa/4.0/")
    assert not usable("")
    assert usable("http://creativecommons.org/licenses/by/4.0/")
    assert usable("http://creativecommons.org/publicdomain/zero/1.0/")

    assert de_campo("https://inaturalist-open-data.s3.amazonaws.com/photos/1/medium.jpg")
    assert not de_campo("http://sweetgum.nybg.org/images3/1811/680/02494665.jpg")
    assert not de_campo("https://multimedia.agouti.eu/x.jpg")
    assert not de_campo("https://collections.nmnh.si.edu/x.jpg")

    inat = "https://inaturalist-open-data.s3.amazonaws.com/photos/654539711/"
    assert encoger(inat + "original.jpg") == inat + "medium.jpg"
    assert encoger(inat + "original.jpeg") == inat + "medium.jpeg"
    assert encoger(inat + "medium.jpg") == inat + "medium.jpg"
    otra = "https://example.org/foto/original.jpg"
    assert encoger(otra) == otra, "no tocar lo que no reconozco"

    fotos = fotos_de(es[0]["clave"], 5)
    assert 0 < len(fotos) <= 5, len(fotos)
    assert all(f["url"].startswith("http") for f in fotos), fotos
    assert all(usable(f["licencia"]) for f in fotos), "se coló una licencia NC"
    print(f"ok · {es[0]['especie']} · {len(fotos)} fotos · {fotos[0]['licencia']}")


if __name__ == "__main__":
    if "--prueba" in sys.argv:
        prueba()
    else:
        main()
