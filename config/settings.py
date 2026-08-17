"""Constantes globales de StockScanner.

Todo lo que sea "número mágico" (pesos, umbrales, colores) vive aquí para que
los módulos de cálculo sean auditables y ajustables sin tocar la lógica.
"""

APP_NOMBRE = "StockScanner"
APP_CLAIM = "Tu análisis del mercado"

# ---------------------------------------------------------------- paleta ----
C_PRIMARIO = "#004e64"
C_AZUL = "#0056a2"
C_VERDE = "#10b981"
C_TEAL = "#25a18e"
C_AMBAR = "#ffcb77"

# Colores derivados para las bandas de valoración (no sustituyen a la paleta,
# la extienden hacia los extremos que pide el enunciado).
C_VERDE_OSCURO = "#065f46"
C_NARANJA = "#f97316"
C_ROJO = "#dc2626"
C_ROJO_OSCURO = "#7f1d1d"

C_FONDO = "#f8fafc"
C_SUPERFICIE = "#ffffff"
C_TEXTO = "#0f172a"
C_TEXTO_TENUE = "#64748b"
C_BORDE = "#e2e8f0"

# ------------------------------------------------------------ navegación ----
SECCIONES = [
    "Análisis Individual",
    "Rastreador",
    "Gestión de Cartera",
    "Paper Trading",
    "Favoritos",
]

# Icono Material (nombre corto, sin prefijo) para cada sección de la navbar.
ICONOS_SECCION = {
    "Análisis Individual": "search",
    "Rastreador": "radar",
    "Gestión de Cartera": "work",
    "Paper Trading": "science",
    "Favoritos": "star",
}

# ------------------------------------------------------- texto de datos N/D --
TEXTO_ND = "Dato no disponible"

# --------------------------------------------------- bandas de valoración ----
# (upside_min, upside_max, etiqueta, color). Límites en % sobre el precio actual.
# None = sin límite. Intervalos cerrados por abajo, abiertos por arriba.
BANDAS_VALORACION = [
    (30.0, None, "MUY INFRAVALORADA — Oportunidad excepcional", C_VERDE_OSCURO),
    (12.0, 30.0, "INFRAVALORADA — Potencial alcista significativo", C_VERDE),
    (3.0, 12.0, "LIGERAMENTE INFRAVALORADA — Entrada atractiva", C_TEAL),
    (-3.0, 3.0, "PRECIO JUSTO — En rango de valor razonable", C_AMBAR),
    (-15.0, -3.0, "EN OBSERVACIÓN — Precio por encima del valor objetivo", C_NARANJA),
    (-30.0, -15.0, "SOBREVALORADA — Riesgo de corrección moderada", C_ROJO),
    (None, -30.0, "MUY SOBREVALORADA — Riesgo de corrección severa", C_ROJO_OSCURO),
]

# ------------------------------------------------- pesos de valoración FV ----
PESOS_FAIR_VALUE = {
    "dcf": 0.30,
    "multiplos": 0.30,
    "ddm": 0.15,
    "consenso": 0.25,
}
# El consenso duplica peso solo si es unánime (100% de recomendaciones de compra)
# y lo cubren >= 10 analistas.
CONSENSO_MIN_ANALISTAS = 10
CONSENSO_UNANIMIDAD = 1.0

# ------------------------------------------------------ parámetros de DCF ----
DCF_ANIOS = 5
DCF_WACC_DEFECTO = 0.09
DCF_G_TERMINAL = 0.025
DCF_CRECIMIENTO_MAX = 0.20  # se recorta el crecimiento estimado a este techo
DCF_CRECIMIENTO_MIN = -0.05

# ------------------------------------------------------ parámetros de DDM ----
DDM_RETORNO_EXIGIDO = 0.09
DDM_G_MAX = 0.06

# --------------------------------------------- pesos de calidad (Bloque 4) ----
PESOS_CALIDAD = {
    "piotroski": 22,
    "per_vs_sector": 8,
    "per_vs_historico": 8,
    "forward_per": 6,
    "margen_neto": 10,
    "roe": 10,
    "roic": 10,
    "peg": 8,
    "tendencia_ingresos": 8,
    "tendencia_beneficios": 6,
    "calidad_beneficio": 4,
}

# ----------------------------------------------- pesos de timing (Bloque 5) ----
PESOS_TIMING = {
    "rsi": 12,
    "macd": 12,
    "margen_seguridad": 10,
    "upside": 12,
    "peg": 8,
    "salud_fundamental": 12,
    "mm50": 8,
    "mm200": 8,
    "variacion_1a": 6,
    "distancia_ath_atl": 6,
    "obv": 6,
    "adx": 6,
    "proximidad_earnings": 6,
}

# El enunciado exige salud fundamental >= 60 para considerar buen timing.
SALUD_MINIMA_TIMING = 60
TIMING_TOPE_SIN_SALUD = 59  # con salud < 60 el timing no puede superar "VIGILAR"

SENIALES_TIMING = [
    (80, "ENTRADA IDEAL", C_VERDE_OSCURO),
    (60, "ENTRADA POSIBLE", C_VERDE),
    (40, "VIGILAR", C_AMBAR),
    (0, "NO ES MOMENTO", C_ROJO),
]

# ------------------------------------------------------- plan DCA (Bloque 6) --
DCA_SEPARACION_MIN_ENTRADAS = 0.10  # 10% mínimo entre niveles de entrada
DCA_PESOS_ENTRADA = [0.40, 0.35, 0.25]
DCA_PESOS_SALIDA = [0.35, 0.35, 0.30]
DCA_STOP_ATR_MULT = 2.5
DCA_STOP_MAX_CAIDA = 0.30  # el stop nunca se coloca a más de un 30% del nivel 1

# ---------------------------------- PER mediano por sector (fallback local) ----
# Solo se usa cuando no se puede calcular la mediana con comparables reales.
PER_MEDIANO_SECTOR = {
    "Technology": 28.0,
    "Communication Services": 19.0,
    "Consumer Cyclical": 20.0,
    "Consumer Defensive": 21.0,
    "Healthcare": 22.0,
    "Financial Services": 13.0,
    "Industrials": 21.0,
    "Energy": 12.0,
    "Basic Materials": 15.0,
    "Utilities": 18.0,
    "Real Estate": 30.0,
}
MARGEN_NETO_MEDIANO_SECTOR = {
    "Technology": 0.18,
    "Communication Services": 0.13,
    "Consumer Cyclical": 0.07,
    "Consumer Defensive": 0.06,
    "Healthcare": 0.10,
    "Financial Services": 0.20,
    "Industrials": 0.08,
    "Energy": 0.09,
    "Basic Materials": 0.08,
    "Utilities": 0.11,
    "Real Estate": 0.20,
}
ROE_MEDIANO_SECTOR = {
    "Technology": 0.20,
    "Communication Services": 0.14,
    "Consumer Cyclical": 0.15,
    "Consumer Defensive": 0.16,
    "Healthcare": 0.13,
    "Financial Services": 0.12,
    "Industrials": 0.15,
    "Energy": 0.13,
    "Basic Materials": 0.10,
    "Utilities": 0.09,
    "Real Estate": 0.07,
}

# ------------------------------------------------------------------ caché ----
TTL_PRECIO = 300        # 5 min
TTL_FUNDAMENTALES = 3600  # 1 h
TTL_NOTICIAS = 900      # 15 min
TTL_FX = 600            # 10 min
