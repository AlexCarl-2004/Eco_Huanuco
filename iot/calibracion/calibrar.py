"""
ECO-8 · T-107 — Calibración de sensores ultrasónicos y validación de criterios.

Lee las mediciones tomadas en campo (distancia real con wincha vs. distancia reportada
por el sensor), calcula por cada dispositivo la recta de corrección por mínimos cuadrados

    distancia_real = factor_escala × distancia_medida + offset_cm

y verifica los criterios de aceptación de PROTOCOLO_CALIBRACION.md.

Genera:
    - un resumen en consola,
    - resultados_calibracion.csv con los coeficientes y el veredicto por sensor,
    - reporte_calibracion.html con gráficos (se abre en cualquier navegador).

Uso:
    python calibrar.py datos_ejemplo.csv
    python calibrar.py mediciones.csv --salida reportes/
    python calibrar.py mediciones.csv --aplicar http://localhost:8000   # guarda los coeficientes de los sensores APROBADOS

Sólo usa la librería estándar de Python (no requiere instalar nada).
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import math
import statistics
import sys
import urllib.error
import urllib.request
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

# ----------------------------------------------------------------- criterios
CRITERIOS = {
    "error_max_cm": 2.0,       # C1 · error absoluto máximo tras la corrección
    "mae_cm": 1.0,             # C2 · error absoluto medio tras la corrección
    "desviacion_cm": 1.0,      # C3 · repetibilidad: desviación estándar en cada punto
    "r2_min": 0.995,           # C4 · linealidad de la respuesta
    "validas_min_pct": 95.0,   # C5 · porcentaje de lecturas con eco válido
    "puntos_min": 4,           # C6 · cobertura: distancias distintas medidas
}
ALTURA_REFERENCIA_CM = 120  # contenedor de 1100 L, para expresar el error en % de nivel


@dataclass
class Medicion:
    real: float
    medida: float | None  # None = sin eco / lectura vacía
    temperatura: float | None = None


@dataclass
class Resultado:
    device_id: str
    n_total: int
    n_validas: int
    factor: float = 1.0
    offset: float = 0.0
    r2: float = 0.0
    mae_antes: float = 0.0
    mae_despues: float = 0.0
    error_max_antes: float = 0.0
    error_max_despues: float = 0.0
    desviacion_max: float = 0.0
    puntos: int = 0
    criterios: dict[str, tuple[bool, str]] = field(default_factory=dict)
    pares: list[tuple[float, float]] = field(default_factory=list)

    @property
    def aprobado(self) -> bool:
        return all(ok for ok, _ in self.criterios.values())

    @property
    def validas_pct(self) -> float:
        return self.n_validas / self.n_total * 100 if self.n_total else 0.0


# ----------------------------------------------------------------- lectura
def leer_csv(ruta: Path) -> dict[str, list[Medicion]]:
    datos: dict[str, list[Medicion]] = defaultdict(list)
    with ruta.open(encoding="utf-8-sig", newline="") as f:
        lineas = (linea for linea in f if linea.strip() and not linea.lstrip().startswith("#"))
        lector = csv.DictReader(lineas)
        requeridas = {"device_id", "distancia_real_cm", "distancia_medida_cm"}
        if not requeridas.issubset(lector.fieldnames or []):
            sys.exit(f"El CSV debe tener las columnas: {', '.join(sorted(requeridas))}")
        for n, fila in enumerate(lector, start=2):
            try:
                real = float(fila["distancia_real_cm"].replace(",", "."))
            except ValueError:
                sys.exit(f"Fila {n}: distancia_real_cm no es un número")
            medida_txt = (fila.get("distancia_medida_cm") or "").strip().replace(",", ".")
            medida = float(medida_txt) if medida_txt and float(medida_txt) > 0 else None
            temp_txt = (fila.get("temperatura_c") or "").strip().replace(",", ".")
            datos[fila["device_id"].strip().upper()].append(
                Medicion(real, medida, float(temp_txt) if temp_txt else None)
            )
    return datos


# ----------------------------------------------------------------- cálculo
def regresion(xs: list[float], ys: list[float]) -> tuple[float, float, float]:
    """Mínimos cuadrados y = a·x + b. Devuelve (a, b, R²)."""
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    if sxx == 0:
        return 1.0, my - mx, 0.0
    a = sxy / sxx
    b = my - a * mx
    ss_tot = sum((y - my) ** 2 for y in ys)
    ss_res = sum((y - (a * x + b)) ** 2 for x, y in zip(xs, ys))
    r2 = 1 - ss_res / ss_tot if ss_tot else 1.0
    return a, b, r2


def calibrar(device_id: str, mediciones: list[Medicion]) -> Resultado:
    validas = [m for m in mediciones if m.medida is not None]
    res = Resultado(device_id, len(mediciones), len(validas))
    c = CRITERIOS
    if len(validas) < 2:
        res.criterios["C5 Lecturas válidas"] = (False, f"{res.validas_pct:.0f} % (mín. {c['validas_min_pct']:.0f} %)")
        return res

    xs = [m.medida for m in validas]
    ys = [m.real for m in validas]
    res.factor, res.offset, res.r2 = regresion(xs, ys)
    res.pares = list(zip(ys, xs))

    errores_antes = [abs(x - y) for x, y in zip(xs, ys)]
    errores_despues = [abs(res.factor * x + res.offset - y) for x, y in zip(xs, ys)]
    res.mae_antes = statistics.fmean(errores_antes)
    res.mae_despues = statistics.fmean(errores_despues)
    res.error_max_antes = max(errores_antes)
    res.error_max_despues = max(errores_despues)

    por_punto: dict[float, list[float]] = defaultdict(list)
    for m in validas:
        por_punto[m.real].append(m.medida)
    res.puntos = len(por_punto)
    res.desviacion_max = max((statistics.stdev(v) for v in por_punto.values() if len(v) > 1), default=0.0)

    res.criterios = {
        "C1 Error máximo": (res.error_max_despues <= c["error_max_cm"], f"{res.error_max_despues:.2f} cm (máx. {c['error_max_cm']} cm)"),
        "C2 Error medio": (res.mae_despues <= c["mae_cm"], f"{res.mae_despues:.2f} cm (máx. {c['mae_cm']} cm)"),
        "C3 Repetibilidad": (res.desviacion_max <= c["desviacion_cm"], f"σ = {res.desviacion_max:.2f} cm (máx. {c['desviacion_cm']} cm)"),
        "C4 Linealidad": (res.r2 >= c["r2_min"], f"R² = {res.r2:.4f} (mín. {c['r2_min']})"),
        "C5 Lecturas válidas": (res.validas_pct >= c["validas_min_pct"], f"{res.validas_pct:.0f} % (mín. {c['validas_min_pct']:.0f} %)"),
        "C6 Cobertura": (res.puntos >= c["puntos_min"], f"{res.puntos} distancias (mín. {c['puntos_min']})"),
        "Rango del factor": (0.5 <= res.factor <= 1.5, f"{res.factor:.4f} (0,5 – 1,5)"),
    }
    return res


# ----------------------------------------------------------------- salidas
def imprimir(resultados: list[Resultado]) -> None:
    print("\n♻  EcoHuánuco · Calibración de sensores ultrasónicos\n")
    cab = f"{'Dispositivo':<13}{'Factor':>9}{'Offset':>9}{'R²':>9}{'MAE antes':>11}{'MAE desp.':>11}{'Máx. desp.':>12}{'Válidas':>9}   Resultado"
    print(cab)
    print("─" * len(cab) + "─" * 10)
    for r in resultados:
        estado = "✔ APROBADO" if r.aprobado else "✘ RECHAZADO"
        print(f"{r.device_id:<13}{r.factor:>9.4f}{r.offset:>+9.2f}{r.r2:>9.4f}{r.mae_antes:>9.2f}cm{r.mae_despues:>9.2f}cm"
              f"{r.error_max_despues:>10.2f}cm{r.validas_pct:>8.0f}%   {estado}")
        for nombre, (ok, detalle) in r.criterios.items():
            if not ok:
                print(f"{'':13}  └─ no cumple {nombre}: {detalle}")
    aprobados = sum(r.aprobado for r in resultados)
    print(f"\n{aprobados} de {len(resultados)} sensores aprobados.\n")


def guardar_csv(resultados: list[Resultado], ruta: Path) -> None:
    with ruta.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["device_id", "factor_escala", "offset_cm", "r2", "mae_antes_cm", "mae_despues_cm",
                    "error_max_despues_cm", "desviacion_max_cm", "lecturas_validas_pct", "aprobado", "observaciones"])
        for r in resultados:
            fallas = "; ".join(f"{k}: {d}" for k, (ok, d) in r.criterios.items() if not ok)
            w.writerow([r.device_id, f"{r.factor:.5f}", f"{r.offset:.3f}", f"{r.r2:.5f}", f"{r.mae_antes:.3f}",
                        f"{r.mae_despues:.3f}", f"{r.error_max_despues:.3f}", f"{r.desviacion_max:.3f}",
                        f"{r.validas_pct:.1f}", "si" if r.aprobado else "no", fallas])


def svg_dispersion(r: Resultado, ancho=420, alto=300) -> str:
    """Gráfico real (eje X) vs. medido (eje Y), con la recta ideal y la recta del sensor."""
    if not r.pares:
        return '<p class="muted">Sin datos suficientes para graficar.</p>'
    m = 40
    vals = [v for p in r.pares for v in p]
    lo, hi = math.floor(min(vals) / 10) * 10, math.ceil(max(vals) / 10) * 10
    esc = lambda v, tam: (v - lo) / (hi - lo) * (tam - 2 * m)  # noqa: E731
    px = lambda v: m + esc(v, ancho)  # noqa: E731
    py = lambda v: alto - m - esc(v, alto)  # noqa: E731
    clip = f"area-{r.device_id}"
    partes = [
        f'<svg viewBox="0 0 {ancho} {alto}" role="img" aria-label="Distancia real contra distancia medida">',
        f'<defs><clipPath id="{clip}"><rect x="{m}" y="{m}" width="{ancho - 2 * m}" height="{alto - 2 * m}"/></clipPath></defs>',
    ]
    for t in range(int(lo), int(hi) + 1, 20):
        partes.append(f'<line x1="{px(t):.1f}" y1="{m}" x2="{px(t):.1f}" y2="{alto - m}" class="grid"/>')
        partes.append(f'<line x1="{m}" y1="{py(t):.1f}" x2="{ancho - m}" y2="{py(t):.1f}" class="grid"/>')
        partes.append(f'<text x="{px(t):.1f}" y="{alto - m + 16}" class="tick" text-anchor="middle">{t}</text>')
        partes.append(f'<text x="{m - 6}" y="{py(t) + 4:.1f}" class="tick" text-anchor="end">{t}</text>')
    partes.append(f'<g clip-path="url(#{clip})">')
    partes.append(f'<line x1="{px(lo):.1f}" y1="{py(lo):.1f}" x2="{px(hi):.1f}" y2="{py(hi):.1f}" class="ideal"/>')
    # medida = (real - offset) / factor  → recta del sensor sin corregir
    y1, y2 = (lo - r.offset) / r.factor, (hi - r.offset) / r.factor
    partes.append(f'<line x1="{px(lo):.1f}" y1="{py(y1):.1f}" x2="{px(hi):.1f}" y2="{py(y2):.1f}" class="ajuste"/>')
    for real, medida in r.pares:
        partes.append(f'<circle cx="{px(real):.1f}" cy="{py(medida):.1f}" r="3.2" class="punto"><title>real {real} cm · medido {medida} cm</title></circle>')
    partes.append("</g>")
    partes.append(f'<text x="{ancho / 2}" y="{alto - 6}" class="eje" text-anchor="middle">Distancia real (cm)</text>')
    partes.append(f'<text x="12" y="{alto / 2}" class="eje" text-anchor="middle" transform="rotate(-90 12 {alto / 2})">Distancia medida (cm)</text>')
    partes.append("</svg>")
    return "".join(partes)


def guardar_html(resultados: list[Resultado], ruta: Path, origen: str) -> None:
    aprobados = sum(r.aprobado for r in resultados)
    tarjetas = []
    for r in resultados:
        filas = "".join(
            f'<tr><td>{html.escape(n)}</td><td>{html.escape(d)}</td><td class="{"ok" if ok else "ko"}">{"Cumple" if ok else "No cumple"}</td></tr>'
            for n, (ok, d) in r.criterios.items()
        )
        mejora = (1 - r.mae_despues / r.mae_antes) * 100 if r.mae_antes else 0
        tarjetas.append(f"""
        <article class="card">
          <header>
            <div><h2>{html.escape(r.device_id)}</h2>
            <p class="muted">{r.n_validas} de {r.n_total} lecturas válidas · {r.puntos} distancias</p></div>
            <span class="badge {'ok' if r.aprobado else 'ko'}">{'Aprobado' if r.aprobado else 'Rechazado'}</span>
          </header>
          <div class="grid2">
            <figure>{svg_dispersion(r)}
              <figcaption><i class="sw ideal"></i>Ideal (medido = real) <i class="sw ajuste"></i>Respuesta del sensor</figcaption>
            </figure>
            <div>
              <dl class="kpis">
                <div><dt>Factor de escala</dt><dd>{r.factor:.4f}</dd></div>
                <div><dt>Offset</dt><dd>{r.offset:+.2f} cm</dd></div>
                <div><dt>Error medio</dt><dd>{r.mae_antes:.2f} → <b>{r.mae_despues:.2f}</b> cm</dd></div>
                <div><dt>Mejora por calibración</dt><dd class="up">{mejora:.0f} %</dd></div>
                <div><dt>Error de nivel equivalente</dt><dd>± {r.error_max_despues / ALTURA_REFERENCIA_CM * 100:.1f} %</dd></div>
              </dl>
              <table><thead><tr><th>Criterio</th><th>Resultado</th><th></th></tr></thead><tbody>{filas}</tbody></table>
            </div>
          </div>
        </article>""")

    documento = f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Reporte de calibración · EcoHuánuco AI</title>
<style>
  :root {{ --bg:#f7f9f8; --card:#fff; --tx:#0f1a16; --mu:#5f6f69; --bd:#e3e9e6; --gr:#10b981; --grk:#047857; --rd:#ef4444; --rdk:#b91c1c; }}
  @media (prefers-color-scheme: dark) {{ :root {{ --bg:#0c1210; --card:#121a17; --tx:#eef4f1; --mu:#8fa19a; --bd:#22302a; --grk:#34d399; --rdk:#f87171; }} }}
  * {{ box-sizing:border-box }}
  body {{ margin:0; font:14px/1.5 Inter,system-ui,-apple-system,Segoe UI,Roboto,sans-serif; background:var(--bg); color:var(--tx); }}
  main {{ max-width:1100px; margin:0 auto; padding:40px 24px 64px; }}
  .eyebrow {{ color:var(--grk); font-size:12px; font-weight:600; letter-spacing:.06em; text-transform:uppercase; margin:0 }}
  h1 {{ font-size:28px; letter-spacing:-.02em; margin:6px 0 4px }}
  .muted {{ color:var(--mu); margin:0 }}
  .resumen {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:12px; margin:28px 0 }}
  .resumen div, .card {{ background:var(--card); border:1px solid var(--bd); border-radius:12px; }}
  .resumen div {{ padding:16px 18px }}
  .resumen dt {{ color:var(--mu); font-size:12.5px }} .resumen dd {{ margin:6px 0 0; font-size:26px; font-weight:650; letter-spacing:-.02em }}
  .card {{ padding:20px 22px; margin-bottom:14px }}
  .card header {{ display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:12px }}
  h2 {{ margin:0; font-size:16px; font-family:ui-monospace,Menlo,monospace }}
  .badge {{ font-size:12px; font-weight:600; padding:3px 10px; border-radius:99px }}
  .badge.ok {{ background:rgba(16,185,129,.14); color:var(--grk) }} .badge.ko {{ background:rgba(239,68,68,.12); color:var(--rdk) }}
  .grid2 {{ display:grid; grid-template-columns:420px 1fr; gap:24px; align-items:start }}
  @media (max-width:860px) {{ .grid2 {{ grid-template-columns:1fr }} }}
  figure {{ margin:0 }} svg {{ width:100%; height:auto }}
  figcaption {{ font-size:12px; color:var(--mu); display:flex; gap:6px; align-items:center; flex-wrap:wrap }}
  .sw {{ display:inline-block; width:14px; height:2px; margin-left:8px }} .sw.ideal {{ background:var(--mu) }} .sw.ajuste {{ background:var(--gr) }}
  .grid {{ stroke:var(--bd); stroke-width:1 }} .tick {{ fill:var(--mu); font-size:10px }} .eje {{ fill:var(--mu); font-size:11px }}
  .ideal {{ stroke:var(--mu); stroke-dasharray:4 4; stroke-width:1.2 }} .ajuste {{ stroke:var(--gr); stroke-width:2 }}
  .punto {{ fill:var(--gr); fill-opacity:.55; stroke:var(--grk); stroke-width:.8 }}
  .kpis {{ display:grid; grid-template-columns:1fr 1fr; gap:10px 18px; margin:0 0 16px }}
  .kpis dt {{ font-size:12px; color:var(--mu) }} .kpis dd {{ margin:2px 0 0; font-weight:600; font-variant-numeric:tabular-nums }}
  .up {{ color:var(--grk) }}
  table {{ width:100%; border-collapse:collapse; font-size:13px }}
  th {{ text-align:left; color:var(--mu); font-weight:600; font-size:12px; padding:6px 8px; border-bottom:1px solid var(--bd) }}
  td {{ padding:6px 8px; border-bottom:1px solid var(--bd); font-variant-numeric:tabular-nums }}
  td.ok {{ color:var(--grk); font-weight:600 }} td.ko {{ color:var(--rdk); font-weight:600 }}
  footer {{ color:var(--mu); font-size:12px; margin-top:28px }}
</style></head>
<body><main>
  <p class="eyebrow">ECO-8 · Pruebas de calibración ultrasónica</p>
  <h1>Reporte de calibración de sensores</h1>
  <p class="muted">Archivo de datos: {html.escape(origen)} · Generado el {datetime.now():%d/%m/%Y %H:%M}</p>
  <dl class="resumen">
    <div><dt>Sensores evaluados</dt><dd>{len(resultados)}</dd></div>
    <div><dt>Aprobados</dt><dd style="color:var(--grk)">{aprobados}</dd></div>
    <div><dt>Rechazados</dt><dd style="color:var(--rdk)">{len(resultados) - aprobados}</dd></div>
    <div><dt>Criterio de exactitud</dt><dd>± {CRITERIOS['error_max_cm']:.0f} cm</dd></div>
  </dl>
  {''.join(tarjetas)}
  <footer>Corrección aplicada por el backend: distancia_corregida = factor_escala × distancia_medida + offset.
  Criterios definidos en iot/calibracion/PROTOCOLO_CALIBRACION.md.</footer>
</main></body></html>"""
    ruta.write_text(documento, encoding="utf-8")


def aplicar(resultados: list[Resultado], base_url: str) -> None:
    for r in resultados:
        if not r.aprobado:
            print(f"  – {r.device_id}: no se aplica (rechazado)")
            continue
        url = f"{base_url.rstrip('/')}/api/dispositivos/{r.device_id}/calibracion/"
        cuerpo = json.dumps({"factor_escala": round(r.factor, 5), "offset_cm": round(r.offset, 3)}).encode()
        peticion = urllib.request.Request(url, data=cuerpo, method="POST", headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(peticion, timeout=10) as resp:
                print(f"  ✔ {r.device_id}: coeficientes guardados (HTTP {resp.status})")
        except urllib.error.HTTPError as exc:
            print(f"  ✘ {r.device_id}: HTTP {exc.code} {exc.read().decode(errors='ignore')[:120]}")
        except urllib.error.URLError as exc:
            sys.exit(f"No se pudo conectar a {base_url}: {exc.reason}")


def main():
    p = argparse.ArgumentParser(description="Calibración de sensores ultrasónicos · EcoHuánuco AI")
    p.add_argument("csv", type=Path, help="Archivo CSV con las mediciones de campo")
    p.add_argument("--salida", type=Path, default=Path("."), help="Carpeta donde guardar los reportes")
    p.add_argument("--aplicar", metavar="URL_BACKEND", help="Envía los coeficientes de los sensores aprobados a la API")
    args = p.parse_args()

    if not args.csv.exists():
        sys.exit(f"No existe el archivo {args.csv}")
    datos = leer_csv(args.csv)
    resultados = [calibrar(device_id, mediciones) for device_id, mediciones in sorted(datos.items())]

    imprimir(resultados)
    args.salida.mkdir(parents=True, exist_ok=True)
    guardar_csv(resultados, args.salida / "resultados_calibracion.csv")
    guardar_html(resultados, args.salida / "reporte_calibracion.html", args.csv.name)
    print(f"Reportes: {args.salida / 'resultados_calibracion.csv'}  ·  {args.salida / 'reporte_calibracion.html'}")

    if args.aplicar:
        print("\nAplicando coeficientes en la plataforma…")
        aplicar(resultados, args.aplicar)


if __name__ == "__main__":
    main()
