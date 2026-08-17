# StockScanner — Tu análisis del mercado

Aplicación de análisis bursátil construida con Streamlit, Supabase y las APIs de
yfinance, Finnhub y SEC EDGAR.

---

## Estructura de directorios

```
stockscanner/
├── main.py                       # Punto de entrada (solo configura y delega)
├── requirements.txt
├── README.md
├── .gitignore
├── .streamlit/
│   ├── config.toml               # Tema claro con la paleta corporativa
│   └── secrets.toml.example      # Plantilla de credenciales (no subir la real)
├── assets/
│   └── logo.png                  # Logo de la app
├── config/
│   └── settings.py               # Paleta, umbrales, pesos y constantes
├── core/                         # Lógica de negocio (sin Streamlit salvo caché)
│   ├── datos_api.py              # yfinance + Finnhub + SEC EDGAR + tipo de cambio
│   ├── indicadores.py            # RSI, MACD, ADX, OBV, ATR, Fibonacci, gaps, pivotes
│   ├── valoracion.py             # DCF, múltiplos, DDM, consenso, Piotroski, calidad
│   ├── timing.py                 # Puntuación de timing y señal de entrada
│   ├── plan_dca.py               # Motor de confluencia, niveles DCA y veredicto
│   ├── bd_supabase.py            # Persistencia
│   └── alertas_telegram.py       # Notificaciones
├── ui/
│   ├── estilos.py                # CSS con las variables de color
│   ├── componentes.py            # Métricas, alertas, notas, gráfico precio-MACD
│   ├── interfaz.py               # Cabecera, navbar y router de secciones
│   └── vistas/
│       ├── analisis_individual.py
│       ├── rastreador.py
│       ├── gestion_cartera.py
│       ├── paper_trading.py
│       └── favoritos.py
├── utils/
│   └── formato.py                # Validación, ponderación segura y formateo
└── sql/
    └── schema.sql                # Esquema de Supabase
```

**Regla de oro del proyecto:** un dato ausente nunca se convierte en cero. Todo
pasa por `utils.formato.es_valido()` y `utils.formato.ponderar()`, que excluye el
componente y redistribuye su peso entre los disponibles. En la interfaz aparece
literalmente «Dato no disponible» y en cada desglose se indica la cobertura real
del modelo.

---

## Puesta en marcha

### 1. Local

```bash
git clone https://github.com/<tu-usuario>/stockscanner.git
cd stockscanner
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # y rellénalo
streamlit run main.py
```

La app arranca sin credenciales: el análisis funciona con yfinance y los
apartados que dependen de Supabase avisan de que falta la conexión.

### 2. Supabase

1. Crea un proyecto en [supabase.com](https://supabase.com).
2. SQL Editor → pega el contenido de `sql/schema.sql` → Run.
3. Settings → API → copia `Project URL` y la clave `anon public`.

### 3. Claves de API

| Secret | Dónde se obtiene | Obligatorio |
|---|---|---|
| `SUPABASE_URL` / `SUPABASE_KEY` | Supabase → Settings → API | Para favoritos, cartera y paper trading |
| `FINNHUB_API_KEY` | [finnhub.io](https://finnhub.io) (plan gratuito) | Recomendado (noticias y sorpresas de resultados) |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | @BotFather y @userinfobot | Opcional (alertas) |

SEC EDGAR no requiere clave, pero sí un `User-Agent` identificable: edita
`SEC_UA` en `core/datos_api.py` con tu correo, como exige la SEC.

### 4. GitHub + Streamlit Community Cloud

```bash
git init && git add . && git commit -m "StockScanner: estructura inicial"
git branch -M main
git remote add origin https://github.com/<tu-usuario>/stockscanner.git
git push -u origin main
```

En [share.streamlit.io](https://share.streamlit.io): **New app** → repositorio,
rama `main`, archivo principal `main.py` → **Advanced settings → Secrets**: pega
el contenido de tu `secrets.toml` → **Deploy**.

`.streamlit/secrets.toml` está en `.gitignore`. No lo subas nunca.

---

## Notas sobre los algoritmos

- **Valor objetivo justo:** media ponderada de DCF (30 %), múltiplos (30 %),
  DDM (15 %) y consenso (25 %). El consenso duplica peso solo si es unánime
  (100 % de recomendaciones de compra) y lo cubren 10 o más analistas. Los
  métodos no calculables se excluyen y sus pesos se redistribuyen.
- **Piotroski F-Score:** se puntúa sobre los criterios efectivamente evaluables
  y se normaliza sobre 9; los no evaluables no suman ni restan.
- **Timing:** si la salud fundamental es inferior a 60, la puntuación se limita a
  59 (techo «VIGILAR»), tal y como exige la especificación.
- **PER sectorial:** `config/settings.py` incluye medianas de referencia como
  respaldo. Sustitúyelas por el cálculo con comparables reales cuando dispongas
  de una fuente de peers.

Este proyecto es una herramienta de análisis, no asesoramiento financiero.
