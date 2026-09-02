"""Los experimentos de Riksi, en MLflow.

**No reentrena nada.** Las nueve configuraciones ya se corrieron y cada una dejó
su `metricas.json`; lo que faltaba era poder compararlas sin abrir nueve ficheros
a mano. Eso es lo que hace este módulo: leerlas y registrarlas.

Registrar a posteriori tiene una ventaja que no se ve al principio: obliga a
mirar qué se guardó de verdad de cada corrida, y ahí se descubre lo que no se
apuntó. Los `metricas.json` de foto no llevan el número de épocas ni el tamaño
del lote, así que dos corridas de la misma arquitectura no se pueden distinguir
por sus hiperparámetros. Se registra lo que hay y se dice lo que falta, en vez de
inventar los valores.

    python experimentos.py            # registra las nueve corridas
    python experimentos.py --ver      # abre la interfaz en el navegador
    python experimentos.py --comprobar
"""

import argparse
import json
import pathlib
import sys

AQUI = pathlib.Path(__file__).parent

# **SQLite y no una carpeta de ficheros.** MLflow 3 dejó el backend de ficheros
# en mantenimiento y aborta con un error explícito si se usa; SQLite es lo que
# recomienda y además permite consultar las corridas con SQL, que es justo lo
# que hace falta para comparar nueve configuraciones.
ALMACEN = AQUI / "mlflow.db"
URI = f"sqlite:///{ALMACEN.as_posix()}"


def corridas():
    """Cada carpeta `modelo*` con métricas, leída tal cual quedó."""
    for carpeta in sorted(AQUI.glob("modelo*/metricas.json")):
        yield carpeta.parent.name, json.loads(carpeta.read_text(encoding="utf-8"))


def _aplanar(m):
    """De las métricas anidadas a lo que MLflow entiende.

    El fichero agrupa por precisión —`pytorch`, `fp32`, `int8`— y MLflow quiere
    nombres planos. `int8.top1` se lee bien y se ordena solo en la tabla.
    """
    parametros, medidas = {}, {}
    for clave, valor in m.items():
        if isinstance(valor, dict):
            for sub, v in valor.items():
                if isinstance(v, (int, float)):
                    medidas[f"{clave}.{sub}"] = float(v)
        elif isinstance(valor, (int, float)) and not isinstance(valor, bool):
            medidas[clave] = float(valor)
        else:
            parametros[clave] = valor
    return parametros, medidas


def registrar():
    """Mete las nueve corridas en MLflow, cada una con sus parámetros."""
    import mlflow

    mlflow.set_tracking_uri(URI)
    n = 0
    for nombre, m in corridas():
        # Foto y audio son dos problemas distintos y comparar sus aciertos no
        # significa nada: 79,8 % sobre cien especies en foto y 52,2 % sobre
        # setenta y cuatro aves por su canto no están en la misma escala.
        tipo = "audio" if "audio" in nombre else "foto"
        mlflow.set_experiment(f"riksi-{tipo}")

        parametros, medidas = _aplanar(m)
        with mlflow.start_run(run_name=nombre):
            mlflow.log_params(parametros)
            mlflow.log_metrics(medidas)

            # Lo que NO se apuntó en su día. Marcarlo es más útil que dejarlo en
            # blanco: quien mire la tabla sabe que la comparación entre dos
            # corridas de la misma arquitectura no es concluyente.
            faltan = [c for c in ("epocas", "lote", "aprendizaje")
                      if c not in parametros]
            if faltan:
                mlflow.set_tag("sin_registrar", ", ".join(faltan))

            mlflow.set_tag("publicado", "si" if nombre in ("modelo", "modelo-audio")
                           else "no")
            fichero = AQUI / nombre / "metricas.json"
            mlflow.log_artifact(str(fichero))
        n += 1
        print(f"  {nombre:28} {len(medidas)} medidas · {len(parametros)} parámetros")
    return n


def comparar():
    """La tabla que justifica el modelo publicado, sacada de MLflow."""
    import mlflow

    mlflow.set_tracking_uri(URI)
    for tipo in ("foto", "audio"):
        exp = mlflow.get_experiment_by_name(f"riksi-{tipo}")
        if not exp:
            continue
        df = mlflow.search_runs(experiment_ids=[exp.experiment_id])
        if df.empty:
            continue

        col = "metrics.int8.top1"
        if col not in df:
            continue
        print(f"\n=== riksi-{tipo} ===")
        print(f"  {'corrida':28}{'int8 top1':>11}{'MB':>8}{'coste':>9}")
        for _, f in df.sort_values(col, ascending=False).iterrows():
            mb = f.get("metrics.int8.mb")
            coste = f.get("metrics.coste_top1")
            print(f"  {f['tags.mlflow.runName']:28}{f[col]:>10.1%}"
                  f"{mb if mb is not None else 0:>8.1f}"
                  f"{coste if coste is not None else 0:>9.3f}")


def prueba():
    """Que las nueve corridas se lean y que aplanar no pierda nada."""
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    todas = list(corridas())
    assert len(todas) >= 9, f"solo {len(todas)} corridas; esperaba 9"

    nombres = {n for n, _ in todas}
    assert "modelo-lite0-288" in nombres, nombres
    assert any("audio" in n for n in nombres), "faltan las corridas de audio"

    # El aplanado: lo numérico va a medidas y lo demás a parámetros. Si la
    # arquitectura acabara en medidas, MLflow la rechazaría por no ser un
    # número y la corrida se perdería entera.
    _, m = next((n, m) for n, m in todas if n == "modelo-lite0-288")
    p, med = _aplanar(m)
    assert p["arquitectura"] == "efficientnet_lite0", p
    assert "int8.top1" in med and 0 < med["int8.top1"] <= 1, med
    assert "clases" in med and med["clases"] == 100, med
    assert all(isinstance(v, float) for v in med.values()), \
        "una medida no numérica haría fallar el registro entero"

    print(f"ok · {len(todas)} corridas · {len(med)} medidas y {len(p)} parámetros "
          f"en modelo-lite0-288 · foto y audio separados")


def main():
    a = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    a.add_argument("--ver", action="store_true", help="abre la interfaz de MLflow")
    a.add_argument("--comprobar", action="store_true")
    args = a.parse_args()

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if args.comprobar:
        return prueba()
    if args.ver:
        import subprocess
        print(f"MLflow en http://127.0.0.1:5000 · Ctrl+C para parar")
        return subprocess.run([sys.executable, "-m", "mlflow", "ui",
                               "--backend-store-uri", URI])
    n = registrar()
    print(f"\n{n} corridas registradas en {ALMACEN.name}/")
    comparar()


if __name__ == "__main__":
    main()
