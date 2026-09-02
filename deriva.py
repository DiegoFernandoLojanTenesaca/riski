"""Cuánto se aleja el modelo en el campo de lo que prometió en validación.

**Las métricas de validación miden un mundo que no existe.** Las 1.000 imágenes
de validación salen del mismo reparto que las de entrenamiento: mismas fuentes,
mismos fotógrafos, mismo sesgo de encuadre. El 79,8 % que sale ahí es real, pero
responde a una pregunta más estrecha de la que uno cree.

El radar mide la otra: fotos que se subieron después, de gente distinta, sin que
nadie las eligiera. Comparar las dos es lo que en producción se llama detectar
deriva, y aquí sale gratis porque las dos mitades ya existen.

**Lo que se compara no son dos números, son dos preguntas distintas.** Una caída
puede significar que el entrenamiento no se parecía al mundo, o que en el campo
llegan fotos más difíciles —el ave lejos, a contraluz, entre ramas—, o
simplemente que hay tres observaciones y el porcentaje no significa nada. Este
módulo no decide cuál: separa lo que tiene muestra suficiente de lo que no, y
marca la diferencia.

    python deriva.py             # la tabla
    python deriva.py --comprobar
"""

import argparse
import json
import pathlib
import sys

AQUI = pathlib.Path(__file__).parent
BANCO = AQUI / "docs" / "banco" / "banco.json"
RADAR = pathlib.Path(r"D:\CLAUDE PROYECTOS\riksi-radar\datos\radar.duckdb")

# Por debajo de esto el porcentaje es anécdota, no medida: con dos
# observaciones se pasa de 0 % a 50 % por una foto. Se siguen mostrando, pero
# aparte, para que nadie saque conclusiones de ellas.
#
# **El banco no da para exigir más.** Reparte 200 imágenes entre 86 especies,
# con un máximo de 6 cada una: se hizo para que la web enseñe ejemplos, no para
# medir especie a especie. Las 1.000 de validación de verdad se quedaron en el
# reparto del entrenamiento, que no está en este disco.
#
# Así que la comparación por especie se lee con reservas y el número que sí
# aguanta es el global, donde las 200 imágenes cuentan juntas.
MINIMO = 3

# A partir de cuántos puntos una diferencia deja de ser ruido. Con muestras de
# decenas, diez puntos entran de sobra en el margen de azar.
AVISO = 20


def validacion():
    """Acierto por especie sobre el banco: imágenes que el modelo no vio."""
    datos = json.loads(BANCO.read_text(encoding="utf-8"))
    imagenes = dict(datos)["imagenes"] if not isinstance(datos, list) else datos

    por_especie = {}
    for i in imagenes:
        verdad = i["verdadera"].replace("_", " ")
        acierta = i.get("python", "").replace("_", " ") == verdad
        n, ok = por_especie.get(verdad, (0, 0))
        por_especie[verdad] = (n + 1, ok + acierta)
    return por_especie


def campo():
    """Acierto por especie sobre lo que el radar ha clasificado."""
    import duckdb

    if not RADAR.exists():
        raise SystemExit(f"No hay almacén del radar en {RADAR}. "
                         f"Córrelo antes: python flujo.py")
    cx = duckdb.connect(str(RADAR), read_only=True)
    filas = cx.execute("""
        select especie, observaciones, aciertos
        from por_especie
    """).fetchall()
    cx.close()
    return {f[0]: (f[1], f[2]) for f in filas}


def comparar():
    """Las dos mitades, especie a especie."""
    val, cam = validacion(), campo()
    comunes = sorted(set(val) & set(cam))

    filas = []
    for esp in comunes:
        nv, okv = val[esp]
        nc, okc = cam[esp]
        pv, pc = 100 * okv / nv, 100 * okc / nc
        filas.append({
            "especie": esp,
            "validacion_n": nv, "validacion_pct": pv,
            "campo_n": nc, "campo_pct": pc,
            "diferencia": pc - pv,
            "medible": nv >= MINIMO and nc >= MINIMO,
        })
    return sorted(filas, key=lambda f: f["diferencia"])


def global_():
    """El acierto agregado a cada lado, que es el número que sí aguanta.

    Por especie el banco no da: seis imágenes como máximo. Sumadas, las 200
    tienen el peso suficiente para comparar contra las clasificadas del radar.
    """
    val, cam = validacion(), campo()
    nv = sum(n for n, _ in val.values())
    okv = sum(ok for _, ok in val.values())
    nc = sum(n for n, _ in cam.values())
    okc = sum(ok for _, ok in cam.values())
    return {"validacion_n": nv, "validacion_pct": 100 * okv / max(nv, 1),
            "campo_n": nc, "campo_pct": 100 * okc / max(nc, 1)}


def informe():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    g = global_()
    print("=== el modelo, a los dos lados ===\n")
    print(f"  {'banco de validación':<26}{g['validacion_pct']:>6.1f}%   "
          f"({g['validacion_n']} imágenes que el modelo no vio al entrenar)")
    print(f"  {'campo, vía el radar':<26}{g['campo_pct']:>6.1f}%   "
          f"({g['campo_n']} observaciones subidas por otros)")
    dif = g["campo_pct"] - g["validacion_pct"]
    print(f"  {'diferencia':<26}{dif:>+6.1f}")
    print()
    if abs(dif) < 5:
        print("  El modelo se comporta en el campo como prometió: la diferencia")
        print("  cabe en el margen de dos muestras de este tamaño.")
    elif dif < 0:
        print(f"  Cae {abs(dif):.0f} puntos fuera del reparto de entrenamiento.")
        print("  Eso es deriva: el mundo trae fotos que el entrenamiento no tenía.")
    else:
        print(f"  Sube {dif:.0f} puntos en el campo, lo que suele significar que")
        print("  llegan especies fáciles y muy fotografiadas, no que el modelo")
        print("  haya mejorado.")
    print()

    filas = comparar()
    if not filas:
        print("Ninguna especie tiene datos en los dos sitios todavía. "
              "El radar necesita clasificar más.")
        return

    medibles = [f for f in filas if f["medible"]]
    pocas = [f for f in filas if not f["medible"]]

    print(f"=== por especie ===\n")
    print(f"  {len(filas)} con datos en los dos sitios · {len(medibles)} con "
          f"al menos {MINIMO} a cada lado\n")

    if medibles:
        print(f"  {'especie':<28}{'validación':>12}{'campo':>12}{'dif':>8}")
        for f in medibles:
            marca = "  ← mirar" if f["diferencia"] <= -AVISO else ""
            print(f"  {f['especie']:<28}"
                  f"{f['validacion_pct']:>10.0f}% ({f['validacion_n']:>2})"
                  f"{f['campo_pct']:>7.0f}% ({f['campo_n']:>2})"
                  f"{f['diferencia']:>+7.0f}{marca}")

        media = sum(f["diferencia"] for f in medibles) / len(medibles)
        print(f"\n  diferencia media: {media:+.1f} puntos")
        caidas = [f for f in medibles if f["diferencia"] <= -AVISO]
        if caidas:
            print(f"  {len(caidas)} especie(s) caen más de {AVISO} puntos en el campo")
        else:
            print(f"  ninguna cae más de {AVISO} puntos: el modelo se comporta "
                  f"en el campo como prometió")

    if pocas:
        print(f"\n  {len(pocas)} especie(s) con muestra corta, aparte porque su "
              f"porcentaje no significa nada todavía:")
        print("   ", ", ".join(f"{f['especie']} ({f['validacion_n']}/{f['campo_n']})"
                               for f in pocas[:6]))


def prueba():
    """Que las dos mitades se lean y que la comparación no mienta."""
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    val = validacion()
    assert len(val) >= 20, f"solo {len(val)} especies en el banco"
    assert all(n > 0 for n, _ in val.values()), "una especie con cero imágenes"
    assert all(ok <= n for n, ok in val.values()), \
        "más aciertos que imágenes: el conteo está mal"

    filas = comparar()
    for f in filas:
        # La diferencia tiene que ser exactamente campo menos validación. Si se
        # invirtiera el signo, una caída se leería como una mejora.
        esperada = f["campo_pct"] - f["validacion_pct"]
        assert abs(f["diferencia"] - esperada) < 1e-9, f
        assert 0 <= f["validacion_pct"] <= 100 and 0 <= f["campo_pct"] <= 100, f

    # Y `medible` tiene que exigir muestra en LOS DOS lados: con 30 imágenes de
    # validación y una sola observación de campo, el porcentaje de campo sigue
    # sin significar nada.
    for f in filas:
        assert f["medible"] == (f["validacion_n"] >= MINIMO and f["campo_n"] >= MINIMO), f

    print(f"ok · {len(val)} especies en validación · {len(filas)} comparables "
          f"· {sum(f['medible'] for f in filas)} con muestra a los dos lados")


def main():
    a = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    a.add_argument("--comprobar", action="store_true")
    args = a.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    prueba() if args.comprobar else informe()


if __name__ == "__main__":
    main()
