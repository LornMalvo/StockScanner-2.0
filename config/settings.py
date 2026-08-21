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
    "dcf": 0.25,
    "multiplos": 0.15,
    "ev_ebitda": 0.20,
    "peg": 0.15,
    "consenso": 0.25,
}
# El consenso duplica peso si lo cubren >= 10 analistas. Se retiró el
# requisito adicional de unanimidad (100% de recomendaciones de compra):
# con cobertura amplia (ej. AVGO, 45 analistas) la probabilidad de
# unanimidad total es casi nula, así que esa condición dejaba el peso
# doble inactivo en la práctica incluso en los valores mejor cubiertos.
CONSENSO_MIN_ANALISTAS = 10

# ------------------------------------------------------ parámetros de DCF ----
DCF_ANIOS = 5
DCF_WACC_DEFECTO = 0.09
DCF_G_TERMINAL = 0.025
DCF_CRECIMIENTO_MAX = 0.20  # techo por defecto si el sector no tiene uno propio
DCF_CRECIMIENTO_MIN = -0.05

# WACC vía CAPM simplificado: tasa libre de riesgo + beta x prima de mercado.
# El suelo del 6% anterior era indefendible para renta variable (implicaba
# exigir a una acción poco más que a un bono) e inflaba sistemáticamente la
# valoración de empresas con beta baja, que es justo donde el DCF más se
# disparaba (NBIX: beta 0,55 -> WACC 6,7% -> DCF un +50% sobre el consenso).
# La prima sube de 4,5% a 5,5%, más acorde con las primas históricas de
# riesgo de mercado.
DCF_TASA_LIBRE_RIESGO = 0.042
DCF_PRIMA_MERCADO = 0.055
DCF_WACC_MIN = 0.075
DCF_WACC_MAX = 0.14

# Techo de crecimiento diferenciado por sector: sectores de crecimiento
# estructural alto (Tecnología, Salud) pueden sostener tasas más altas que
# sectores maduros (Utilities, Energy) sin que sea una señal de exceso de
# optimismo. Sustituye al techo único global de antes.
DCF_CRECIMIENTO_MAX_SECTOR = {
    "Technology": 0.30,
    "Communication Services": 0.25,
    "Healthcare": 0.25,
    "Consumer Cyclical": 0.20,
    "Consumer Defensive": 0.12,
    "Industrials": 0.18,
    "Financial Services": 0.15,
    "Energy": 0.12,
    "Basic Materials": 0.15,
    "Utilities": 0.08,
    "Real Estate": 0.12,
}

# ------------------------------------------------ parámetros valoración PEG ---
# PER justo = PEG objetivo x crecimiento estimado (en %), aplicado al BPA
# estimado del próximo ejercicio. Regla de Lynch: un PEG de 1 representa un
# precio razonable para el ritmo de crecimiento de la empresa. No se usa el
# PEG mediano del sector como objetivo porque, al multiplicarse por el
# crecimiento, valores de 1,8-1,9 disparan el PER justo a niveles absurdos
# (NBIX: 1,9 x 17,3 = PER 33x -> ~390$, casi el doble del consenso).
PEG_OBJETIVO = 1.0
PEG_CRECIMIENTO_MIN = 0.05  # por debajo, el método no aporta señal fiable
PEG_CRECIMIENTO_MAX = 0.25  # techo para no extrapolar crecimientos explosivos

# --------------------------------------------- pesos de calidad (Bloque 4) ----
# Estructura de 4 bloques analíticos al 25% cada uno. Sustituye al esquema
# anterior, que agregaba 9 criterios dentro de un único "piotroski" con peso
# 18: ahora esos criterios están disueltos en métricas individuales visibles
# (rotación de activos, margen bruto, ROA, apalancamiento, liquidez,
# dilución), de modo que se ve exactamente qué falla y cuánto pesa.
BLOQUES_CALIDAD = {
    "I. Crecimiento y Eficiencia": {
        "tendencia_ingresos": 12,
        "tendencia_beneficios": 11,
        "rotacion_activos": 2,
    },
    "II. Rentabilidad y Calidad": {
        "roic": 8,
        "calidad_beneficio": 5,
        "margen_neto": 4,
        "margen_bruto": 4,
        "roa": 2,
        "roe": 2,
    },
    "III. Salud Financiera": {
        "net_debt_ebitda": 5,
        "dilucion": 5,
        "fcf_solidez": 4,
        "cobertura_intereses": 4,
        "current_ratio": 2,
        "debt_equity": 2,
        "apalancamiento": 2,
        "liquidez_creciente": 1,
    },
    "IV. Valoración Relativa": {
        "peg": 8,
        "forward_per": 7,
        "ev_ebitda": 5,
        "per_vs_historico": 3,
        "per_vs_sector": 2,
    },
}
# Vista plana (métrica -> peso) para `ponderar()`, que redistribuye el peso
# de las métricas sin dato entre las disponibles. Suma 100.
PESOS_CALIDAD = {
    metrica: peso for bloque in BLOQUES_CALIDAD.values() for metrica, peso in bloque.items()
}

# Margen bruto mediano por sector (heurístico propio, como el resto de
# medianas sectoriales de este archivo). Se evalúa el nivel frente al sector,
# no solo si crece: un 85% estable dice más sobre el foso competitivo que un
# 40% que sube un punto.
MARGEN_BRUTO_MEDIANO_SECTOR = {
    "Technology": 0.55,
    "Communication Services": 0.45,
    "Healthcare": 0.60,
    "Consumer Cyclical": 0.35,
    "Consumer Defensive": 0.32,
    "Industrials": 0.30,
    "Financial Services": 0.50,
    "Energy": 0.28,
    "Basic Materials": 0.25,
    "Utilities": 0.35,
    "Real Estate": 0.45,
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

# ----------------------------- medias sectoriales adicionales (fallback) ----
# Mismo criterio que las tablas anteriores: estimaciones heurísticas propias,
# usadas solo para resaltar en el apartado "Fundamentales" (Bloque 3) qué
# métricas destacan sobre la media de su sector. No sustituyen una fuente de
# comparables reales; si se detecta una mejor, migrar aquí.
FORWARD_PER_MEDIANO_SECTOR = {
    "Technology": 24.0,
    "Communication Services": 17.0,
    "Consumer Cyclical": 18.0,
    "Consumer Defensive": 19.0,
    "Healthcare": 19.0,
    "Financial Services": 12.0,
    "Industrials": 18.0,
    "Energy": 11.0,
    "Basic Materials": 13.0,
    "Utilities": 16.0,
    "Real Estate": 26.0,
}
PEG_MEDIANO_SECTOR = {
    "Technology": 2.0,
    "Communication Services": 1.8,
    "Consumer Cyclical": 1.7,
    "Consumer Defensive": 2.2,
    "Healthcare": 1.9,
    "Financial Services": 1.4,
    "Industrials": 1.8,
    "Energy": 1.3,
    "Basic Materials": 1.5,
    "Utilities": 2.5,
    "Real Estate": 2.3,
}
EV_EBITDA_MEDIANO_SECTOR = {
    "Technology": 18.0,
    "Communication Services": 10.0,
    "Consumer Cyclical": 12.0,
    "Consumer Defensive": 13.0,
    "Healthcare": 14.0,
    "Financial Services": 11.0,
    "Industrials": 12.0,
    "Energy": 6.0,
    "Basic Materials": 8.0,
    "Utilities": 10.0,
    "Real Estate": 16.0,
}
PS_MEDIANO_SECTOR = {
    "Technology": 6.0,
    "Communication Services": 3.0,
    "Consumer Cyclical": 1.5,
    "Consumer Defensive": 1.3,
    "Healthcare": 3.0,
    "Financial Services": 3.0,
    "Industrials": 1.8,
    "Energy": 1.2,
    "Basic Materials": 1.3,
    "Utilities": 2.2,
    "Real Estate": 6.0,
}
PB_MEDIANO_SECTOR = {
    "Technology": 8.0,
    "Communication Services": 3.0,
    "Consumer Cyclical": 4.0,
    "Consumer Defensive": 5.0,
    "Healthcare": 4.0,
    "Financial Services": 1.5,
    "Industrials": 3.5,
    "Energy": 1.8,
    "Basic Materials": 2.0,
    "Utilities": 1.8,
    "Real Estate": 2.0,
}
MARGEN_OPERATIVO_MEDIANO_SECTOR = {
    "Technology": 0.22,
    "Communication Services": 0.16,
    "Consumer Cyclical": 0.09,
    "Consumer Defensive": 0.08,
    "Healthcare": 0.13,
    "Financial Services": 0.25,
    "Industrials": 0.11,
    "Energy": 0.11,
    "Basic Materials": 0.10,
    "Utilities": 0.20,
    "Real Estate": 0.35,
}
MARGEN_EBITDA_MEDIANO_SECTOR = {
    "Technology": 0.30,
    "Communication Services": 0.25,
    "Consumer Cyclical": 0.13,
    "Consumer Defensive": 0.12,
    "Healthcare": 0.18,
    "Financial Services": 0.30,
    "Industrials": 0.16,
    "Energy": 0.20,
    "Basic Materials": 0.16,
    "Utilities": 0.35,
    "Real Estate": 0.45,
}
ROIC_MEDIANO_SECTOR = {
    "Technology": 0.16,
    "Communication Services": 0.10,
    "Consumer Cyclical": 0.10,
    "Consumer Defensive": 0.11,
    "Healthcare": 0.09,
    "Financial Services": 0.08,
    "Industrials": 0.10,
    "Energy": 0.07,
    "Basic Materials": 0.07,
    "Utilities": 0.05,
    "Real Estate": 0.05,
}
ROA_MEDIANO_SECTOR = {
    "Technology": 0.10,
    "Communication Services": 0.06,
    "Consumer Cyclical": 0.05,
    "Consumer Defensive": 0.06,
    "Healthcare": 0.05,
    "Financial Services": 0.01,
    "Industrials": 0.05,
    "Energy": 0.05,
    "Basic Materials": 0.04,
    "Utilities": 0.03,
    "Real Estate": 0.02,
}
DEBT_EQUITY_MEDIANO_SECTOR = {
    "Technology": 40.0,
    "Communication Services": 90.0,
    "Consumer Cyclical": 80.0,
    "Consumer Defensive": 70.0,
    "Healthcare": 50.0,
    "Financial Services": 150.0,
    "Industrials": 90.0,
    "Energy": 60.0,
    "Basic Materials": 70.0,
    "Utilities": 130.0,
    "Real Estate": 100.0,
}
CURRENT_RATIO_MEDIANO_SECTOR = {
    "Technology": 2.5,
    "Communication Services": 1.2,
    "Consumer Cyclical": 1.5,
    "Consumer Defensive": 1.0,
    "Healthcare": 1.8,
    "Financial Services": 1.1,
    "Industrials": 1.5,
    "Energy": 1.3,
    "Basic Materials": 1.7,
    "Utilities": 0.9,
    "Real Estate": 1.2,
}

# ------------------------------------------------------------------ caché ----
TTL_PRECIO = 300        # 5 min
TTL_FUNDAMENTALES = 3600  # 1 h
TTL_NOTICIAS = 900      # 15 min
TTL_FX = 600            # 10 min
