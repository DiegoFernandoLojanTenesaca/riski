"""Fase 3: pasa el modelo a ONNX, lo cuantiza a 8 bits y mide qué cuesta.

    python exportar.py --datos C:/datos/riksi

La cuantización no es gratis: encoge el modelo unas cuatro veces y algo de
precisión se pierde. Este script mide las tres variantes sobre el MISMO conjunto
de validación —PyTorch, ONNX float32 y ONNX int8— para poder decidir con un
número delante en vez de por fe.

Para CNN hace falta cuantización estática con calibración: la dinámica apenas
toca las convoluciones, que es justo donde está el peso de MobileNet.
"""

import argparse
import sys
import json
from pathlib import Path

import numpy as np
import onnx
import onnxruntime as ort
import timm
import torch
from onnxruntime.quantization import CalibrationDataReader, QuantFormat, QuantType, quantize_static
from torch.utils.data import DataLoader, Subset
from torchvision.datasets import ImageFolder

from entrenar import evaluar, filtrar_clases, partir_por_observacion, transformaciones


class Calibracion(CalibrationDataReader):
    """Le da al cuantizador un puñado de imágenes reales para fijar las escalas."""

    def __init__(self, cargador, entrada, maximo=200):
        self.entrada = entrada
        lotes = []
        vistas = 0
        for x, _ in cargador:
            lotes.append(x.numpy())
            vistas += len(x)
            if vistas >= maximo:
                break
        self.it = iter(lotes)

    def get_next(self):
        lote = next(self.it, None)
        return None if lote is None else {self.entrada: lote}


def medir_onnx(ruta, cargador, k=3):
    ses = ort.InferenceSession(str(ruta), providers=["CPUExecutionProvider"])
    entrada = ses.get_inputs()[0].name
    t1 = tk = n = 0
    for x, y in cargador:
        salida = ses.run(None, {entrada: x.numpy()})[0]
        top = np.argsort(-salida, axis=1)[:, :k]
        y = y.numpy()
        t1 += (top[:, 0] == y).sum()
        tk += (top == y[:, None]).any(axis=1).sum()
        n += len(y)
    return t1 / n, tk / n


def mb(ruta):
    """Tamaño real, contando los pesos externos.

    El exportador nuevo de PyTorch deja el grafo en el `.onnx` y los pesos en un
    `.onnx.data` aparte: mirar solo el primero daba 0,3 MB para un modelo de 16,7
    y hacía que la comparación con el cuantizado saliera del revés.
    """
    ruta = Path(ruta)
    total = ruta.stat().st_size
    datos = ruta.with_suffix(ruta.suffix + ".data")
    if datos.exists():
        total += datos.stat().st_size
    return total / 1024 ** 2


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--datos", default="C:/datos/riksi")
    p.add_argument("--modelo", default="modelo/riksi.pt")
    p.add_argument("--salida", default="modelo")
    p.add_argument("--muestras", type=int, default=1000,
                   help="imágenes de validación para medir (ONNX en CPU es lento)")
    p.add_argument("--minimo", type=int, default=50, help="el mismo que se usó al entrenar")
    args = p.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    ckpt = torch.load(args.modelo, map_location="cpu", weights_only=False)
    clases = ckpt["clases"]
    modelo = timm.create_model(ckpt["arquitectura"], pretrained=False, num_classes=len(clases))
    modelo.load_state_dict(ckpt["modelo"])
    modelo.eval()
    # La resolución viaja en el checkpoint: exportar a 224 un modelo entrenado
    # a 288 no da error, solo destroza la precisión sin decir por qué.
    tam = ckpt.get("tam", 224)

    raiz = Path(args.datos) / "imagenes"
    _, t_prueba = transformaciones(tam)
    # Mismo filtro que en el entrenamiento, o las clases no coinciden.
    base = filtrar_clases(ImageFolder(raiz, allow_empty=True), args.minimo)
    assert base.classes == clases, "las clases del disco no son las del checkpoint"
    _, idx_va = partir_por_observacion(base)
    idx_va = idx_va[:args.muestras]
    va = Subset(filtrar_clases(ImageFolder(raiz, t_prueba, allow_empty=True), args.minimo), idx_va)
    cargador = DataLoader(va, batch_size=32, num_workers=4)

    salida = Path(args.salida)
    fp32 = salida / "riksi-fp32.onnx"
    int8 = salida / "riksi-int8.onnx"

    print(f"{len(clases)} clases · {len(idx_va):,} imágenes de validación\n")

    torch.onnx.export(
        modelo, torch.randn(1, 3, tam, tam), str(fp32),
        input_names=["imagen"], output_names=["logits"],
        dynamic_axes={"imagen": {0: "lote"}, "logits": {0: "lote"}},
        opset_version=17,
    )
    onnx.checker.check_model(onnx.load(str(fp32)))

    quantize_static(
        str(fp32), str(int8),
        Calibracion(cargador, "imagen"),
        quant_format=QuantFormat.QDQ,
        activation_type=QuantType.QUInt8,
        weight_type=QuantType.QInt8,
        per_channel=True,
    )

    disp = "cuda" if torch.cuda.is_available() else "cpu"
    a1_t, a3_t = evaluar(modelo.to(disp), cargador, disp)
    a1_f, a3_f = medir_onnx(fp32, cargador)
    a1_q, a3_q = medir_onnx(int8, cargador)

    print(f"{'variante':<16}{'tamaño':>10}{'top1':>9}{'top3':>9}")
    print(f"{'PyTorch':<16}{'—':>10}{a1_t:>8.1%}{a3_t:>9.1%}")
    print(f"{'ONNX float32':<16}{mb(fp32):>9.1f}M{a1_f:>8.1%}{a3_f:>9.1%}")
    print(f"{'ONNX int8':<16}{mb(int8):>9.1f}M{a1_q:>8.1%}{a3_q:>9.1%}")
    print(f"\nencoge {mb(fp32)/mb(int8):.1f}× · cuesta {100*(a1_f-a1_q):.1f} puntos de top1")

    # A disco, no solo a la consola: sin esto la comparación entre arquitecturas
    # se copia a mano al README y a la siguiente ya no se sabe qué se comparaba.
    (salida / "metricas.json").write_text(json.dumps({
        "arquitectura": ckpt["arquitectura"],
        "tam": tam,
        "clases": len(clases),
        "imagenes_validacion": len(idx_va),
        "pytorch": {"top1": float(a1_t), "top3": float(a3_t)},
        "fp32": {"mb": mb(fp32), "top1": float(a1_f), "top3": float(a3_f)},
        "int8": {"mb": mb(int8), "top1": float(a1_q), "top3": float(a3_q)},
        "coste_top1": float(a1_f - a1_q),
    }, indent=1), encoding="utf-8")

    (salida / "clases.json").write_text(json.dumps(clases, ensure_ascii=False, indent=1), encoding="utf-8")
    (salida / "preprocesado.json").write_text(json.dumps({
        "tam": tam, "resize": tam * 256 // 224,
        "media": [0.485, 0.456, 0.406], "desv": [0.229, 0.224, 0.225],
        "nota": "la web tiene que hacer exactamente esto antes de invocar el modelo",
    }, indent=1), encoding="utf-8")
    print(f"clases y preprocesado en {salida}/")


if __name__ == "__main__":
    main()
