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

import csv
import json
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


def muestras(datos, clases, comunes, cuantas=24):
    """Fotos de portada, con su autor, su licencia y su grupo.

    Se reparten a lo largo del listado en vez de tomar las primeras: alfabético
    seguido saldrían ocho plantas del mismo género. Y cada una viaja con su
    crédito, que en CC-BY la atribución no es opcional.
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

    destino = WEB / "muestras"
    destino.mkdir(exist_ok=True)
    for viejo in destino.glob("*.jpg"):
        viejo.unlink()

    paso = max(1, len(clases) // cuantas)
    salida = []
    for nombre in clases[::paso][:cuantas]:
        fotos = sorted((datos / "imagenes" / nombre).glob("*.jpg"))
        if not fotos:
            continue
        foto = fotos[len(fotos) // 2]
        shutil.copy(foto, destino / foto.name)
        autor, licencia = creditos.get(foto.name, ("", ""))
        salida.append({
            "archivo": foto.name,
            "especie": nombre.replace("_", " "),
            "comun": comunes.get(nombre, ""),
            "grupo": grupos.get(nombre, ""),
            "autor": autor,
            "licencia": "CC0" if "zero" in licencia else "CC-BY",
        })
    (destino / "muestras.json").write_text(
        json.dumps(salida, ensure_ascii=False, indent=1), encoding="utf-8")

    # Nombre fijo para la imagen que comparten Facebook, WhatsApp o Telegram:
    # og:image no puede apuntar a un archivo que cambia de nombre en cada
    # regeneración del dataset.
    if salida:
        shutil.copy(destino / salida[0]["archivo"], WEB / "portada.jpg")
    return salida


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    origen = Path(sys.argv[1] if len(sys.argv) > 1 else "modelo-efficientnet_lite0")
    datos = Path("C:/datos/riksi")

    (WEB / "modelo").mkdir(parents=True, exist_ok=True)
    for f in ("riksi-int8.onnx", "clases.json", "preprocesado.json"):
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

    galeria = muestras(datos, clases, comunes)
    print(f"muestras · {len(galeria)} fotos de portada con crédito")

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
    print("ahora: abre docs/app.html?test=1 (con un servidor, no file://)")


if __name__ == "__main__":
    main()
