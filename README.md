# 🏛️ Observatorio Legislativo — Asamblea Nacional de Panamá

Dashboard interactivo que muestra la producción legislativa de la Asamblea Nacional, con datos actualizados automáticamente cada 24 horas.

## 🌐 Demo
Desplegado en Netlify: `https://TU-SITIO.netlify.app`

## 📊 Qué muestra
- Total de proyectos, leyes aprobadas, diputados activos
- Actividad legislativa por mes (gráfico de barras)
- Distribución por etapa (donut chart)
- Embudo legislativo (de preliminar a ley)
- Top 20 diputados por proyectos presentados
- Tabla completa con producción por diputado (ordenable, buscable)

## 🗂️ Estructura
```
asamblea-dashboard/
├── index.html              # Dashboard (frontend)
├── scraper.py              # Scraper de datos
├── resumen.json            # Datos procesados (auto-generado)
├── datos.json              # Datos crudos (auto-generado)
├── netlify.toml            # Configuración Netlify
└── .github/workflows/
    └── update-data.yml     # Actualización automática diaria
```

## 🚀 Despliegue

### 1. Subir a GitHub
```bash
git init
git add .
git commit -m "🏛️ Observatorio Legislativo"
git remote add origin https://github.com/TU-USUARIO/asamblea-dashboard.git
git push -u origin main
```

### 2. Conectar Netlify
1. Ve a [netlify.com](https://netlify.com) → **Add new site** → **Import from Git**
2. Selecciona tu repositorio
3. Build command: *(dejar vacío)*
4. Publish directory: `.`
5. Click **Deploy**

### 3. Activar GitHub Actions
Para que los datos se actualicen automáticamente:
1. Ve a tu repo en GitHub → **Settings** → **Actions** → **General**
2. En *Workflow permissions*, selecciona **Read and write permissions**
3. Los datos se actualizarán cada día a las 8:00 AM UTC
4. También puedes ejecutarlo manualmente desde **Actions** → **Actualizar datos legislativos** → **Run workflow**

### 4. Ejecutar scraper localmente (opcional)
```bash
pip install playwright pandas
playwright install chromium
python scraper.py
```

## 🔄 Cómo funciona la actualización automática
1. GitHub Actions ejecuta `scraper.py` cada día
2. El scraper extrae todos los proyectos de `sistemas.asamblea.gob.pa`
3. Genera `resumen.json` y `datos.json`
4. Hace commit automático al repositorio
5. Netlify detecta el nuevo commit y redespliega el sitio automáticamente

## 📡 Fuente de datos
[Seguimiento Legislativo — Asamblea Nacional de Panamá](https://sistemas.asamblea.gob.pa/segLegis/viewsPublico/SeguimientoLegislativo)
