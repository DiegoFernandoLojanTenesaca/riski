"""Fase 4, red de seguridad: deja lo que la web necesita y con qué compararse.

    python comprobar.py

Hace dos cosas pequeñas y una importante:

- copia el modelo ganador a `docs/modelo/`,
- escribe `docs/modelo/comunes.json` (nombre en español por especie),
- y deja en `docs/prueba/` una imagen real con el resultado que da **Python**,
  para que `docs/app.html?test=1` compruebe que el navegador saca lo mismo.

Lo tercero es el punto. Si el preprocesado del navegador no replica el del
entrenamiento —un resize distinto, el orden de canales, olvidar la
normalización— el modelo no falla: acierta menos. Sin este contraste, eso se
confunde con "el modelo es malo" y se buscan meses en el sitio equivocado.
"""

import argparse
import csv
import json
import random
import shutil
import sys
from pathlib import Path

import numpy as np
import onnxruntime as ort
from PIL import Image

AQUI = Path(__file__).parent
WEB = AQUI / "docs"   # docs/ y no web/: GitHub Pages publica esa carpeta sin workflow
TOLERANCIA = 0.05      # el canvas no interpola igual que PIL; ~1-2 puntos es normal


def preparar(ruta, pre):
    """El mismo preprocesado que `transformaciones()` de entrenar.py."""
    im = Image.open(ruta).convert("RGB")
    corto = min(im.size)
    escala = pre["resize"] / corto
    im = im.resize((round(im.width * escala), round(im.height * escala)), Image.BILINEAR)

    tam = pre["tam"]
    izq, arriba = (im.width - tam) // 2, (im.height - tam) // 2
    im = im.crop((izq, arriba, izq + tam, arriba + tam))

    x = np.asarray(im, dtype=np.float32) / 255.0
    x = (x - np.array(pre["media"], dtype=np.float32)) / np.array(pre["desv"], dtype=np.float32)
    return x.transpose(2, 0, 1)[None]


def softmax(v):
    e = np.exp(v - v.max())
    return e / e.sum()


# GBIF devuelve la clase taxonómica en latín. En la portada va el nombre que
# usaría cualquiera, no el del árbol de Linneo.
GRUPOS = {
    "Aves": "Aves", "Magnoliopsida": "Plantas", "Liliopsida": "Plantas",
    "Polypodiopsida": "Helechos", "Pinopsida": "Plantas", "Insecta": "Insectos",
    "Arachnida": "Arácnidos", "Malacostraca": "Crustáceos", "Reptilia": "Reptiles",
    "Squamata": "Reptiles", "Testudines": "Tortugas", "Mammalia": "Mamíferos",
    "Amphibia": "Anfibios", "Actinopterygii": "Peces", "Elasmobranchii": "Tiburones y rayas",
    "Gastropoda": "Caracoles", "Anthozoa": "Corales", "Bivalvia": "Moluscos",
}


def galeria(datos, clases, comunes, ancho=480):
    """Una foto por especie para el catálogo de la web, con su crédito.

    Se guardan reducidas a 480 px y no las originales: cien fotos de 150 KB
    serían 15 MB en el repositorio para verse en tarjetas de 250 px. Cada una
    viaja con su autor y su licencia, que en CC-BY la atribución no es opcional.
    """
    creditos = {}
    ruta_creditos = datos / "creditos.csv"
    if ruta_creditos.exists():
        with open(ruta_creditos, encoding="utf-8") as fh:
            for fila in csv.DictReader(fh):
                creditos[fila["archivo"]] = (fila["autor"], fila["licencia"])

    grupos = {}
    ruta_especies = datos / "especies.csv"
    if ruta_especies.exists():
        with open(ruta_especies, encoding="utf-8") as fh:
            for fila in csv.DictReader(fh):
                grupos[fila["especie"].replace(" ", "_")] = GRUPOS.get(fila["grupo"], fila["grupo"])

    destino = WEB / "catalogo"
    destino.mkdir(exist_ok=True)
    for viejo in destino.glob("*.jpg"):
        viejo.unlink()

    salida = []
    for nombre in clases:
        fotos = sorted((datos / "imagenes" / nombre).glob("*.jpg"))
        if not fotos:
            continue
        # La del medio y no la primera: las primeras de cada especie suelen ser
        # de la misma observación y salen casi iguales entre sí.
        foto = fotos[len(fotos) // 2]
        im = Image.open(foto).convert("RGB")
        if im.width > ancho:
            im = im.resize((ancho, round(im.height * ancho / im.width)), Image.LANCZOS)
        im.save(destino / foto.name, quality=82, optimize=True)

        autor, licencia = creditos.get(foto.name, ("", ""))
        salida.append({
            "archivo": foto.name,
            "especie": nombre.replace("_", " "),
            "comun": comunes.get(nombre, ""),
            "grupo": grupos.get(nombre, ""),
            "fotos": len(fotos),
            "autor": autor,
            "licencia": "CC0" if "zero" in licencia else "CC-BY",
        })
    (destino / "catalogo.json").write_text(
        json.dumps(salida, ensure_ascii=False, indent=1), encoding="utf-8")

    # Nombre fijo para la imagen que comparten Facebook, WhatsApp o Telegram:
    # og:image no puede apuntar a un archivo que cambia de nombre cada vez que
    # se regenera el dataset.
    if salida:
        shutil.copy(destino / salida[0]["archivo"], WEB / "portada.jpg")
    return salida


def indices_validacion(datos, clases, minimo=50):
    """Las mismas imágenes de validación que usó el entrenamiento, barajadas.

    Los índices vienen agrupados por clase, así que cortar sin barajar daba las
    primeras especies del alfabeto y nada más. Semilla fija para que dos
    corridas se puedan comparar entre sí.
    """
    from torchvision.datasets import ImageFolder
    from entrenar import filtrar_clases, partir_por_observacion

    base = filtrar_clases(ImageFolder(datos / "imagenes", allow_empty=True), minimo)
    assert base.classes == clases, "las clases del disco no son las del modelo"
    _, idx_va = partir_por_observacion(base)
    idx_va = list(idx_va)
    random.Random(7).shuffle(idx_va)
    return base, idx_va


def calibrar(datos, clases, pre, ses, cuantas=1000, objetivo=0.85, minimo=50):
    """A partir de qué confianza se puede afirmar una determinación.

    El umbral estaba puesto a ojo en 0,40 y eso es una decisión con
    consecuencias: demasiado alto y la aplicación duda de aciertos buenos,
    demasiado bajo y afirma barbaridades. Aquí se mide de verdad: para cada
    corte se calcula cuántas respuestas se dan (cobertura) y qué porcentaje de
    esas es correcto (precisión), y se elige el corte más bajo que llegue al
    objetivo. Bajo es mejor: cada punto de umbral de más es una respuesta
    correcta que se calla.
    """
    base, idx_va = indices_validacion(datos, clases, minimo)
    entrada = ses.get_inputs()[0].name

    casos = []
    for i in idx_va[:cuantas]:
        ruta, verdadera = base.samples[i]
        probs = softmax(ses.run(None, {entrada: preparar(Path(ruta), pre)})[0][0])
        casos.append((float(probs.max()), int(probs.argmax()) == verdadera))

    curva = []
    for corte in [c / 100 for c in range(10, 95, 5)]:
        aceptados = [ok for p, ok in casos if p >= corte]
        if not aceptados:
            continue
        curva.append({
            "umbral": corte,
            "cobertura": round(len(aceptados) / len(casos), 4),
            "precision": round(sum(aceptados) / len(aceptados), 4),
        })

    bueno = next((c for c in curva if c["precision"] >= objetivo), curva[-1])
    salida = {
        "umbral": bueno["umbral"],
        "precision": bueno["precision"],
        "cobertura": bueno["cobertura"],
        "objetivo": objetivo,
        "imagenes": len(casos),
        "curva": curva,
        "nota": "por debajo de este umbral la ficha sale con cf.",
    }
    (WEB / "modelo" / "umbral.json").write_text(
        json.dumps(salida, ensure_ascii=False, indent=1), encoding="utf-8")
    return salida


def medir_espejo(datos, clases, pre, ses, cuantas=500, minimo=50):
    """¿Compensa preguntarle también por la imagen volteada?

    Promediar la predicción de la foto y la de su espejo es lo más barato que
    hay para arañar precisión: no toca el modelo ni engorda la descarga, solo
    duplica el tiempo de respuesta. Duplicar 60 ms se puede permitir; ganar
    medio punto por ese precio, quizá no. Por eso se mide antes de ponerlo.
    """
    base, idx_va = indices_validacion(datos, clases, minimo)
    entrada = ses.get_inputs()[0].name

    solo = ambas = n = 0
    for i in idx_va[:cuantas]:
        ruta, verdadera = base.samples[i]
        x = preparar(Path(ruta), pre)
        p1 = softmax(ses.run(None, {entrada: x})[0][0])
        p2 = softmax(ses.run(None, {entrada: x[..., ::-1].copy()})[0][0])
        solo += int(p1.argmax()) == verdadera
        ambas += int((p1 + p2).argmax()) == verdadera
        n += 1
    return solo / n, ambas / n, n


def banco(datos, clases, pre, ses, cuantas, minimo=50, ancho=480):
    """Deja un lote de validación servible por HTTP con su veredicto de Python.

    La prueba de una sola imagen dice si el preprocesado está *roto*. No dice
    cuánto cuesta: el `canvas` no reduce igual que PIL, y esa diferencia se
    paga en puntos de precisión que nadie ha medido. Con doscientas imágenes
    etiquetadas el navegador puede calcular su propio acierto y compararlo con
    el de Python sobre exactamente las mismas fotos.

    El banco NO va al repositorio (lo excluye .gitignore): son megas que solo
    sirven para medir en local.
    """
    base, idx_va = indices_validacion(datos, clases, minimo)

    destino = WEB / "banco"
    destino.mkdir(exist_ok=True)
    for viejo in destino.glob("*.jpg"):
        viejo.unlink()

    entrada = ses.get_inputs()[0].name
    filas, aciertos = [], 0
    for i in idx_va[:cuantas]:
        ruta, verdadera = base.samples[i]
        ruta = Path(ruta)
        im = Image.open(ruta).convert("RGB")
        if im.width > ancho:
            im = im.resize((ancho, round(im.height * ancho / im.width)), Image.LANCZOS)
        copia = destino / ruta.name
        im.save(copia, quality=88)

        # Python mide sobre la MISMA copia reducida que va a recibir el
        # navegador. Si midiera el original, la diferencia entre los dos
        # incluiría este reescalado y no solo el del canvas, que es lo que se
        # quiere aislar.
        probs = softmax(ses.run(None, {entrada: preparar(copia, pre)})[0][0])
        elegida = int(probs.argmax())
        aciertos += elegida == verdadera

        filas.append({
            "archivo": ruta.name,
            "verdadera": clases[verdadera],
            "python": clases[elegida],
            "prob": round(float(probs[elegida]), 4),
        })

    (destino / "banco.json").write_text(json.dumps({
        "imagenes": filas,
        "top1_python": round(aciertos / len(filas), 4),
        "nota": "las fotos van reducidas a 480 px, igual que las verá el navegador",
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    return aciertos / len(filas), len(filas)


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--modelo", default="modelo-efficientnet_lite0")
    p.add_argument("--datos", default="C:/datos/riksi")
    p.add_argument("--calibrar", type=int, default=0,
                   help="imágenes para elegir el umbral del cf. con datos")
    p.add_argument("--espejo", type=int, default=0,
                   help="imágenes para ver si promediar con la imagen volteada compensa")
    p.add_argument("--banco", type=int, default=0,
                   help="imágenes de validación para medir el navegador contra Python")
    args = p.parse_args()
    origen = Path(args.modelo)
    datos = Path(args.datos)

    (WEB / "modelo").mkdir(parents=True, exist_ok=True)
    # metricas.json viaja con el modelo: si se queda la medición del anterior,
    # la portada publica cifras de un modelo que ya no es el que corre.
    for f in ("riksi-int8.onnx", "clases.json", "preprocesado.json", "metricas.json"):
        if (origen / f).exists():
            shutil.copy(origen / f, WEB / "modelo" / f)
    print(f"modelo de {origen} → docs/modelo/")

    clases = json.loads((WEB / "modelo" / "clases.json").read_text(encoding="utf-8"))
    pre = json.loads((WEB / "modelo" / "preprocesado.json").read_text(encoding="utf-8"))

    # Nombre común: quien está en el campo no busca «Amblyrhynchus cristatus».
    csv_especies = datos / "especies.csv"
    comunes = {}
    if csv_especies.exists():
        with open(csv_especies, encoding="utf-8") as fh:
            for fila in csv.DictReader(fh):
                nombre = fila["especie"].replace(" ", "_")
                if fila.get("comun") and nombre in clases:
                    comunes[nombre] = fila["comun"]
    (WEB / "modelo" / "comunes.json").write_text(
        json.dumps(comunes, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"comunes.json · {len(comunes)}/{len(clases)} especies con nombre en español")

    catalogo = galeria(datos, clases, comunes)
    print(f"catálogo · {len(catalogo)} fotos reducidas con crédito")

    # Una foto real, no un tensor sintético: el fallo que se busca está en el
    # camino JPEG → píxeles, y con ruido aleatorio no aparece.
    carpeta = datos / "imagenes" / clases[0]
    muestra = sorted(carpeta.glob("*.jpg"))[0]
    ses = ort.InferenceSession(str(WEB / "modelo" / "riksi-int8.onnx"),
                               providers=["CPUExecutionProvider"])
    probs = softmax(ses.run(None, {ses.get_inputs()[0].name: preparar(muestra, pre)})[0][0])
    i = int(probs.argmax())

    (WEB / "prueba").mkdir(exist_ok=True)
    shutil.copy(muestra, WEB / "prueba" / muestra.name)
    (WEB / "prueba" / "esperado.json").write_text(json.dumps({
        "archivo": muestra.name,
        "clase": clases[i],
        "prob": float(probs[i]),
        "tolerancia": TOLERANCIA,
        "nota": "generado por comprobar.py · abre docs/app.html?test=1 y compara",
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    assert clases[i] == carpeta.name, f"el modelo falla su propia clase: {clases[i]} != {carpeta.name}"
    print(f"prueba · {muestra.name} → {clases[i]} {probs[i]:.3f}")

    if args.calibrar:
        u = calibrar(datos, clases, pre, ses, args.calibrar)
        print(f"umbral · {u['umbral']:.2f} → responde en el {u['cobertura']:.0%} "
              f"de los casos y acierta el {u['precision']:.0%} de esas veces "
              f"({u['imagenes']} imágenes)")

    if args.espejo:
        solo, ambas, n = medir_espejo(datos, clases, pre, ses, args.espejo)
        print(f"espejo · {n} imágenes · sola {solo:.1%} · promediando con su espejo "
              f"{ambas:.1%} · gana {100 * (ambas - solo):+.1f} puntos por el doble de tiempo")

    if args.banco:
        acierto, n = banco(datos, clases, pre, ses, args.banco)
        print(f"banco · {n} imágenes · python acierta {acierto:.1%}")
        print("compara con el navegador en banco.html")

    print("ahora: abre docs/app.html?test=1 (con un servidor, no file://)")


if __name__ == "__main__":
    main()
