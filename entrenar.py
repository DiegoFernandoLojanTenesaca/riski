"""Fase 2: entrena el clasificador de Riksi.

    python entrenar.py --datos C:/datos/riksi

Dos pasos, el barato primero: primero solo la cabeza con el backbone congelado
—unos minutos, y ya dice si los datos están bien—, después el fine-tuning
completo. Si el primer paso da un desastre, no hace falta gastar el segundo.

La partición train/val va **por observación**, no por foto: iNaturalist suele
tener varias fotos del mismo animal en el mismo sitio, y si caen a ambos lados
el modelo las reconoce de memoria y la métrica sale inflada.
"""

import argparse
import json
import random
import sys
import time
from collections import defaultdict
from pathlib import Path

import timm
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Subset
from torchvision import transforms
from torchvision.datasets import ImageFolder

MEDIA = (0.485, 0.456, 0.406)
DESV = (0.229, 0.224, 0.225)


def transformaciones(tam=224):
    entreno = transforms.Compose([
        transforms.RandomResizedCrop(tam, scale=(0.6, 1.0)),
        transforms.RandomHorizontalFlip(),
        transforms.ColorJitter(0.2, 0.2, 0.2),
        transforms.ToTensor(),
        transforms.Normalize(MEDIA, DESV),
    ])
    prueba = transforms.Compose([
        # 256 exacto, no `tam * 1.14` (que daba 255): la web replica este número
        # desde preprocesado.json y un desajuste ahí no da error, solo precisión.
        transforms.Resize(tam * 256 // 224),
        transforms.CenterCrop(tam),
        transforms.ToTensor(),
        transforms.Normalize(MEDIA, DESV),
    ])
    return entreno, prueba


def filtrar_clases(dataset, minimo):
    """Quita las especies con menos de `minimo` fotos y renumera el resto.

    El facet de GBIF promete muchas más fotos de las que quedan tras filtrar por
    proveedor: *Dasyprocta punctata* anuncia 2.296 y deja 157, porque casi todas
    sus fotos son de cámara trampa. Algunas especies se quedan en cero. Una clase
    con cuatro ejemplos no se aprende: estorba.
    """
    cuenta = defaultdict(int)
    for _, clase in dataset.samples:
        cuenta[clase] += 1
    validas = sorted(c for c, n in cuenta.items() if n >= minimo)
    nuevo = {viejo: i for i, viejo in enumerate(validas)}

    dataset.samples = [(r, nuevo[c]) for r, c in dataset.samples if c in nuevo]
    dataset.targets = [c for _, c in dataset.samples]
    dataset.imgs = dataset.samples
    dataset.classes = [dataset.classes[c] for c in validas]
    dataset.class_to_idx = {n: i for i, n in enumerate(dataset.classes)}
    return dataset


def observacion_de(ruta):
    """Los archivos se llaman `{observacion}_{n}.jpg` — ver datos.py."""
    return Path(ruta).stem.rsplit("_", 1)[0]


def partir_por_observacion(dataset, fraccion_val=0.2, semilla=0):
    """Índices de train y val sin que una misma observación caiga en ambos."""
    grupos = defaultdict(list)
    for i, (ruta, clase) in enumerate(dataset.samples):
        grupos[(clase, observacion_de(ruta))].append(i)

    porclase = defaultdict(list)
    for (clase, _), indices in grupos.items():
        porclase[clase].append(indices)

    rng = random.Random(semilla)
    entreno, val = [], []
    for clase, observaciones in porclase.items():
        rng.shuffle(observaciones)
        corte = max(1, int(len(observaciones) * fraccion_val))
        for grupo in observaciones[:corte]:
            val += grupo
        for grupo in observaciones[corte:]:
            entreno += grupo
    return entreno, val


def aciertos(salida, y, k=3):
    top = salida.topk(k, dim=1).indices
    top1 = (top[:, 0] == y).sum().item()
    topk = (top == y.unsqueeze(1)).any(dim=1).sum().item()
    return top1, topk


def evaluar(modelo, cargador, disp):
    modelo.eval()
    t1 = t3 = n = 0
    with torch.no_grad(), torch.autocast(disp, dtype=torch.float16):
        for x, y in cargador:
            x, y = x.to(disp, non_blocking=True), y.to(disp, non_blocking=True)
            a, b = aciertos(modelo(x), y)
            t1 += a; t3 += b; n += y.numel()
    return t1 / n, t3 / n


def epoca(modelo, cargador, opt, escala, perdida_fn, disp):
    modelo.train()
    total = n = 0
    for x, y in cargador:
        x, y = x.to(disp, non_blocking=True), y.to(disp, non_blocking=True)
        opt.zero_grad(set_to_none=True)
        with torch.autocast(disp, dtype=torch.float16):
            perdida = perdida_fn(modelo(x), y)
        escala.scale(perdida).backward()
        escala.step(opt)
        escala.update()
        total += perdida.item() * y.numel(); n += y.numel()
    return total / n


def main():
    # La consola de Windows viene en cp1252 y tumba el proceso al imprimir
    # cualquier carácter que no esté en esa tabla. Doce épocas perdidas por una
    # flecha.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--datos", default="C:/datos/riksi")
    # EfficientNet-Lite0 está hecho para cuantizar: sin squeeze-excite y con
    # ReLU6 en vez de hard-swish. Medido, pierde 0 puntos al pasar a int8;
    # MobileNetV3 pierde 7,1 con este mismo dataset.
    p.add_argument("--modelo", default="efficientnet_lite0")
    p.add_argument("--lote", type=int, default=64)
    p.add_argument("--epocas-cabeza", type=int, default=3)
    p.add_argument("--epocas-todo", type=int, default=12)
    p.add_argument("--salida", default="modelo")
    p.add_argument("--minimo", type=int, default=50, help="fotos mínimas para admitir una especie")
    # Subir la resolución no engorda el modelo (los pesos son los mismos), pero
    # multiplica el cómputo en el teléfono: 288 px cuesta un 65% más que 224.
    p.add_argument("--tam", type=int, default=224, help="lado de la imagen de entrada")
    args = p.parse_args()

    disp = "cuda" if torch.cuda.is_available() else "cpu"
    raiz = Path(args.datos) / "imagenes"
    t_entreno, t_prueba = transformaciones(args.tam)

    # allow_empty: 15 especies se quedaron sin ninguna foto de campo, y sin esto
    # ImageFolder revienta en el constructor antes de que filtrar_clases actúe.
    carpeta = lambda t=None: ImageFolder(raiz, t, allow_empty=True)

    base = filtrar_clases(carpeta(), args.minimo)
    idx_tr, idx_va = partir_por_observacion(base)
    tr = Subset(filtrar_clases(carpeta(t_entreno), args.minimo), idx_tr)
    va = Subset(filtrar_clases(carpeta(t_prueba), args.minimo), idx_va)

    descartadas = len(carpeta().classes) - len(base.classes)
    print(f"{len(base.classes)} especies ({descartadas} descartadas por tener menos "
          f"de {args.minimo} fotos) · {len(idx_tr):,} entreno / {len(idx_va):,} validación")
    print(f"dispositivo: {disp}\n")

    comun = dict(batch_size=args.lote, num_workers=8, pin_memory=True, persistent_workers=True)
    c_tr = DataLoader(tr, shuffle=True, drop_last=True, **comun)
    c_va = DataLoader(va, shuffle=False, **comun)

    modelo = timm.create_model(args.modelo, pretrained=True, num_classes=len(base.classes)).to(disp)
    perdida_fn = nn.CrossEntropyLoss(label_smoothing=0.1)
    escala = torch.amp.GradScaler(disp)

    # Paso 1: solo la cabeza. Barato, y delata datos mal armados enseguida.
    for nombre, param in modelo.named_parameters():
        param.requires_grad = "classifier" in nombre or "head" in nombre
    opt = torch.optim.AdamW([q for q in modelo.parameters() if q.requires_grad], lr=1e-3)
    for e in range(args.epocas_cabeza):
        t = time.time()
        perdida = epoca(modelo, c_tr, opt, escala, perdida_fn, disp)
        a1, a3 = evaluar(modelo, c_va, disp)
        print(f"cabeza {e+1}/{args.epocas_cabeza}  pérdida {perdida:.3f}  "
              f"top1 {a1:.1%}  top3 {a3:.1%}  ({time.time()-t:.0f}s)")

    # Paso 2: todo, con paso más corto.
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
            torch.save({"modelo": modelo.state_dict(), "clases": base.classes,
                        "arquitectura": args.modelo, "tam": args.tam}, salida / "riksi.pt")
            marca = "  <-- mejor"
        print(f"todo   {e+1}/{args.epocas_todo}  pérdida {perdida:.3f}  "
              f"top1 {a1:.1%}  top3 {a3:.1%}  ({time.time()-t:.0f}s){marca}")

    (salida / "clases.json").write_text(json.dumps(base.classes, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nmejor top1: {mejor:.1%} · guardado en {salida/'riksi.pt'}")


def prueba():
    """Lo único con lógica propia aquí es la partición: que no se filtre nada."""
    class Falso:
        samples = [(f"C:/x/especie{c}/{obs}_{n}.jpg", c)
                   for c in range(3) for obs in range(10) for n in range(4)]

    tr, va = partir_por_observacion(Falso(), 0.2, semilla=1)
    assert len(tr) + len(va) == 120, (len(tr), len(va))
    assert set(tr).isdisjoint(va), "índices repetidos"

    obs = lambda idx: {(Falso.samples[i][1], observacion_de(Falso.samples[i][0])) for i in idx}
    assert obs(tr).isdisjoint(obs(va)), "una observación cayó en train y en val"

    clases_va = {Falso.samples[i][1] for i in va}
    assert clases_va == {0, 1, 2}, f"alguna clase se quedó sin validación: {clases_va}"

    assert observacion_de("C:/x/y/6273265358_10.jpg") == "6273265358"

    class Pocas:
        classes = ["mucha", "poca", "vacia"]
        samples = [(f"C:/x/mucha/{i}_0.jpg", 0) for i in range(60)] + [("C:/x/poca/1_0.jpg", 1)]
    d = filtrar_clases(Pocas(), 50)
    assert d.classes == ["mucha"], d.classes
    assert {c for _, c in d.samples} == {0}, "las clases no se renumeraron"
    assert len(d.samples) == 60, len(d.samples)

    print(f"ok · {len(tr)} entreno / {len(va)} val · sin fugas · filtro de clases correcto")


if __name__ == "__main__":

    if "--prueba" in sys.argv:
        prueba()
    else:
        main()
