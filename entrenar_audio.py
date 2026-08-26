"""Fase 5: entrena el clasificador de cantos.

    python entrenar_audio.py --datos C:/datos/riksi-audio

Un canto no se parece a una foto, pero un espectrograma sí. Se convierte cada
ventana de audio en una imagen de tiempo por frecuencia y encima va el mismo
tipo de red pequeña que reconoce bichos, con sus pesos preentrenados: un patrón
de armónicos en una escala mel se parece más a una textura de lo que uno diría.

**El espectrograma va dentro del modelo, no fuera.** Es la decisión importante
de esta fase. Si se calculara aparte, el navegador tendría que reproducirlo en
JavaScript, y una ventana o un solapamiento distinto no dan error: dan otro
resultado. Metiéndolo en el grafo solo existe una implementación, y viaja dentro
del `.onnx`.

La partición va **por grabación**, no por ventana: dos trozos del mismo audio
son casi el mismo sonido, y repartidos entre entrenamiento y prueba inflarían la
métrica igual que hacían las fotos de la misma observación.
"""

import argparse
import json
import random
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import soundfile as sf
import timm
import torch
import torch.nn as nn
import torchaudio
from torch.utils.data import DataLoader, Dataset

from entrenar import epoca, evaluar

FRECUENCIA = 32000      # 32 kHz: los cantos de ave viven muy por debajo de 16 kHz
SEGUNDOS = 5


def leer(ruta, frecuencia=FRECUENCIA):
    """Un mp3 a mono, a la frecuencia que espera el modelo."""
    x, fs = sf.read(str(ruta), dtype="float32", always_2d=True)
    x = torch.from_numpy(x.mean(axis=1))            # a mono
    if fs != frecuencia:
        x = torchaudio.functional.resample(x, fs, frecuencia)
    return x


class Cantos(Dataset):
    """Ventanas de cinco segundos sacadas de las grabaciones.

    En entrenamiento la ventana se elige al azar dentro del audio, que es la
    augmentación más barata y más natural aquí: el ave no canta siempre en el
    mismo segundo. En validación se toma siempre la del centro, para que dos
    corridas den lo mismo.
    """

    def __init__(self, ficheros, clases, entrenando):
        self.ficheros = ficheros
        self.clases = clases
        self.entrenando = entrenando
        self.largo = FRECUENCIA * SEGUNDOS

    def __len__(self):
        return len(self.ficheros)

    def __getitem__(self, i):
        ruta, clase = self.ficheros[i]
        try:
            x = leer(ruta)
        except Exception:
            # Un mp3 corrupto no puede tumbar una época entera de entrenamiento.
            x = torch.zeros(self.largo)

        if len(x) < self.largo:
            x = torch.nn.functional.pad(x, (0, self.largo - len(x)))
        elif self.entrenando:
            inicio = random.randint(0, len(x) - self.largo)
            x = x[inicio:inicio + self.largo]
        else:
            inicio = (len(x) - self.largo) // 2
            x = x[inicio:inicio + self.largo]

        maximo = x.abs().max()
        if maximo > 0:
            x = x / maximo               # el volumen de grabación no dice la especie
        return x, clase


class Oido(nn.Module):
    """Audio crudo entra, especie sale. El espectrograma vive aquí dentro."""

    def __init__(self, arquitectura, n_clases, n_mels=128):
        super().__init__()
        self.mel = torchaudio.transforms.MelSpectrogram(
            sample_rate=FRECUENCIA, n_fft=1024, hop_length=320,
            n_mels=n_mels, f_min=50, f_max=14000)
        # in_chans=1: timm adapta los pesos de ImageNet a un solo canal sumando
        # los tres. Repetir el espectrograma tres veces gastaría el triple para
        # dar exactamente la misma información.
        self.cnn = timm.create_model(arquitectura, pretrained=True,
                                     num_classes=n_clases, in_chans=1)

    def forward(self, x):
        z = torch.log(self.mel(x) + 1e-6)
        # Normalizar cada ventana con su propia media evita depender de
        # estadísticas globales que habría que llevar al navegador aparte.
        z = (z - z.mean(dim=(1, 2), keepdim=True)) / (z.std(dim=(1, 2), keepdim=True) + 1e-5)
        return self.cnn(z.unsqueeze(1))


def partir_por_grabacion(ficheros, fraccion_val=0.2, semilla=0):
    """Ningún trozo de una grabación puede caer a los dos lados."""
    porclase = defaultdict(list)
    for i, (_, clase) in enumerate(ficheros):
        porclase[clase].append(i)

    rng = random.Random(semilla)
    entreno, val = [], []
    for clase, indices in porclase.items():
        rng.shuffle(indices)
        corte = max(1, int(len(indices) * fraccion_val))
        val += indices[:corte]
        entreno += indices[corte:]
    return entreno, val


def catalogar(raiz, minimo):
    """Lista de (ruta, clase) y los nombres de las clases que llegan al mínimo."""
    carpetas = sorted(d for d in (raiz / "audio").iterdir() if d.is_dir())
    clases, ficheros = [], []
    for carpeta in carpetas:
        mp3 = sorted(carpeta.glob("*.mp3"))
        if len(mp3) < minimo:
            continue
        clase = len(clases)
        clases.append(carpeta.name)
        ficheros += [(m, clase) for m in mp3]
    return ficheros, clases


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--datos", default="C:/datos/riksi-audio")
    p.add_argument("--modelo", default="efficientnet_lite0")
    p.add_argument("--lote", type=int, default=32)
    p.add_argument("--epocas-cabeza", type=int, default=2)
    p.add_argument("--epocas-todo", type=int, default=12)
    p.add_argument("--minimo", type=int, default=30, help="grabaciones mínimas por especie")
    p.add_argument("--salida", default="modelo-audio")
    args = p.parse_args()

    disp = "cuda" if torch.cuda.is_available() else "cpu"
    ficheros, clases = catalogar(Path(args.datos), args.minimo)
    if not clases:
        sys.exit(f"No hay ninguna especie con {args.minimo} grabaciones en {args.datos}")

    idx_tr, idx_va = partir_por_grabacion(ficheros)
    tr = torch.utils.data.Subset(Cantos(ficheros, clases, True), idx_tr)
    va = torch.utils.data.Subset(Cantos(ficheros, clases, False), idx_va)

    print(f"{len(clases)} especies · {len(idx_tr):,} grabaciones de entreno / "
          f"{len(idx_va):,} de validación · ventanas de {SEGUNDOS} s a {FRECUENCIA // 1000} kHz")
    print(f"dispositivo: {disp}\n")

    # Menos workers que con fotos: descomprimir un mp3 cuesta bastante más que
    # abrir un jpeg, y cada uno se come su hilo entero.
    comun = dict(batch_size=args.lote, num_workers=6, pin_memory=True, persistent_workers=True)
    c_tr = DataLoader(tr, shuffle=True, drop_last=True, **comun)
    c_va = DataLoader(va, shuffle=False, **comun)

    modelo = Oido(args.modelo, len(clases)).to(disp)
    perdida_fn = nn.CrossEntropyLoss(label_smoothing=0.1)
    escala = torch.amp.GradScaler(disp)

    for nombre, param in modelo.named_parameters():
        param.requires_grad = "classifier" in nombre or "head" in nombre
    opt = torch.optim.AdamW([q for q in modelo.parameters() if q.requires_grad], lr=1e-3)
    for e in range(args.epocas_cabeza):
        t = time.time()
        perdida = epoca(modelo, c_tr, opt, escala, perdida_fn, disp)
        a1, a3 = evaluar(modelo, c_va, disp)
        print(f"cabeza {e+1}/{args.epocas_cabeza}  pérdida {perdida:.3f}  "
              f"top1 {a1:.1%}  top3 {a3:.1%}  ({time.time()-t:.0f}s)")

    for param in modelo.parameters():
        param.requires_grad = True
    opt = torch.optim.AdamW(modelo.parameters(), lr=1e-4, weight_decay=0.01)
    plan = torch.optim.lr_scheduler.CosineAnnealingLR(opt, args.epocas_todo)

    mejor = 0.0
    salida = Path(args.salida); salida.mkdir(exist_ok=True)
    for e in range(args.epocas_todo):
        t = time.time()
        perdida = epoca(modelo, c_tr, opt, escala, perdida_fn, disp)
        a1, a3 = evaluar(modelo, c_va, disp)
        plan.step()
        marca = ""
        if a1 > mejor:
            mejor = a1
            torch.save({"modelo": modelo.state_dict(), "clases": clases,
                        "arquitectura": args.modelo, "frecuencia": FRECUENCIA,
                        "segundos": SEGUNDOS}, salida / "riksi-audio.pt")
            marca = "  <-- mejor"
        print(f"todo   {e+1}/{args.epocas_todo}  pérdida {perdida:.3f}  "
              f"top1 {a1:.1%}  top3 {a3:.1%}  ({time.time()-t:.0f}s){marca}")

    (salida / "clases.json").write_text(json.dumps(clases, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nmejor top1: {mejor:.1%} · guardado en {salida/'riksi-audio.pt'}")


def prueba():
    """Que la partición no filtre grabaciones y que el modelo trague audio."""
    ficheros = [(Path(f"C:/x/especie{c}/XC{n}.mp3"), c) for c in range(3) for n in range(10)]
    tr, va = partir_por_grabacion(ficheros, 0.2, semilla=1)
    assert len(tr) + len(va) == 30, (len(tr), len(va))
    assert set(tr).isdisjoint(va), "una grabación cayó en los dos lados"
    assert {ficheros[i][1] for i in va} == {0, 1, 2}, "alguna clase se quedó sin validación"

    m = Oido("efficientnet_lite0", 5).eval()
    with torch.no_grad():
        y = m(torch.randn(2, FRECUENCIA * SEGUNDOS))
    assert y.shape == (2, 5), y.shape

    corta = Cantos([(Path("no-existe.mp3"), 0)], ["x"], False)
    x, c = corta[0]
    assert len(x) == FRECUENCIA * SEGUNDOS, "un fichero ilegible debe dar silencio, no reventar"
    print(f"ok · {len(tr)} entreno / {len(va)} val · sin fugas · el modelo traga audio crudo")


if __name__ == "__main__":
    if "--prueba" in sys.argv:
        prueba()
    else:
        main()
