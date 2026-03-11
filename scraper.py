"""
=============================================================
 SCRAPER - Seguimiento Legislativo - Asamblea Nacional de Panamá
 Genera: resumen.json (para el dashboard) y datos.json (raw)
=============================================================

INSTALACIÓN:
    pip install playwright pandas
    playwright install chromium

EJECUCIÓN:
    python scraper.py
=============================================================
"""

import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from playwright.sync_api import sync_playwright

URL = "https://sistemas.asamblea.gob.pa/segLegis/viewsPublico/SeguimientoLegislativo"


def extraer_filas(page):
    return page.evaluate("""
        () => {
            const filas = [];
            const tabla = document.querySelector('table');
            if (!tabla) return filas;
            tabla.querySelectorAll('tbody tr').forEach(tr => {
                const tds = [...tr.querySelectorAll('td')];
                if (tds.length < 7) return;
                const fecha = tds[2]?.innerText.trim() || "";
                if (!/^\d{2}-\d{2}-\d{4}$/.test(fecha)) return;
                filas.push({
                    fecha_presentacion: fecha,
                    ficha:              tds[3]?.innerText.trim() || "",
                    proyecto:           tds[4]?.innerText.trim() || "",
                    anteproyecto:       tds[5]?.innerText.trim() || "",
                    titulo:             tds[6]?.innerText.trim() || "",
                    etapa:              tds[7]?.innerText.trim() || "",
                    proponente:         tds[8]?.innerText.trim() || "",
                });
            });
            return filas;
        }
    """)


def navegar_a(page, numero, ficha_esperada_diferente):
    page.evaluate(f"__doPostBack('dataTable','Page${numero}')")
    page.wait_for_load_state("networkidle")
    for _ in range(20):
        page.wait_for_timeout(400)
        filas = extraer_filas(page)
        if filas and filas[0]["ficha"] != ficha_esperada_diferente:
            return True
    return False


def limpiar_nombre(nombre):
    return re.sub(r'^H\.D\.?S?\s+', '', nombre.strip())


def generar_resumen(datos, ts):
    prod = defaultdict(lambda: {"proyectos": 0, "leyes": 0, "etapas": {}})
    meses = {}
    etapas = {}

    for r in datos:
        # Timeline
        parts = r["fecha_presentacion"].split("-")
        if len(parts) == 3:
            key = f"{parts[2]}-{parts[1]}"
            meses[key] = meses.get(key, 0) + 1

        # Etapas globales
        etapas[r["etapa"]] = etapas.get(r["etapa"], 0) + 1

        # Por diputado
        for p in r["proponente"].split(","):
            nombre = limpiar_nombre(p)
            if not nombre:
                continue
            prod[nombre]["proyectos"] += 1
            if r["etapa"] == "Ley":
                prod[nombre]["leyes"] += 1
            et = prod[nombre]["etapas"]
            et[r["etapa"]] = et.get(r["etapa"], 0) + 1

    diputados = sorted(
        [{"nombre": k, **v} for k, v in prod.items()],
        key=lambda x: x["proyectos"],
        reverse=True,
    )

    return {
        "fecha_extraccion": ts,
        "fuente": URL,
        "total_proyectos": len(datos),
        "total_leyes": sum(1 for r in datos if r["etapa"] == "Ley"),
        "total_diputados": len(prod),
        "etapas": etapas,
        "timeline": dict(sorted(meses.items())),
        "diputados": diputados,
    }


def main():
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    print("=" * 55)
    print(" SCRAPER - Seguimiento Legislativo - Asamblea Panamá")
    print("=" * 55)

    todos = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
        )

        print("\n[1/2] Cargando resultados...")
        page.goto(URL, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(2000)
        page.click("#btnMostrarTodo")
        page.wait_for_selector("table tbody tr td", timeout=20000)
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1000)
        print("  OK\n")

        print("[2/2] Extrayendo páginas...")
        fichas_vistas = set()
        pagina_num = 1
        paginas_sin_nuevos = 0

        while True:
            filas = extraer_filas(page)
            if not filas:
                print(f"  Pág {pagina_num}: vacía — fin.")
                break

            primera_ficha = filas[0]["ficha"]
            if primera_ficha in fichas_vistas:
                print(f"  Pág {pagina_num}: datos repetidos — fin.")
                break

            nuevas = [f for f in filas if f["ficha"] not in fichas_vistas]
            print(f"  Pág {pagina_num}: {len(filas)} registros ({len(nuevas)} nuevos)")

            for f in filas:
                if f["ficha"] not in fichas_vistas:
                    f["pagina"] = pagina_num
                    fichas_vistas.add(f["ficha"])
                    todos.append(f)

            if len(nuevas) == 0:
                paginas_sin_nuevos += 1
                if paginas_sin_nuevos >= 3:
                    print("  3 páginas sin nuevos — fin.")
                    break
            else:
                paginas_sin_nuevos = 0

            ok = navegar_a(page, pagina_num + 1, primera_ficha)
            if not ok:
                print(f"  No cambió al ir a pág {pagina_num+1} — fin.")
                break

            pagina_num += 1

        browser.close()

    print(f"\nTotal extraído: {len(todos)} registros")

    # Guardar datos.json (raw)
    with open("datos.json", "w", encoding="utf-8") as f:
        json.dump({"fecha_extraccion": ts, "fuente": URL,
                   "total_registros": len(todos), "datos": todos},
                  f, ensure_ascii=False, indent=2)
    print("Guardado: datos.json")

    # Guardar resumen.json (para el dashboard)
    resumen = generar_resumen(todos, ts)
    with open("resumen.json", "w", encoding="utf-8") as f:
        json.dump(resumen, f, ensure_ascii=False, indent=2)
    print("Guardado: resumen.json")

    print("\n" + "=" * 55)
    print(f" COMPLETADO: {len(todos)} proyectos · {resumen['total_leyes']} leyes")
    print("=" * 55)


if __name__ == "__main__":
    main()
