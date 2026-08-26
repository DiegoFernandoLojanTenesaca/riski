"""Fase 5: pasa el modelo de cantos a ONNX, lo cuantiza y mide qué cuesta.

    python exportar_audio.py --datos C:/datos/riksi-audio

Igual que `exportar.py` pero con audio, y con dos diferencias que no son
cosméticas:

**Hay que usar el exportador nuevo** (`dynamo=True`). El viejo no sabe exportar
el STFT porque trabaja con números complejos, y el espectrograma va dentro del
modelo.

**Aquí gana float16, no int8.** Medido sobre las mismas ventanas: los 8 bits
dejan el fichero en 4,2 MB pero cuestan **9 puntos** de acierto, y no hay
calibración que lo arregle (se probaron activaciones con y sin signo, y cuatro
veces más muestras). Los 16 bits pesan 6,9 MB y cuestan 1,3. Un canto se
distingue por diferencias finas en el espectro: la resolución de 8 bits no da
para tanto, y en las fotos sí porque una textura tolera mucho más redondeo.

Se exportan las tres variantes y se miden, pero la que se publica es la de 16
bits. El espectrograma se queda **siempre en 32 bits**: es la misma lección del
NaN, un tono puro desborda el techo de la media precisión dentro del STFT.
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import onnx
import onnxruntime as ort
import torch
from onnxconverter_common import float16
from onnxruntime.quantization import QuantFormat, QuantType, quantize_static
from torch.utils.data import DataLoader, Subset

# Reutilizadas tal cual del exportador de fotos: la lectora de calibración y la
# cuenta del tamaño real no cambian porque la entrada sea audio.
from exportar import Calibracion, mb
from entrenar_audio import Cantos, Oido, catalogar, partir_por_grabacion


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
    fp32 = salida / "riksi-audio-fp32.onnx"
    int8 = salida / "riksi-audio-int8.onnx"
    fp16 = salida / "riksi-audio-fp16.onnx"
    largo = ckpt["frecuencia"] * ckpt["segundos"]

    # Borrar lo de la corrida anterior: el exportador escribe los pesos en un
    # `.onnx.data` aparte y falla con «Invalid argument» si ya existe uno.
    for viejo in (fp32, int8, fp16):
        viejo.unlink(missing_ok=True)
        Path(str(viejo) + ".data").unlink(missing_ok=True)

    print(f"{len(clases)} especies · {len(va)} ventanas de validación\n")

    torch.onnx.export(
        modelo, (torch.randn(1, largo),), str(fp32),
        input_names=["audio"], output_names=["logits"],
        dynamic_axes={"audio": {0: "lote"}, "logits": {0: "lote"}},
        opset_version=17, dynamo=True,
    )

    quantize_static(
        str(fp32), str(int8),
        Calibracion(cargador, "audio", maximo=100),
        quant_format=QuantFormat.QDQ,
        activation_type=QuantType.QUInt8,
        weight_type=QuantType.QInt8,
        per_channel=True,
        # Solo la red, no el espectrograma: los MatMul del banco de filtros mel
        # y el STFT se quedan en float.
        op_types_to_quantize=["Conv", "Gemm"],
    )

    # A 16 bits, dejando fuera el espectrograma: un tono puro desborda el techo
    # de la media precisión dentro del STFT y saldría NaN.
    onnx.save(float16.convert_float_to_float16(
        onnx.load(str(fp32)), keep_io_types=True,
        op_block_list=["STFT", "MatMul", "Div", "Sub", "ReduceMean", "Log"]), str(fp16))

    a1_t, a3_t = medir(modelo, cargador)
    a1_f, a3_f = medir(ort.InferenceSession(str(fp32), providers=["CPUExecutionProvider"]), cargador)
    a1_m, a3_m = medir(ort.InferenceSession(str(fp16), providers=["CPUExecutionProvider"]), cargador)
    a1_q, a3_q = medir(ort.InferenceSession(str(int8), providers=["CPUExecutionProvider"]), cargador)

    print(f"{'variante':<16}{'tamaño':>10}{'top1':>9}{'top3':>9}")
    print(f"{'PyTorch':<16}{'-':>10}{a1_t:>8.1%}{a3_t:>9.1%}")
    print(f"{'ONNX float32':<16}{mb(fp32):>9.1f}M{a1_f:>8.1%}{a3_f:>9.1%}")
    print(f"{'ONNX float16':<16}{mb(fp16):>9.1f}M{a1_m:>8.1%}{a3_m:>9.1%}   <-- el que se publica")
    print(f"{'ONNX int8':<16}{mb(int8):>9.1f}M{a1_q:>8.1%}{a3_q:>9.1%}")
    print(f"\n16 bits: la mitad de tamaño por {100*(a1_f-a1_m):.1f} puntos")
    print(f"8 bits: {mb(fp32)/mb(int8):.1f}x más pequeño, pero cuesta {100*(a1_f-a1_q):.1f} puntos")

    (salida / "metricas.json").write_text(json.dumps({
        "arquitectura": ckpt["arquitectura"],
        "frecuencia": ckpt["frecuencia"], "segundos": ckpt["segundos"],
        "clases": len(clases), "ventanas_validacion": len(va),
        "publicado": "fp16",
        "pytorch": {"top1": float(a1_t), "top3": float(a3_t)},
        "fp32": {"mb": mb(fp32), "top1": float(a1_f), "top3": float(a3_f)},
        "fp16": {"mb": mb(fp16), "top1": float(a1_m), "top3": float(a3_m)},
        "int8": {"mb": mb(int8), "top1": float(a1_q), "top3": float(a3_q)},
        "coste_top1": float(a1_f - a1_m),
    }, indent=1), encoding="utf-8")

    # Su propio umbral, medido sobre el modelo que de verdad se publica. Sin
    # esto la ficha de un canto tendría que callarse o, peor, pedirle prestada
    # la calibración al modelo de fotos.
    ses = ort.InferenceSession(str(fp16), providers=["CPUExecutionProvider"])
    entrada = ses.get_inputs()[0].name
    casos = []
    for x, y in cargador:
        for logits, verdadera in zip(ses.run(None, {entrada: x.numpy()})[0], y.numpy()):
            e = np.exp(logits - logits.max())
            probs = e / e.sum()
            casos.append((float(probs.max()), int(probs.argmax()) == int(verdadera)))

    curva = []
    for corte in [c / 100 for c in range(10, 95, 5)]:
        aceptados = [ok for p, ok in casos if p >= corte]
        if aceptados:
            curva.append({"umbral": corte, "cobertura": round(len(aceptados) / len(casos), 4),
                          "precision": round(sum(aceptados) / len(aceptados), 4)})
    bueno = next((c for c in curva if c["precision"] >= 0.85), curva[-1])
    (salida / "umbral.json").write_text(json.dumps({
        **bueno, "objetivo": 0.85, "imagenes": len(casos), "curva": curva,
        "nota": "por debajo de este umbral la ficha del canto sale con cf.",
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"umbral · {bueno['umbral']:.2f} → responde en el {bueno['cobertura']:.0%} "
          f"de los casos y acierta el {bueno['precision']:.0%} de esas veces")

    (salida / "clases.json").write_text(json.dumps(clases, ensure_ascii=False, indent=1), encoding="utf-8")
    (salida / "preprocesado.json").write_text(json.dumps({
        "frecuencia": ckpt["frecuencia"], "segundos": ckpt["segundos"],
        "nota": "el navegador solo tiene que mandar audio mono a esta frecuencia; "
                "el espectrograma lo hace el propio modelo",
    }, indent=1), encoding="utf-8")
    print(f"clases y preprocesado en {salida}/")


if __name__ == "__main__":
    main()
