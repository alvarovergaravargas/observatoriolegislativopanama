"""
=============================================================
 SCRAPER COMPLETO - Observatorio Legislativo
 Asamblea Nacional de Panamá

 1. Extrae proyectos de sistemas.asamblea.gob.pa
 2. Extrae diputados de espaciocivico.org
 3. Cruza y genera resumen.json para el dashboard

INSTALACIÓN:
    pip install playwright
    playwright install chromium

EJECUCIÓN:
    python scraper.py
=============================================================
"""

import json, re, time, unicodedata
from collections import defaultdict
from datetime import datetime
from playwright.sync_api import sync_playwright

URL_LEG  = "https://sistemas.asamblea.gob.pa/segLegis/viewsPublico/SeguimientoLegislativo"
URL_DIPS = "https://espaciocivico.org/diputados"


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def normalizar(s):
    s = s.upper().strip()
    s = unicodedata.normalize('NFD', s)
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    s = re.sub(r'^H\.D\.?S?\s+', '', s)
    return re.sub(r'\s+', ' ', s).strip()

def encontrar_diputado(pn, dip_norm):
    for dn, d in dip_norm:
        if dn == pn: return d
    for dn, d in dip_norm:
        ap = ' '.join(dn.split()[-2:])
        if len(ap) > 4 and ap in pn: return d
    for dn, d in dip_norm:
        w = dn.split(); wp = pn.split()
        if len(w) >= 2 and w[-1] in wp and w[0] in wp: return d
    return None


# ─────────────────────────────────────────────
# SCRAPER 1: PROYECTOS LEGISLATIVOS
# ─────────────────────────────────────────────
def extraer_filas_leg(page):
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
                    ficha:         tds[3]?.innerText.trim() || "",
                    proyecto:      tds[4]?.innerText.trim() || "",
                    anteproyecto:  tds[5]?.innerText.trim() || "",
                    titulo:        tds[6]?.innerText.trim() || "",
                    etapa:         tds[7]?.innerText.trim() || "",
                    proponente:    tds[8]?.innerText.trim() || "",
                });
            });
            return filas;
        }
    """)

def navegar_pagina_leg(page, numero, ficha_actual):
    page.evaluate(f"__doPostBack('dataTable','Page${numero}')")
    page.wait_for_load_state("networkidle")
    for _ in range(20):
        page.wait_for_timeout(400)
        filas = extraer_filas_leg(page)
        if filas and filas[0]["ficha"] != ficha_actual:
            return True
    return False

def scrape_proyectos(page):
    print(f"\n[1/2] Extrayendo proyectos de {URL_LEG}")
    page.goto(URL_LEG, wait_until="networkidle", timeout=60000)
    page.wait_for_timeout(2000)
    page.click("#btnMostrarTodo")
    page.wait_for_selector("table tbody tr td", timeout=20000)
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(1000)

    todos, fichas_vistas, pagina_num, sin_nuevos = [], set(), 1, 0

    while True:
        filas = extraer_filas_leg(page)
        if not filas: break

        primera = filas[0]["ficha"]
        if primera in fichas_vistas:
            print(f"  Pág {pagina_num}: repetido — fin.")
            break

        nuevas = [f for f in filas if f["ficha"] not in fichas_vistas]
        print(f"  Pág {pagina_num}: {len(filas)} registros ({len(nuevas)} nuevos)")

        for f in filas:
            if f["ficha"] not in fichas_vistas:
                f["pagina"] = pagina_num
                fichas_vistas.add(f["ficha"])
                todos.append(f)

        if not nuevas:
            sin_nuevos += 1
            if sin_nuevos >= 3: break
        else:
            sin_nuevos = 0

        if not navegar_pagina_leg(page, pagina_num+1, primera): break
        pagina_num += 1

    print(f"  Total: {len(todos)} proyectos")
    return todos


# ─────────────────────────────────────────────
# SCRAPER 2: DIPUTADOS
# ─────────────────────────────────────────────
def extraer_tarjetas_dips(page):
    return page.evaluate("""
        () => {
            const cards = [...document.querySelectorAll('a[href*="/diputados/"]')]
                .filter(a => a.querySelector('img') && a.querySelector('h3'));
            return cards.map(card => {
                const lines = card.innerText.trim().split('\\n').map(l=>l.trim()).filter(Boolean);
                const href  = card.getAttribute('href') || '';
                const cp    = (lines[2]||'').split(' - ');
                const sLine = lines.find(l=>l.toLowerCase().includes('suplente'))||'';
                return {
                    nombre:   card.querySelector('h3')?.innerText.trim()||lines[0]||'',
                    partido:  lines[1]||'',
                    circuito: cp[0]?.trim()||'',
                    provincia:cp.slice(1).join(' - ').trim()||'',
                    suplente: sLine.replace(/suplente:\\s*/i,'').trim(),
                    foto:     card.querySelector('img')?.src||'',
                    perfil:   href.startsWith('http')?href:'https://espaciocivico.org'+href,
                    slug:     href.replace('/diputados/','').replace(/\\/+$/,''),
                };
            });
        }
    """)

def scrape_diputados(page):
    print(f"\n[2/2] Extrayendo diputados de {URL_DIPS}")
    page.goto(URL_DIPS, wait_until="domcontentloaded", timeout=60000)
    try:
        page.wait_for_selector('a[href*="/diputados/"] h3', timeout=20000)
    except Exception: pass
    time.sleep(2)

    todos, slugs = [], set()

    # Intentar "Todos"
    try:
        page.select_option('select', label='Todos')
        time.sleep(3)
        dips = extraer_tarjetas_dips(page)
        if len(dips) >= 50:
            for d in dips:
                if d['slug'] not in slugs and d['nombre']:
                    slugs.add(d['slug']); todos.append(d)
            print(f"  Cargados con 'Todos': {len(todos)}")
            return todos
    except Exception: pass

    # Paginar
    page.goto(URL_DIPS, wait_until="domcontentloaded", timeout=60000)
    try: page.wait_for_selector('a[href*="/diputados/"] h3', timeout=20000)
    except Exception: pass
    time.sleep(2)

    for num in range(1, 10):
        dips = extraer_tarjetas_dips(page)
        if not dips: break
        nuevos = 0
        for d in dips:
            if d['slug'] not in slugs and d['nombre']:
                slugs.add(d['slug']); todos.append(d); nuevos += 1
        print(f"  Pág {num}: {len(dips)} tarjetas, {nuevos} nuevos")
        if not nuevos: break
        try:
            page.locator(f'a:text-is("{num+1}")').first.click(timeout=5000)
            page.wait_for_selector('a[href*="/diputados/"] h3', timeout=15000)
            time.sleep(1)
        except Exception:
            print(f"  No hay página {num+1} — fin.")
            break

    # Fallback: leer diputados.json guardado
    if len(todos) < 50:
        try:
            with open('diputados.json', encoding='utf-8') as f:
                raw = json.load(f)
            todos = raw if isinstance(raw, list) else raw.get('diputados', [])
            print(f"  Usando diputados.json guardado: {len(todos)}")
        except Exception as e:
            print(f"  No se pudo cargar diputados.json: {e}")

    print(f"  Total: {len(todos)} diputados")
    return todos


# ─────────────────────────────────────────────
# GENERAR RESUMEN.JSON
# ─────────────────────────────────────────────
def generar_resumen(datos, dips, ts):
    dip_norm = [(normalizar(d['nombre']), d) for d in dips]

    prod = defaultdict(lambda: {'proyectos':0,'leyes':0,'etapas':{}})
    meses, etapas = {}, {}

    for r in datos:
        # Timeline
        parts = r['fecha_presentacion'].split('-')
        if len(parts) == 3:
            k = f"{parts[2]}-{parts[1]}"
            meses[k] = meses.get(k, 0) + 1
        # Etapas
        etapas[r['etapa']] = etapas.get(r['etapa'], 0) + 1
        # Por diputado
        for p in r['proponente'].split(','):
            pn = normalizar(p.strip())
            if not pn: continue
            dip = encontrar_diputado(pn, dip_norm)
            if dip:
                key = dip['nombre']
                prod[key]['proyectos'] += 1
                if r['etapa'] == 'Ley': prod[key]['leyes'] += 1
                et = prod[key]['etapas']
                et[r['etapa']] = et.get(r['etapa'], 0) + 1

    # Enriquecer diputados
    diputados_enriq = []
    for d in dips:
        p = prod.get(d['nombre'], {'proyectos':0,'leyes':0,'etapas':{}})
        diputados_enriq.append({**d, **p})
    diputados_enriq.sort(key=lambda x: x['proyectos'], reverse=True)

    # Por partido
    por_partido = defaultdict(lambda: {'diputados':0,'proyectos':0,'leyes':0})
    por_provincia = defaultdict(lambda: {'diputados':0,'proyectos':0,'leyes':0})
    for d in diputados_enriq:
        por_partido[d['partido']]['diputados'] += 1
        por_partido[d['partido']]['proyectos'] += d['proyectos']
        por_partido[d['partido']]['leyes'] += d['leyes']
        por_provincia[d['provincia']]['diputados'] += 1
        por_provincia[d['provincia']]['proyectos'] += d['proyectos']
        por_provincia[d['provincia']]['leyes'] += d['leyes']

    return {
        'fecha_extraccion': ts,
        'fuente': URL_LEG,
        'total_proyectos': len(datos),
        'total_leyes': sum(1 for r in datos if r['etapa']=='Ley'),
        'total_diputados': len(dips),
        'etapas': etapas,
        'timeline': dict(sorted(meses.items())),
        'diputados': diputados_enriq,
        'por_partido': {k:dict(v) for k,v in sorted(por_partido.items(), key=lambda x:-x[1]['proyectos'])},
        'por_provincia': {k:dict(v) for k,v in sorted(por_provincia.items(), key=lambda x:-x[1]['proyectos'])},
    }


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
def main():
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    print("=" * 55)
    print(" SCRAPER - Observatorio Legislativo Panamá")
    print("=" * 55)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
        )
        datos = scrape_proyectos(page)
        dips  = scrape_diputados(page)
        browser.close()

    # Guardar datos crudos
    with open("datos.json", "w", encoding="utf-8") as f:
        json.dump({"fecha_extraccion":ts,"fuente":URL_LEG,"total_registros":len(datos),"datos":datos},
                  f, ensure_ascii=False, indent=2)

    with open("diputados.json", "w", encoding="utf-8") as f:
        json.dump({"fuente":URL_DIPS,"total":len(dips),"diputados":dips},
                  f, ensure_ascii=False, indent=2)

    # Generar resumen
    resumen = generar_resumen(datos, dips, ts)
    with open("resumen.json", "w", encoding="utf-8") as f:
        json.dump(resumen, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*55}")
    print(f" COMPLETADO")
    print(f"  Proyectos : {len(datos)}")
    print(f"  Leyes     : {resumen['total_leyes']}")
    print(f"  Diputados : {len(dips)}")
    print(f"{'='*55}")
    print("Archivos generados: datos.json · diputados.json · resumen.json")

if __name__ == "__main__":
    main()
