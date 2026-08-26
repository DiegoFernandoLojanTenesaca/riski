"""Fase 5: pasa el modelo de cantos a ONNX, lo cuantiza y mide qué cuesta.

    python exportar_audio.py --datos C:/datos/riksi-audio

Igual que `exportar.py` pero con audio, y con dos diferencias que no son
cosméticas:

**Hay que usar el exportador nuevo** (`dynamo=True`). El viejo no sabe exportar
el STFT porque trabaja con números complejos, y el espectrograma va dentro del
modelo.

**No se cuantiza todo.** Las convoluciones y la capa final sí, que es donde está
el peso del fichero. El espectrograma se queda en coma flotante: redondear a
enteros una transformada de Fourier estropea justo la información fina que
distingue dos cantos, y a cambio no ahorra casi nada, porque el mel no tiene
pesos que guardar.
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import onnxruntime as ort
import torch
from onnxruntime.quantization import CalibrationDataReader, QuantFormat, QuantType, quantize_static
from torch.utils.data import DataLoader, Subset

from entrenar_audio import Cantos, Oido, catalogar, partir_por_grabacion


class Calibracion(CalibrationDataReader):
    """Unas cuantas ventanas reales para fijar las escalas de la cuantización."""

    def __init__(self, cargador, entrada, maximo=100):
        self.entrada = entrada
        lotes, vistas = [], 0
        for x, _ in cargador:
            lotes.append(x.numpy())
            vistas += len(x)
            if vistas >= maximo:
                break
        self.it = iter(lotes)

    def get_next(self):
        lote = next(self.it, None)
        return None if lote is None else {self.entrada: lote}


def medir(ses_o_modelo, cargador, disp="cpu", k=3):
    """top1 y top3, con la misma cuenta para PyTorch y para ONNX."""
    t1 = tk = n = 0
    es_onnx = isinstance(ses_o_modelo, ort.InferenceSession)
    if es_onnx:
        entrada = ses_o_modelo.get_inputs()[0].name
    for x, y in cargador:
        if es_onnx:
            salida = ses_o_modelo.run(None, {entrada: x.numpy()})[0]
        else:
            with torch.no_grad():
                salida = ses_o_modelo(x.to(disp)).cpu().numpy()
        top = np.argsort(-salida, axis=1)[:, :k]
        y = y.numpy()
        t1 += (top[:, 0] == y).sum()
        tk += (top == y[:, None]).any(axis=1).sum()
        n += len(y)
    return t1 / n, tk / n


def mb(ruta):
    ruta = Path(ruta)
    total = ruta.stat().st_size
    datos = ruta.with_suffix(ruta.suffix + ".data")
    if datos.exists():
        total += datos.stat().st_size
    return total / 1024 ** 2


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--datos", default="C:/datos/riksi-audio")
    p.add_argument("--modelo", default="modelo-audio/riksi-audio.pt")
    p.add_argument("--salida", default="modelo-audio")
    p.add_argument("--muestras", type=int, default=400,
                   help="ventanas de validación para medir (ONNX en CPU es lento)")
    p.add_argument("--minimo", type=int, default=30, help="el mismo que se usó al entrenar")
    args = p.parse_args()

    ckpt = torch.load(args.modelo, map_location="cpu", weights_only=False)
    clases = ckpt["clases"]
    modelo = Oido(ckpt["arquitectura"], len(clases))
    modelo.load_state_dict(ckpt["modelo"])
    modelo.eval()

    ficheros, clases_disco = catalogar(Path(args.datos), args.minimo)
    assert clases_disco == clases, "las clases del disco no son las del checkpoint"
    _, idx_va = partir_por_grabacion(ficheros)
    va = Subset(Cantos(ficheros, clases, False), idx_va[:args.muestras])
    cargador = DataLoader(va, batch_size=8, num_workers=4)

    salida = Path(args.salida)
    fp32, int8 = salida / "riksi-audio-fp32.onnx", salida / "riksi-audio-int8.onnx"
    largo = ckpt["frecuencia"] * ckpt["segundos"]

    print(f"{len(clases)} especies · {len(va)} ventanas de validación\n")

    torch.onnx.export(
        modelo, (torch.randn(1, largo),), str(fp32),
        input_names=["audio"], output_names=["logits"],
        dynamic_axes={"audio": {0: "lote"}, "logits": {0: "lote"}},
        opset_version=17, dynamo=True,
    )

    quantize_static(
        str(fp32), str(int8),
        Calibracion(cargador, "audio"),
        quant_format=QuantFormat.QDQ,
        activation_type=QuantType.QUInt8,
        weight_type=QuantType.QInt8,
        per_channel=True,
        # Solo la red, no el espectrograma: los MatMul del banco de filtros mel
        # y el STFT se quedan en float.
        op_types_to_quantize=["Conv", "Gemm"],
    )

    a1_t, a3_t = medir(modelo, cargador)
    a1_f, a3_f = medir(ort.InferenceSession(str(fp32), providers=["CPUExecutionProvider"]), cargador)
    a1_q, a3_q = medir(ort.InferenceSession(str(int8), providers=["CPUExecutionProvider"]), cargador)

    print(f"{'variante':<16}{'tamaño':>10}{'top1':>9}{'top3':>9}")
    print(f"{'PyTorch':<16}{'-':>10}{a1_t:>8.1%}{a3_t:>9.1%}")
    print(f"{'ONNX float32':<16}{mb(fp32):>9.1f}M{a1_f:>8.1%}{a3_f:>9.1%}")
    print(f"{'ONNX int8':<16}{mb(int8):>9.1f}M{a1_q:>8.1%}{a3_q:>9.1%}")
    print(f"\nencoge {mb(fp32)/mb(int8):.1f}× · cuesta {100*(a1_f-a1_q):.1f} puntos de top1")

    (salida / "metricas.json").write_text(json.dumps({
        "arquitectura": ckpt["arquitectura"],
        "frecuencia": ckpt["frecuencia"], "segundos": ckpt["segundos"],
        "clases": len(clases), "ventanas_validacion": len(va),
        "pytorch": {"top1": float(a1_t), "top3": float(a3_t)},
        "fp32": {"mb": mb(fp32), "top1": float(a1_f), "top3": float(a3_f)},
        "int8": {"mb": mb(int8), "top1": float(a1_q), "top3": float(a3_q)},
        "coste_top1": float(a1_f - a1_q),
    }, indent=1), encoding="utf-8")

    (salida / "clases.json").write_text(json.dumps(clases, ensure_ascii=False, indent=1), encoding="utf-8")
    (salida / "preprocesado.json").write_text(json.dumps({
        "frecuencia": ckpt["frecuencia"], "segundos": ckpt["segundos"],
        "nota": "el navegador solo tiene que mandar audio mono a esta frecuencia; "
                "el espectrograma lo hace el propio modelo",
    }, indent=1), encoding="utf-8")
    print(f"clases y preprocesado en {salida}/")


if __name__ == "__main__":
    main()
