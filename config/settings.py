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

# --------------------------------------------- paleta del plan DCA (gráfico)
# Las entradas van en la familia AZUL y las salidas en la VERDE. Antes las
# entradas eran verdes (C_VERDE) y las salidas turquesa (C_TEAL): a 1,3 px de
# grosor los dos tonos eran prácticamente indistinguibles, que es justo lo
# contrario de lo que tiene que comunicar el gráfico (comprar vs. vender).
#
# Dentro de cada familia el tono se aclara del nivel 1 al 3, así que el color
# codifica DOS cosas a la vez: qué se hace (comprar/vender/proteger) y en qué
# orden llega. Por eso las líneas ya no necesitan bajar de opacidad para
# distinguir el nivel, y todas se pintan sólidas y legibles.
PLAN_COLORES_ENTRADA = ("#1d4ed8", "#3b82f6", "#93c5fd")
PLAN_COLORES_SALIDA = ("#059669", "#10b981", "#6ee7b7")
PLAN_COLOR_STOP = C_ROJO

# Alto del gráfico de cotización + MACD. 430 px dejaba las velas y los hasta
# 7 niveles del plan comprimidos en una franja demasiado estrecha para leer
# nada; con 560 px y menos peso relativo del MACD el plan se lee de un
# vistazo.
GRAFICO_ALTO = 560
GRAFICO_PROPORCION_FILAS = (0.75, 0.25)  # precio / MACD

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
# Recalibrado tras simulación sobre cesta de 29 tickers multisector (ver
# ESTADO_PROYECTO.md). El DCF baja de 0,25 a 0,10: en la calibración fue,
# con diferencia, el método más alejado del consenso de analistas (mediana
# de desviación ~50-60% frente a ~25-35% de multiplos/ev_ebitda/peg), y su
# desviación media no mejoró pese a corregir la metodología (FCFF, WACC
# ponderado real, deuda contada una sola vez) — el problema no es un bug de
# cálculo sino la naturaleza del método: cualquier tasa de descuento
# defendible topa el múltiplo de salida muy por debajo de lo que paga hoy
# el mercado en sectores de alto crecimiento (ver nota en valorar_dcf).
# No se retira del todo porque en varios tickers (los de FCF estable y
# deuda normal) seguía siendo la lectura más precisa de los cuatro. El resto
# de pesos se reescala proporcionalmente para seguir sumando 1,0.
PESOS_FAIR_VALUE = {
    "dcf": 0.10,
    "multiplos": 0.17,
    "ev_ebitda": 0.22,
    "peg": 0.17,
    "consenso": 0.34,
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
DCF_WACC_MIN = 0.075   # suelo de Ke (coste de recursos propios, CAPM)
DCF_WACC_MAX = 0.14

# WACC PONDERADO real (Ke y Kd por estructura de capital), no solo Ke. El
# suelo/techo de abajo acotan el WACC ya ponderado, más laxos que los de Ke
# porque una empresa con deuda barata puede defender un WACC más bajo que
# su Ke en solitario (caso AMT: Kd real 3,4%).
DCF_WACC_MIN_PONDERADO = 0.055
DCF_WACC_MAX_PONDERADO = 0.14

# Coste de deuda (Kd). Se calcula como intereses/deuda cuando ambos datos
# son fiables; el suelo solo actúa como red de seguridad ante datos rotos
# (intereses ~0 con deuda grande), nunca sustituye el dato real — un suelo
# forzado sistemáticamente arregla un ticker (VZ) y rompe otro con deuda
# genuinamente barata (AMT, REIT con Kd real 3,4%).
DCF_KD_MIN = 0.047   # Rf + 0,5%: un Kd por debajo del bono sin riesgo no es defendible
DCF_KD_MAX = 0.12

# Tope al múltiplo de salida implícito del valor terminal (Gordon growth).
# Con WACC bajo y g terminal 2,5%, Gordon puede implicar múltiplos de 30x+
# el FCF del año 5 (caso VZ: WACC 5,5% -> VT en 33x -> DCF a +242% del
# consenso). El tope ataca el modo de fallo directamente.
DCF_MULTIPLO_TERMINAL_MAX = 20.0

# Guardarraíl de deuda contaminada por financiera cautiva (caso Ford: Ford
# Credit infla `totalDebt` muy por encima de la estructura de capital del
# negocio industrial). Si deuda/capitalización bursátil supera este umbral
# en un sector que NO es estructuralmente apalancado, el dato no es fiable
# y el DCF se excluye en vez de devolver un número inventado.
DCF_DEUDA_MKTCAP_MAX = 2.0
DCF_SECTORES_APALANCADOS = {"Financial Services", "Real Estate", "Utilities"}

# Tipo impositivo por defecto cuando `effectiveTaxRate` no es fiable
# (ausente o fuera de [0, 45%]), usado para desapalancar el FCF a FCFF.
DCF_TIPO_IMPOSITIVO_DEFECTO = 0.21

# Umbral de anomalía para la normalización de la base de FCF: por encima de
# esta desviación sobre la mediana de 3 años en una serie oscilante, se usa
# la mediana en vez del último ejercicio.
DCF_ANOMALIA_FCF = 0.35

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
# Por debajo de este crecimiento el método se EXCLUYE (antes se pinzaba a
# 5%, lo que con PEG_OBJETIVO=1.0 implicaba un PER justo mínimo de 5x —
# indefendible para KO, PG, SO, AMT. El PEG es una herramienta para
# empresas en crecimiento; forzarlo en una utility que crece al 4% es un
# error de categoría, no de calibración. En la calibración fue el método
# con más desviaciones extremas del motor (12 de 29 tickers >60% de
# desviación); tras el cambio a exclusión bajó a 2 de 29.
PEG_CRECIMIENTO_MIN = 0.10
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
# Los pesos SUMAN 100 a propósito: así el peso bruto de cada métrica coincide
# con el porcentaje que se muestra en pantalla (antes sumaban 112 y la
# interfaz enseñaba peso/112, lo que hacía imposible cuadrar la tabla a ojo).
#
# Dos cambios de fondo respecto al esquema anterior:
#
#  1. `margen_seguridad` DESAPARECE, fundido en `upside`. Ambos partían del
#     mismo numerador (valor_objetivo − precio) y solo cambiaban de
#     denominador (valor objetivo vs precio), así que eran la misma lectura
#     contada dos veces —20% del timing— y, peor aún, cualquier error del
#     valor objetivo entraba por partida doble en la nota en vez de
#     diluirse. Los 22 puntos que sumaban entre los dos bajan a 12.
#  2. Tres dimensiones nuevas que antes no tenían representación alguna:
#     intensidad del volumen reciente, contexto relativo frente al
#     sector/mercado y proximidad a las zonas del propio motor DCA.
#
# Agrupación conceptual de los pesos (la interfaz no los agrupa, es solo la
# lógica con la que están repartidos):
#   Momentum y flujo    34  (rsi, macd, obv, adx, volumen_relativo)
#   Estructura de precio 29  (mm50, mm200, ath/atl, variacion_1a, confluencia)
#   Valoración          17  (upside, peg)
#   Calidad             10  (salud_fundamental)
#   Contexto            10  (fuerza_relativa, proximidad_earnings)
PESOS_TIMING = {
    "rsi": 10,
    "macd": 9,
    "upside": 12,
    "peg": 5,
    "salud_fundamental": 10,
    "mm50": 6,
    "mm200": 6,
    "variacion_1a": 4,
    "distancia_ath_atl": 4,
    "obv": 4,
    "adx": 5,
    "volumen_relativo": 6,
    "fuerza_relativa": 6,
    "confluencia_dca": 9,
    "proximidad_earnings": 4,
}

# --------------------------- referencia de mercado para la fuerza relativa ----
# ETF sectorial de referencia (familia SPDR Select Sector, la más líquida y
# con histórico largo) para medir si el valor cae solo o cae con todo su
# sector. Un RSI en sobreventa mientras el sector sube es debilidad
# idiosincrática (mala señal); el mismo RSI con el sector cayendo es riesgo
# sistémico, que no dice nada malo de la empresa en concreto.
# Ojo: para valores no estadounidenses el ETF sectorial es una aproximación
# imperfecta (divisa y ciclo distintos); se acepta a sabiendas por no
# multiplicar las peticiones a Yahoo con un mapa de índices por país.
ETF_SECTORIAL = {
    "Technology": "XLK",
    "Communication Services": "XLC",
    "Consumer Cyclical": "XLY",
    "Consumer Defensive": "XLP",
    "Healthcare": "XLV",
    "Financial Services": "XLF",
    "Industrials": "XLI",
    "Energy": "XLE",
    "Basic Materials": "XLB",
    "Utilities": "XLU",
    "Real Estate": "XLRE",
}
ETF_MERCADO = "SPY"  # fallback cuando el sector no está en el mapa
FUERZA_RELATIVA_SESIONES = 63  # ~3 meses de sesiones bursátiles

# ------------------------------- volumen relativo del movimiento reciente ----
VOLUMEN_SESIONES_RECIENTES = 5   # ventana corta que se compara con la media 3m
VOLUMEN_VARIACION_NEUTRA = 1.0   # % por debajo del cual el tramo se considera plano

# ------------------------ proximidad a zona de confluencia del motor DCA ------
# Peso agregado a partir del cual una zona del motor DCA se considera
# "confluencia fuerte" (equivale, p. ej., a MM200 + Fibonacci + mínimo de 52
# semanas cayendo casi en el mismo precio).
DCA_CONFLUENCIA_FUERTE = 5.0
# Distancia a la zona medida en múltiplos de ATR(14), no en % fijo: a 0,5 ATR
# o menos la zona se considera "pegada" al precio; a partir de 4 ATR deja de
# ser relevante para el timing. En ATR y no en % por coherencia con el
# rediseño pendiente del motor DCA (umbrales adaptativos, no fijos).
CONFLUENCIA_ATR_CERCA = 0.5
CONFLUENCIA_ATR_LEJOS = 4.0
# Respaldo en % cuando no hay ATR disponible.
CONFLUENCIA_PCT_CERCA = 0.02
CONFLUENCIA_PCT_LEJOS = 0.15

# ------------------------- cruce de medias (Golden Cross / Death Cross) ------
# Informativo, SIN peso propio en PESOS_TIMING (ver docstring de
# `indicadores.cruce_medias`): la fuerza y dirección que revela ya las
# capturan el ADX direccional y las distancias mm50/mm200.
CRUCE_VENTANA_BUSQUEDA = 120   # sesiones hacia atrás para localizar el último cruce
CRUCE_VENTANA_PENDIENTE = 10   # sesiones para estimar si las medias convergen
CRUCE_PROXIMO_PCT = 3.0        # distancia MM50-MM200 (%) por debajo de la cual se avisa de cruce próximo

# El enunciado exige salud fundamental >= 60 para considerar buen timing.
SALUD_MINIMA_TIMING = 60
TIMING_TOPE_SIN_SALUD = 59  # con salud < 60 el timing no puede superar "VIGILAR"

SENIALES_TIMING = [
    (80, "ENTRADA IDEAL", C_VERDE_OSCURO),
    (60, "ENTRADA POSIBLE", C_VERDE),
    (40, "VIGILAR", C_AMBAR),
    (0, "NO ES MOMENTO", C_ROJO),
]

# Traducción y color del consenso de analistas (`info["recommendationKey"]`
# de yfinance). Se muestra como pastilla de color en el Bloque 5 (Timing).
# "none" es el valor que devuelve yfinance cuando no hay recomendación.
CONSENSO_ANALISTAS_ES = {
    "strong_buy": ("Compra fuerte", C_VERDE_OSCURO),
    "buy": ("Compra", C_VERDE),
    "hold": ("Mantener", C_AMBAR),
    "sell": ("Venta", C_NARANJA),
    "strong_sell": ("Venta fuerte", C_ROJO_OSCURO),
    "none": ("Sin recomendación", C_TEXTO_TENUE),
}

# ------------------------------------------------------ banda de cordura ----
# Tras calcular los 4 métodos, cada uno se compara con un ancla (el
# consenso de analistas si hay >= BANDA_MIN_ANALISTAS cobertura; si no, la
# mediana de los métodos disponibles). Dos niveles, ASIMÉTRICOS:
#   - Dentro de [ancla/BANDA_SUELO, ancla*BANDA_TECHO]: el método se usa
#     tal cual.
#   - Hasta [ancla/EXCLUSION_SUELO, ancla*EXCLUSION_TECHO]: se RECORTA al
#     borde de la banda (el método discrepa, pero su dirección sigue
#     siendo información real).
#   - Más allá: se EXCLUYE (no se recorta). Ahí el método no está
#     discrepando, ha fallado, y forzarlo al borde solo arrastraría la
#     media con un número inventado.
# Asimétrica porque el consenso del sell-side corre de media un 10-20% por
# encima del precio en el que termina cotizando el valor (los analistas
# rara vez publican objetivos por debajo del precio actual): ser más
# permisivo por debajo que por encima evita importar ese sesgo alcista al
# plan de DCA, que preferimos que se equivoque por el lado conservador.
BANDA_SUELO = 2.5
BANDA_TECHO = 1.6
EXCLUSION_SUELO = 4.0
EXCLUSION_TECHO = 2.5
BANDA_MIN_ANALISTAS = 5

# ------------------------------------------------------- plan DCA (Bloque 6) --
DCA_SEPARACION_MIN_ENTRADAS = 0.10  # RESPALDO: solo se usa si no hay ATR válido
DCA_PESOS_ENTRADA = [0.40, 0.35, 0.25]
DCA_PESOS_SALIDA = [0.35, 0.35, 0.30]
DCA_STOP_ATR_MULT = 2.5

# Pérdida máxima admitida. IMPORTANTE: se mide sobre el PRECIO MEDIO ESTIMADO
# del plan, no sobre el nivel 1. Anclarla al nivel 1 (como se hacía antes) era
# incoherente: si la escalera de entradas se abría más de un 30% entre N1 y N3
# —algo habitual en valores volátiles—, el suelo caía POR ENCIMA de N3, pisaba
# la regla del ATR y dejaba el stop pegado a la última entrada. Medida sobre el
# coste medio la restricción es económicamente interpretable ("no arriesgo más
# de un 30% de lo invertido") y ya no puede entrar en conflicto con la escalera.
DCA_STOP_MAX_CAIDA = 0.30

# Margen mínimo entre la última entrada y el stop. Garantiza que el plan no se
# detenga antes de haberse ejecutado del todo. Es proporcional a la volatilidad:
# un margen porcentual fijo dejaba stops a media sesión de distancia en valores
# con ATR alto. El suelo porcentual solo actúa como respaldo si no hay ATR.
DCA_STOP_MARGEN_MIN = 0.02
DCA_STOP_MARGEN_ATR_MULT = 1.5
DCA_STOP_MARGEN_MAX = 0.12

# Respaldo cuando no hay ni ATR ni mínimo de 52 semanas utilizable.
DCA_STOP_CAIDA_RESPALDO = 0.15

# ================== motor de confluencia de soportes/resistencias =============
# Rediseño completo del motor DCA. El diagnóstico previo (simulado sobre NBIX y
# GRAB) fue que los umbrales FIJOS descartaban zonas de confluencia fuerte por
# márgenes de 0,1-0,3 puntos porcentuales, tanto al fusionar candidatos como al
# elegir los 3 niveles finales. Todo lo que aquí se parametriza sustituye a
# umbrales fijos por magnitudes adaptativas al ATR de cada valor.

# ---------------------------------------------- agrupación por densidad -------
# Ya no hay "tolerancia de cluster" binaria (el antiguo 2,5% fijo). Cada
# candidato es una campana gaussiana de altura = su peso y anchura = SIGMA.
# Se suman todas las campanas y las zonas de confluencia son los máximos
# locales de la curva resultante: dos candidatos cercanos en términos de ATR
# generan un único pico aunque su distancia en % supere cualquier umbral.
CONFLUENCIA_SIGMA_ATR = 0.45      # anchura de la campana, en múltiplos de ATR(14)
CONFLUENCIA_SIGMA_PCT = 0.018     # respaldo en % del precio cuando no hay ATR
CONFLUENCIA_SIGMA_MAX_PCT = 0.030 # techo: con ATR muy alto las campanas fundirían todo
CONFLUENCIA_SIGMA_MIN_PCT = 0.004 # suelo: con ATR degenerado no se fundiría nada
CONFLUENCIA_REJILLA = 800         # nº de puntos de la rejilla de precios
CONFLUENCIA_PESO_MIN_ZONA = 0.8   # zonas por debajo de este peso se descartan

# --------------------------------------------- rango de trabajo del motor -----
# Al pasar a seleccionar POR PESO apareció un efecto secundario que el criterio
# antiguo (recorrido por precio) enmascaraba: una zona muy fuerte pero
# lejanísima —el mínimo de la burbuja de 2022, a un -66%— se cuela en el plan
# por tener mucho peso acumulado. Como entrada de un DCA es inútil: no se va a
# ejecutar nunca. Los candidatos fuera de este rango se descartan ANTES de
# agrupar, para que tampoco aporten peso a zonas intermedias.
DCA_DISTANCIA_MAX_ATR = 12.0      # rango en múltiplos de ATR(14)
DCA_DISTANCIA_MAX_ENTRADAS = 0.40 # techo absoluto: nada por debajo de un -40%
DCA_DISTANCIA_MAX_SALIDAS = 0.60  # techo absoluto: nada por encima de un +60%
# Suelos del rango, distintos por lado: en un valor tranquilo (KO, ATR 1,8%)
# 12xATR se quedaba en un +21% y dejaba fuera el propio valor objetivo, que
# estaba a +25%. Las salidas necesitan más recorrido que las entradas porque el
# objetivo de un plan es precisamente un precio que hoy no existe.
DCA_DISTANCIA_MIN_ENTRADAS = 0.25
DCA_DISTANCIA_MIN_SALIDAS = 0.35

# ------------------------------------------ separación mínima adaptativa ------
# `separacion = k * ATR(14) / precio`, acotada entre un suelo y un techo para
# que un ATR extremo no genere planes absurdos (niveles pegados o a un 40%).
DCA_SEPARACION_ATR_ENTRADAS = 2.5
DCA_SEPARACION_ATR_SALIDAS = 1.5
DCA_SEPARACION_MIN_ABS = 0.03     # suelo: nunca menos de un 3% entre niveles
DCA_SEPARACION_MAX_ABS = 0.20     # techo: nunca más de un 20%

# ------------------------------------------------- regla de excepción ---------
# Una zona que incumple la separación mínima puede colarse igualmente SOLO si
# se cumplen las DOS condiciones a la vez (nunca una sola), y siempre por
# encima de un suelo absoluto de distancia al precio actual.
DCA_EXCEPCION_RATIO_PESO = 1.40      # su peso debe superar en >=40% al de la zona rival
DCA_EXCEPCION_COBERTURA_MIN = 0.65   # y ya cubrir >=65% de la separación exigida
DCA_EXCEPCION_DISTANCIA_MIN = 0.015  # suelo absoluto de distancia al precio actual
# COBERTURA: bajada del 75% al 65% tras auditar GRAB, donde la zona de soporte
# más pesada de toda la tabla (peso 16,8, a -7,0%) quedaba fuera del plan por
# cubrir el 68,5% de la separación exigida. Es la constante más sensible del
# motor —afecta a todos los tickers, no solo al que motivó el cambio—, así que
# conviene revalidar con `calibracion_motor_dca.py` antes de volver a moverla.
# SUELO: bajado del 3% al 1,5%. El 3% original bloqueaba zonas de confluencia
# fuerte legítimamente pegadas al precio. No se elimina del todo porque la
# cobertura por sí sola no acota bien el caso extremo: con la separación en su
# mínimo (DCA_SEPARACION_MIN_ABS, 3%), una cobertura del 65% equivale a una
# distancia de apenas el 1,95%, y sin suelo nada impediría una "Entrada 1"
# prácticamente al precio de mercado si ese mínimo se recalibrara a la baja.

# --------------------------------------------------------- Volume Profile -----
# Dónde se ha negociado volumen de verdad, no solo por dónde pasó el precio.
# El volumen de cada sesión se reparte proporcionalmente entre las bandas que
# cruza su rango High-Low (no se asigna entero al cierre).
VP_SESIONES = 504                 # ~2 años de sesiones
VP_BANDAS = 60
VP_VALUE_AREA_PCT = 0.70          # % del volumen total que define la Value Area
VP_PESO_POC = 2.40                # Point of Control: el candidato de más peso
VP_PESO_VALUE_AREA = 1.30         # bordes VAH/VAL, como zona ancha

# ---------------------------------------------------- multi-temporalidad ------
# Un pivote que también existe en velas semanales es estructuralmente más
# fiable que uno que solo aparece en diario.
PIVOTE_VENTANA_SEMANAL = 4        # semanas a cada lado para el máximo/mínimo local
PIVOTE_PESO_SEMANAL = 1.80        # frente a 1,0-1,2 del pivote diario

# ------------------------------------------------ toques y antigüedad ---------
# Multiplicador NO lineal por número de toques confirmados (2 toques valen más
# que 1, pero 6 no valen seis veces) y decadencia por antigüedad del pivote.
PIVOTE_TOQUES_MULT = 0.35         # peso *= (1 + MULT * ln(toques))
PIVOTE_DECADENCIA_ANOS = 3.0      # antigüedad a la que se aplica el descuento pleno
PIVOTE_DECADENCIA_MIN = 0.60      # el peso nunca cae por debajo del 60% del original

# ----------------------------------------------- líneas de tendencia ----------
# Diagonales (canales) proyectadas a la fecha de hoy: un soporte horizontal de
# hace 8 meses vale poco si hay una diagonal bajista clara por encima.
DIAGONAL_MIN_TOQUES = 3           # una recta necesita 3 pivotes para ser válida
DIAGONAL_TOLERANCIA_ATR = 0.75    # holgura para considerar que un pivote "toca" la recta
DIAGONAL_SESIONES = 378           # ~18 meses: más atrás la diagonal deja de ser vigente
DIAGONAL_PESO = 1.60

# ------------------------------------------------- niveles psicológicos -------
NIVEL_REDONDO_PESO = 0.60         # peso bajo: sirve de desempate, no de argumento
NIVEL_REDONDO_MAX = 3             # nº de redondos a cada lado del precio

# ------------------------------------------ régimen de volatilidad ------------
# Percentil histórico del ATR relativo actual: con el ATR en máximos de 2 años
# el mercado está nervioso y TODOS los niveles son menos fiables; con el ATR en
# mínimos, los niveles se respetan mejor. Modula el peso global de la tabla.
ATR_PERCENTIL_VENTANA = 504
CONFIANZA_VOLATILIDAD_MIN = 0.85  # ATR en percentil 100 -> pesos x0,85
CONFIANZA_VOLATILIDAD_MAX = 1.15  # ATR en percentil 0   -> pesos x1,15

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

# El PER histórico propio no puede superar este múltiplo del PER sectorial
# de referencia. Antes el filtro era absoluto (0 < PER < 60), lo que dejaba
# pasar valores como un PER histórico de 44,1x en un sector con mediana
# ~24x. Relativo al sector, el techo se ajusta automáticamente a cada
# industria en vez de usar el mismo límite duro para todas.
PER_HIST_TECHO_VS_SECTOR = 1.3

# Peso del PER sectorial frente al histórico propio al combinarlos (el
# resto, 1 - este valor, va al histórico). El histórico es el que arrastra
# outliers de ejercicios puntuales; ponderar más el sectorial reduce esa
# distorsión sin descartar la referencia propia.
PESO_PER_SECTOR = 0.60
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

# Múltiplo EV/EBITDA por INDUSTRIA (más específico que el sector, usado con
# prioridad sobre él con fallback a EV_EBITDA_MEDIANO_SECTOR). Nace del caso
# Healthcare: un único múltiplo de 14x no distingue biotecnología en
# crecimiento (Biotechnology, ~40 años) de una aseguradora médica (Healthcare
# Plans, 7-9x reales) o una farmacéutica madura. Poblado solo donde la
# desviación observada en la calibración era material; el resto de
# industrias sigue cayendo al múltiplo de sector.
EV_EBITDA_MEDIANO_INDUSTRIA = {
    "Drug Manufacturers - General": 15.0,
    "Drug Manufacturers - Specialty & Generic": 10.0,
    "Healthcare Plans": 11.0,
    "Medical Devices": 17.0,
    "Medical Instruments & Supplies": 22.0,
    "Diagnostics & Research": 16.0,
    "Medical Distribution": 9.0,
    "Healthcare Providers & Services": 9.0,
    "Semiconductors": 18.0,
    "Semiconductor Equipment & Materials": 17.0,
    "Software - Infrastructure": 22.0,
    "Software - Application": 17.0,
    "Information Technology Services": 13.0,
    "Consumer Electronics": 18.0,
    "Computer Hardware": 14.0,
    "REIT - Specialty": 22.0,
    "REIT - Industrial": 21.0,
    "REIT - Retail": 17.0,
    "REIT - Residential": 20.0,
    "REIT - Healthcare Facilities": 18.0,
    "REIT - Office": 13.0,
    "Internet Content & Information": 14.0,
    "Telecom Services": 7.0,
    "Entertainment": 12.0,
    "Internet Retail": 16.0,
    "Auto Manufacturers": 8.0,
    "Home Improvement Retail": 14.0,
    "Beverages - Non-Alcoholic": 18.0,
    "Household & Personal Products": 15.0,
    "Discount Stores": 14.0,
    "Credit Services": 20.0,
    "Banks - Diversified": 11.0,
    "Railroads": 13.0,
    "Farm & Heavy Construction Machinery": 12.0,
    "Aerospace & Defense": 15.0,
    "Oil & Gas Integrated": 6.0,
    "Oil & Gas Equipment & Services": 7.0,
    "Specialty Chemicals": 14.0,
    "Steel": 7.0,
    "Utilities - Regulated Electric": 12.0,
}

# Industrias donde EV/EBITDA se EXCLUYE directamente (no se usa ni siquiera
# como fallback a sector). Caso Biotechnology: se probaron múltiplos de
# 20x y 32x y ninguno acercó NBIX al consenso -- el problema no es el
# múltiplo, es que el EBITDA de una biotech en rampa comercial (o aún sin
# ingresos de producto) no es una magnitud estable a la que aplicar un
# múltiplo sectorial.
EV_EBITDA_INDUSTRIAS_EXCLUIDAS = {"Biotechnology"}
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

# ---------------------------------------------------------------- cartera ----
# Divisa en la que se lleva el coste de las posiciones reales. El bróker
# (Trade Republic) liquida ya convertido a euros, así que el libro de
# operaciones guarda importes en EUR aunque el valor cotice en otra divisa;
# `core/cartera.py::precio_en_eur()` convierte la cotización para poder
# compararla con ese coste.
CARTERA_DIVISA_BASE = "EUR"

# Divisas de cotización que la app sabe convertir a la divisa base. Cualquier
# otra hace que el valor de mercado se reporte como "dato no disponible" en
# vez de mezclarse sin convertir (regla de oro: nunca inventar un dato).
CARTERA_DIVISAS_CONVERTIBLES = ("EUR", "USD")

# Umbral por debajo del cual un número de acciones se considera cero. Existe
# porque el saldo se obtiene sumando y restando flotantes: tras vender toda
# la posición puede quedar un residuo de 1e-14 acciones que, sin esta
# tolerancia, dejaría la posición eternamente "abierta".
CARTERA_TOLERANCIA_ACCIONES = 1e-6

# ------------------------------------------------------------ paper trading --
# Máquina de estados de una posición simulada. `derivar_estado()` en
# core/paper_trading.py calcula la clave a partir del libro de ejecuciones;
# aquí solo vive la etiqueta visible y el color de cada una. `descartada` es
# la única que no se deriva (acción manual desde 'vigilancia').
PAPER_ESTADOS = {
    "vigilancia":      ("Vigilando", C_AMBAR),
    "parcial_entrada": ("Abierto, en marcha", C_TEAL),
    "abierta":         ("Abierto, completado", C_VERDE),
    "parcial_salida":  ("Cerrado parcialmente", C_AZUL),
    "cerrada":         ("Cerrado, completado", C_PRIMARIO),
    "descartada":      ("Descartado", C_TEXTO_TENUE),
}

# Agrupación para las pestañas de la vista: activo = todavía puede moverse
# (incluye tanto "esperando entrar" como "vendiendo por partes"); terminal =
# ya no cambia salvo que se borre.
PAPER_ESTADOS_ACTIVOS = ("vigilancia", "parcial_entrada", "abierta", "parcial_salida")
PAPER_ESTADOS_CERRADOS = ("cerrada",)
PAPER_ESTADOS_DESCARTADOS = ("descartada",)

# ------------------------------------------------------------------ caché ----
TTL_PRECIO = 300        # 5 min — fast_info en vivo (obtener_precio_actual). No
# lleva cubo de calendario: es la única pieza que de verdad necesita
# frescura de minutos mientras el mercado respira, y es una llamada ligera
# (no las ~1.250 velas del histórico), así que no es donde está el gasto.
# El ETF sectorial/de mercado de referencia (fuerza relativa del timing) no
# necesita la frescura de un precio en vivo: alimenta un diferencial de
# rentabilidad a 63 SESIONES, así que una actualización diaria sobra de
# sobra. Con TTL_PRECIO (5 min) cada análisis fuera de esa ventana repetía
# la petición a Yahoo sin necesidad, en un endpoint ya sensible al límite
# por IP compartida de Streamlit Community Cloud. 12 h cubre una sesión de
# trabajo completa sin arrastrar datos de más de un día hábil de retraso.
TTL_REFERENCIA_MERCADO = 43200  # 12 h
# `obtener_historico()` ya NO usa este número como TTL real: usa un cubo de
# calendario de mercado (ver `_cubo_mercado()` en datos_api.py) que congela
# la caché entera mientras el mercado está cerrado y solo la revalida una
# vez por hora en sesión. Este valor queda como techo de seguridad (red de
# respaldo si el cubo fallara), no como el mecanismo real de invalidación.
TTL_HISTORICO_RESPALDO = 21600  # 6 h, solo como cinturón de seguridad
TTL_FUNDAMENTALES = 3600  # 1 h — consenso, estimaciones, precio objetivo:
# datos que sí pueden moverse a lo largo del día.
# Los estados financieros (cuenta de resultados, balance, flujo de caja)
# solo se actualizan 4 veces al año, en la publicación de resultados.
# Compartir TTL_FUNDAMENTALES (1 h) con ellos repetía la misma petición
# varias veces al día sin ninguna necesidad real. La caché en memoria usa
# este TTL (L1); además se respalda en Supabase (L2, ver bd_supabase.py)
# con este mismo horizonte para sobrevivir al reinicio del contenedor de
# Streamlit Community Cloud tras un periodo de inactividad.
TTL_ESTADOS_FINANCIEROS = 172800  # 48 h
TTL_NOTICIAS = 900      # 15 min
TTL_FX = 600            # 10 min

# `obtener_info()` (los fundamentales de yfinance) es la pieza más frágil de
# todo el sistema: es la primera petición de cualquier análisis y la que
# antes topa con el límite por IP de Yahoo. Cuando Streamlit Community Cloud
# redespliega o reinicia el contenedor, L1 se vacía y el primer análisis
# tenía que pedirla a pelo — de ahí el clásico "tras un redespliegue no
# carga, y al rato ya va". Con respaldo en L2 (Supabase) ese primer análisis
# se sirve de la base de datos. El TTL es largo a propósito: lo que se
# reutiliza de L2 son los fundamentales (que cambian con los resultados
# trimestrales), NO el precio — los campos de precio se descartan al leer de
# L2 (ver `_info_sin_precio()` en datos_api.py) para que la cotización venga
# siempre del histórico, que sí se revalida con el calendario de mercado.
TTL_INFO_L2 = 43200  # 12 h

# ------------------------------------------------------- calendario de mercado
# Usado por `_cubo_mercado()` en datos_api.py para no gastar peticiones de
# histórico cuando el mercado está cerrado (fin de semana, fuera de horario):
# mientras esté cerrado, el "cubo" no cambia y la caché no se revalida.
MERCADO_ZONA_HORARIA = "America/New_York"
MERCADO_HORA_APERTURA = (9, 30)   # 9:30 ET
MERCADO_HORA_CIERRE = (16, 0)     # 16:00 ET
# Festivos NYSE no contemplados en esta primera versión: un festivo entre
# semana se trata como sesión normal (gasta, como mucho, una petición de
# histórico de más ese día). Añadir una lista estática si compensa.
