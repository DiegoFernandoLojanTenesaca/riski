"""Que lo publicado siga siendo cierto. Lo que corre en el CI.

Va en un fichero y no dentro del YAML del workflow por una razón práctica: un
script metido en un `run: |` con heredoc se puede correr en local exactamente
igual, y el YAML deja de tener lógica escondida entre comillas anidadas.

Comprueba tres cosas, todas sobre ficheros que están en el repositorio:

- que el modelo publicado prediga lo mismo que el día que se exportó;
- que el porcentaje del README salga de `metricas.json` y no de la memoria;
- que las páginas no referencien ficheros que no existen.

    python comprobaciones.py
"""

import json
import pathlib
import re
import sys

AQUI = pathlib.Path(__file__).parent
DOCS = AQUI / "docs"


def modelo_reproduce():
    """El `.onnx` publicado, sobre la foto de prueba.

    **Un preprocesado que deja de coincidir con el del entrenamiento no lanza
    ningún error**: el modelo responde igual, solo que peor, y la culpa se le
    echa al modelo. Esto es lo que lo detecta.

    Sobre `docs/prueba` y no sobre el banco de 200 imágenes: el banco son 11 MB
    que el `.gitignore` excluye a propósito, así que en un clon limpio no
    existe.
    """
    import numpy as np
    import onnxruntime as ort
    from PIL import Image

    modelo = DOCS / "modelo"
    pre = json.loads((modelo / "preprocesado.json").read_text(encoding="utf-8"))
    clases = json.loads((modelo / "clases.json").read_text(encoding="utf-8"))
    esperado = json.loads((DOCS / "prueba" / "esperado.json").read_text(encoding="utf-8"))

    sesion = ort.InferenceSession(str(modelo / "riksi-int8.onnx"),
                                  providers=["CPUExecutionProvider"])

    im = Image.open(DOCS / "prueba" / esperado["archivo"]).convert("RGB")
    escala = pre["resize"] / min(im.size)
    im = im.resize((round(im.width * escala), round(im.height * escala)),
                   Image.BILINEAR)
    tam = pre["tam"]
    izq, arriba = (im.width - tam) // 2, (im.height - tam) // 2
    im = im.crop((izq, arriba, izq + tam, arriba + tam))
    x = np.asarray(im, dtype=np.float32) / 255.0
    x = (x - np.array(pre["media"], np.float32)) / np.array(pre["desv"], np.float32)

    salida = sesion.run(None, {sesion.get_inputs()[0].name:
                               x.transpose(2, 0, 1)[None]})[0][0]
    e = np.exp(salida - salida.max())
    probs = e / e.sum()
    i = int(np.argmax(probs))

    assert clases[i] == esperado["clase"], (
        f"el modelo dice {clases[i]} y debería decir {esperado['clase']}: "
        f"o se reexportó distinto, o el preprocesado cambió")

    # La tolerancia sale del propio fichero, que la escribió `comprobar.py` al
    # generarlo: absorbe las diferencias de redondeo entre versiones de Pillow y
    # de onnxruntime, que no son un fallo.
    desvio = abs(float(probs[i]) - esperado["prob"])
    assert desvio < esperado.get("tolerancia", 0.05), (
        f"la confianza se desvía {desvio:.4f}, más de lo tolerado")

    return f"{clases[i]} {probs[i]:.4f} · desvío {desvio:.4f}"


def readme_al_dia():
    """Que el porcentaje del README salga de `metricas.json`.

    Copiado a mano se queda viejo en cuanto se reentrena, y nadie lo nota porque
    sigue siendo un número plausible.
    """
    m = json.loads((DOCS / "modelo" / "metricas.json").read_text(encoding="utf-8"))
    readme = (AQUI / "README.md").read_text(encoding="utf-8")
    esperado = f"{m['int8']['top1'] * 100:.1f}".replace(".", ",")
    assert esperado in readme, (
        f"el README no menciona {esperado} %, que es lo que dice "
        f"metricas.json. ¿Se reentrenó sin actualizarlo?")
    return f"README y metricas.json coinciden en {esperado} %"


def paginas_completas():
    """Que ningún `src` apunte a un fichero que no está.

    No da error en el servidor: da una página que carga a medias y un modelo que
    nunca llega.
    """
    faltan = []
    for html in DOCS.glob("*.html"):
        texto = html.read_text(encoding="utf-8")
        for ref in re.findall(r'(?:src|href)="([^":#?]+\.(?:js|css|json|svg|onnx|wasm))"',
                              texto):
            if not (DOCS / ref).exists():
                faltan.append(f"{html.name} → {ref}")
    assert not faltan, "referencias rotas: " + ", ".join(faltan)
    return f"{len(list(DOCS.glob('*.html')))} páginas, sin referencias rotas"


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    for comprobacion in (modelo_reproduce, readme_al_dia, paginas_completas):
        print(f"  ok · {comprobacion()}")


if __name__ == "__main__":
    main()
