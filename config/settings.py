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

# -------------------------------------------- histórico de resultados ----
# Nº de trimestres del histórico de resultados (racha de sorpresas de BPA).
# Cuatro cubre un año completo, el mínimo para que el efecto estacional del
# propio negocio no distorsione la lectura.
TRIMESTRES_EVOLUCION = 4
# Alto de los minigráficos de barras horizontales del Bloque 2.
# Deliberadamente pequeños: son gráficos de contexto en una columna
# estrecha, no protagonistas.
GRAFICO_BARRAS_ALTO = 130
GRAFICO_PER_ALTO = 150

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
# Motor de valor objetivo: cuatro métodos de una sola multiplicación (cero
# DCF) más el consenso de analistas con peso FIJO.
#
# Dos cambios estructurales respecto al motor anterior:
#
# 1) Fuera el DCF. En la calibración sobre 29 tickers multisector fue, con
#    diferencia, el método más alejado del consenso (mediana de desviación
#    ~50-60% frente a ~25-35% del resto), y no mejoró al corregir su
#    metodología (FCFF, WACC ponderado real, deuda contada una sola vez):
#    el problema no era un bug sino la naturaleza del método, que topa el
#    múltiplo de salida muy por debajo de lo que paga el mercado en
#    sectores de crecimiento. `valorar_dcf()` sigue en el módulo pero ya no
#    lo llama nadie (ver ESTADO_PROYECTO.md).
#
# 2) Peso FIJO del consenso, sin duplicación. Antes el consenso podía
#    llegar al 68% del peso efectivo (0,34 x2 con >=10 analistas) siendo a
#    la vez el ancla de la banda de cordura: se vigilaba a sí mismo. Ahora
#    pesa un 20% constante y el ancla es mixta (mediana de los 4 métodos
#    propios junto al consenso), rompiendo la circularidad.
PESOS_FAIR_VALUE = {
    "per_ttm": 0.20,      # A. PER histórico propio x BPA TTM
    "per_forward": 0.25,  # B. PER razonable x BPA forward
    "peg": 0.20,          # C. PEG (reutilizado sin cambios)
    "ev_ebitda": 0.15,    # D. EV/EBITDA por industria (reutilizado sin cambios)
    "consenso": 0.20,     # Precio objetivo medio de analistas
}

# Filtro de estabilidad del PER histórico propio (método B). Si el ejercicio
# más caro de la serie de 5 años supera al más barato en más de este factor,
# la empresa no tiene un "PER propio" fiable -- tiene una serie inestable
# (rampa de crecimiento, o un cargo puntual que casi anula el BPA de un
# ejercicio) -- y el método cae al PER forward mediano del sector. Calibrado
# en 2,0x: NBIX pasaba el filtro con un PER histórico que sobrestimaba el
# valor un +221%, y con este umbral cae correctamente al sectorial.
UMBRAL_ESTABILIDAD_PER_HISTORICO = 2.0

# Cuánto tiene que desviarse el PER actual de una referencia (sector o
# histórico propio) para llamarlo "caro" o "barato" en vez de "en línea".
# 1,15 = 15% de margen a cada lado: por debajo de esa diferencia el ruido
# de las medianas sectoriales heurísticas no permite afirmar nada.
UMBRAL_PER_CARA_BARATA = 1.15

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

# Margen bruto por sector.
MARGEN_BRUTO_MEDIANO_SECTOR = {
    "Basic Materials": 0.3737,
    "Communication Services": 0.5058,
    "Consumer Cyclical": 0.3791,
    "Consumer Defensive": 0.3554,
    "Energy": 0.3142,
    "Financial Services": 0.7719,
    "Healthcare": 0.5458,
    "Industrials": 0.3201,
    "Real Estate": 0.573,
    "Technology": 0.5488,
    "Utilities": 0.4713,
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

# ------------------------------------------------------------- 52 semanas -----
# Antes hardcodeados inline (1,50 / 2,00), sin justificación explícita para la
# asimetría entre ambos. Igualados a 2,20: validado con `calibracion_pesos_52s.py`
# sobre 16 tickers — el lado soporte gana selecciones sin ninguna regresión, y
# el lado resistencia queda sin cambios frente a 2,00 (los pivotes semanales
# con 2+ toques ya lo superaban en ambos casos). Sin razón de fondo para que el
# máximo pese más: si acaso, el mínimo de 52s (capitulación) es una lectura más
# fiable que el máximo (que en momentum suele seguir rompiendo al alza).
PESO_MIN_52S = 2.20
PESO_MAX_52S = 2.20

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
# PER (agregado, solo empresas con beneficio) por sector.
PER_MEDIANO_SECTOR = {
    "Basic Materials": 23.3,
    "Communication Services": 25.8,
    "Consumer Cyclical": 26.9,
    "Consumer Defensive": 19.7,
    "Energy": 18.9,
    "Financial Services": 18.0,
    "Healthcare": 28.7,
    "Industrials": 26.8,
    "Real Estate": 28.5,
    "Technology": 36.8,
    "Utilities": 21.3,
}

# HUÉRFANAS A PROPÓSITO: las dos constantes de abajo alimentaban a
# `valorar_multiplos()`, que mezclaba PER sectorial e histórico en una media
# ponderada y fue sustituida por los métodos A y B del motor nuevo (que los
# usan por separado: el histórico tal cual en A, y en B con un filtro de
# ESTABILIDAD -- `UMBRAL_ESTABILIDAD_PER_HISTORICO` -- en vez de un techo
# relativo). Se conservan documentadas por si se reevalúa ese enfoque.
PER_HIST_TECHO_VS_SECTOR = 1.3
PESO_PER_SECTOR = 0.60
# Margen neto por sector.
MARGEN_NETO_MEDIANO_SECTOR = {
    "Basic Materials": 0.1322,
    "Communication Services": 0.1033,
    "Consumer Cyclical": 0.0557,
    "Consumer Defensive": 0.0657,
    "Energy": 0.0798,
    "Financial Services": 0.221,
    "Healthcare": 0.0685,
    "Industrials": 0.075,
    "Real Estate": 0.1301,
    "Technology": 0.1846,
    "Utilities": 0.1124,
}

# ROE por sector.
ROE_MEDIANO_SECTOR = {
    "Basic Materials": 0.1503,
    "Communication Services": 0.1322,
    "Consumer Cyclical": 0.206,
    "Consumer Defensive": 0.1481,
    "Energy": 0.1133,
    "Financial Services": 0.1678,
    "Healthcare": 0.1031,
    "Industrials": 0.1731,
    "Real Estate": 0.0504,
    "Technology": 0.2341,
    "Utilities": 0.089,
}

# ---------------------------------------------------------------------------
# TABLAS DE SECTOR -- agregadas desde Damodaran (edición 2026-01-05, EE.UU.) por
# `generar_tablas_damodaran.py` + `construir_tablas_nuevas()`: media ponderada
# por nº de empresas de cada industria Damodaran que cae en el sector, según
# el mapeo oficial de yfinance (`yfinance.const.SECTOR_INDUSTY_MAPPING`, con su
# separador em-dash normalizado -- sin normalizar, esta tabla sale vacía o
# gravemente sesgada en silencio; ver ESTADO_PROYECTO.md).
#
# Sustituyen a las heurísticas anteriores (11 valores estimados a ojo cada
# una). Regenerar con `generar_tablas_damodaran.py` cuando Damodaran publique
# una edición nueva.

# PER forward por sector.
FORWARD_PER_MEDIANO_SECTOR = {
    "Basic Materials": 22.9,
    "Communication Services": 35.2,
    "Consumer Cyclical": 24.3,
    "Consumer Defensive": 17.7,
    "Energy": 22.6,
    "Financial Services": 14.8,
    "Healthcare": 44.0,
    "Industrials": 25.8,
    "Real Estate": 46.2,
    "Technology": 35.7,
    "Utilities": 21.4,
}

# HUÉRFANA A PROPÓSITO: no la usa ningún método de `core/valoracion.py`
# (verificado por grep -- no aparece en ninguna llamada de `valorar_*` ni en
# `puntuar_calidad`). Se conserva sin actualizar porque actualizar un valor
# que no se lee en ningún sitio no tiene efecto ni sentido. Candidata a
# eliminar en una limpieza futura si se confirma que sigue sin uso.
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

# EV/EBITDA (solo empresas con EBITDA positivo) por sector.
EV_EBITDA_MEDIANO_SECTOR = {
    "Basic Materials": 11.1,
    "Communication Services": 17.0,
    "Consumer Cyclical": 13.9,
    "Consumer Defensive": 12.0,
    "Energy": 8.2,
    "Financial Services": 40.9,
    "Healthcare": 16.7,
    "Industrials": 15.7,
    "Real Estate": 19.8,
    "Technology": 23.0,
    "Utilities": 13.2,
}

# Industria de yfinance -> industria de Damodaran (edicion 2026-01-05). Escrito
# a mano y verificado con generar_tablas_damodaran.py: el emparejamiento
# difuso por nombre falla en silencio (ej. "Utilities - Regulated Electric" ->
# "Coal & Related Energy"). None = sin equivalente defendible; `ponderar()`
# redistribuye el peso del método afectado en vez de forzar una referencia.
#
# Regenerar con generar_tablas_damodaran.py cuando Damodaran publique una
# edición nueva (~enero de cada año). Las entradas marcadas RESUELTO tienen
# más de una traducción defendible; se decidió tras medir la sensibilidad
# real sobre la cesta de 29 tickers (ver ESTADO_PROYECTO.md).
INDUSTRIA_YF_A_DAMODARAN = {
    "Advertising Agencies": "Advertising",
    "Aerospace & Defense": "Aerospace/Defense",
    "Agricultural Inputs": "Chemical (Basic)",
    "Airlines": "Air Transport",
    "Airports & Air Services": "Transportation",
    "Aluminum": "Metals & Mining",
    "Apparel Manufacturing": "Apparel",
    "Apparel Retail": "Retail (Special Lines)",
    "Asset Management": "Investments & Asset Management",
    "Auto & Truck Dealerships": "Retail (Automotive)",
    "Auto Manufacturers": "Auto & Truck",
    "Auto Parts": "Auto Parts",
    "Banks - Diversified": "Bank (Money Center)",
    "Banks - Regional": "Banks (Regional)",
    "Beverages - Brewers": "Beverage (Alcoholic)",
    "Beverages - Non-Alcoholic": "Beverage (Soft)",
    "Beverages - Wineries & Distilleries": "Beverage (Alcoholic)",
    "Biotechnology": "Drugs (Biotechnology)",
    "Broadcasting": "Broadcasting",
    "Building Materials": "Building Materials",
    "Building Products & Equipment": "Construction Supplies",
    "Business Equipment & Supplies": "Office Equipment & Services",
    "Capital Markets": "Brokerage & Investment Banking",
    "Chemicals": "Chemical (Diversified)",
    "Coking Coal": "Coal & Related Energy",
    "Communication Equipment": "Telecom. Equipment",
    "Computer Hardware": "Computers/Peripherals",
    "Confectioners": "Food Processing",
    "Conglomerates": "Diversified",
    "Consulting Services": "Business & Consumer Services",
    "Consumer Electronics": "Electronics (Consumer & Office)",
    "Copper": "Metals & Mining",
    "Credit Services": "Financial Svcs. (Non-bank & Insurance)",
    "Department Stores": "Retail (General)",
    "Diagnostics & Research": "Healthcare Products",
    "Discount Stores": "Retail (General)",
    "Drug Manufacturers - General": "Drugs (Pharmaceutical)",
    "Drug Manufacturers - Specialty & Generic": "Drugs (Pharmaceutical)",
    "Education & Training Services": "Education",
    "Electrical Equipment & Parts": "Electrical Equipment",
    "Electronic Components": "Electronics (General)",
    "Electronic Gaming & Multimedia": "Software (Entertainment)",
    "Electronics & Computer Distribution": "Retail (Distributors)",
    "Engineering & Construction": "Engineering/Construction",
    "Entertainment": "Entertainment",
    "Farm & Heavy Construction Machinery": "Machinery",
    "Farm Products": "Farming/Agriculture",
    "Financial Conglomerates": "Diversified",
    "Financial Data & Stock Exchanges": "Information Services",
    "Food Distribution": "Food Wholesalers",
    "Footwear & Accessories": "Shoe",
    "Furnishings, Fixtures & Appliances": "Furn/Home Furnishings",
    "Gambling": "Hotel/Gaming",
    "Gold": "Precious Metals",
    "Grocery Stores": "Retail (Grocery and Food)",
    "Health Information Services": "Heathcare Information and Technology",
    "Healthcare Plans": "Healthcare Support Services",
    "Healthcare Providers & Services": "Healthcare Support Services",
    "Home Improvement Retail": "Retail (Building Supply)",
    "Household & Personal Products": "Household Products",
    "Industrial Distribution": "Retail (Distributors)",
    "Information Technology Services": "Computer Services",
    "Infrastructure Operations": "Engineering/Construction",
    "Insurance - Diversified": "Insurance (General)",
    "Insurance - Life": "Insurance (Life)",
    "Insurance - Property & Casualty": "Insurance (Prop/Cas.)",
    "Insurance - Reinsurance": "Reinsurance",
    "Insurance - Specialty": "Insurance (General)",
    "Insurance Brokers": "Insurance (General)",
    "Integrated Freight & Logistics": "Transportation",
    "Internet Content & Information": "Software (Internet)",
    "Internet Retail": "Retail (General)",
    "Leisure": "Recreation",
    "Lodging": "Hotel/Gaming",
    "Lumber & Wood Production": "Paper/Forest Products",
    "Luxury Goods": "Retail (Special Lines)",
    "Marine Shipping": "Shipbuilding & Marine",
    "Medical Care Facilities": "Hospitals/Healthcare Facilities",
    "Medical Devices": "Healthcare Products",
    "Medical Distribution": "Healthcare Support Services",
    "Medical Instruments & Supplies": "Healthcare Products",
    "Metal Fabrication": "Machinery",
    "Mortgage Finance": "Financial Svcs. (Non-bank & Insurance)",
    "Oil & Gas Drilling": "Oilfield Svcs/Equip.",
    "Oil & Gas E&P": "Oil/Gas (Production and Exploration)",
    "Oil & Gas Equipment & Services": "Oilfield Svcs/Equip.",
    "Oil & Gas Integrated": "Oil/Gas (Integrated)",
    "Oil & Gas Midstream": "Oil/Gas Distribution",
    "Oil & Gas Refining & Marketing": "Oil/Gas (Integrated)",
    "Other Industrial Metals & Mining": "Metals & Mining",
    "Other Precious Metals & Mining": "Precious Metals",
    "Packaged Foods": "Food Processing",
    "Packaging & Containers": "Packaging & Container",
    "Paper & Paper Products": "Paper/Forest Products",
    "Personal Services": "Business & Consumer Services",
    "Pharmaceutical Retailers": "Retail (General)",
    "Pollution & Treatment Controls": "Environmental & Waste Services",
    "Publishing": "Publishing & Newspapers",
    "REIT - Diversified": "R.E.I.T.",
    "REIT - Healthcare Facilities": "R.E.I.T.",
    "REIT - Hotel & Motel": "R.E.I.T.",
    "REIT - Industrial": "R.E.I.T.",
    "REIT - Mortgage": "R.E.I.T.",
    "REIT - Office": "R.E.I.T.",
    "REIT - Residential": "R.E.I.T.",
    "REIT - Retail": "Retail (REITs)",
    "REIT - Specialty": "R.E.I.T.",
    "Railroads": "Transportation (Railroads)",
    "Real Estate - Development": "Real Estate (Development)",
    "Real Estate - Diversified": "Real Estate (General/Diversified)",
    "Real Estate Services": "Real Estate (Operations & Services)",
    "Recreational Vehicles": "Recreation",
    "Rental & Leasing Services": "Business & Consumer Services",
    "Residential Construction": "Homebuilding",
    "Resorts & Casinos": "Hotel/Gaming",
    "Restaurants": "Restaurant/Dining",
    "Scientific & Technical Instruments": "Electronics (General)",
    "Security & Protection Services": "Business & Consumer Services",
    "Semiconductor Equipment & Materials": "Semiconductor Equip",
    "Semiconductors": "Semiconductor",
    "Shell Companies": None,
    "Silver": "Precious Metals",
    "Software - Application": "Software (System & Application)",
    "Software - Infrastructure": "Software (System & Application)",
    "Solar": "Green & Renewable Energy",
    "Specialty Business Services": "Business & Consumer Services",
    "Specialty Chemicals": "Chemical (Specialty)",
    "Specialty Industrial Machinery": "Machinery",
    "Specialty Retail": "Retail (Special Lines)",
    "Staffing & Employment Services": "Business & Consumer Services",
    "Steel": "Steel",
    "Telecom Services": "Telecom. Services",
    "Textile Manufacturing": "Apparel",
    "Thermal Coal": "Coal & Related Energy",
    "Tobacco": "Tobacco",
    "Tools & Accessories": "Machinery",
    "Travel Services": "Business & Consumer Services",
    "Trucking": "Trucking",
    "Uranium": "Metals & Mining",
    "Utilities - Diversified": "Utility (General)",
    "Utilities - Independent Power Producers": "Power",
    "Utilities - Regulated Electric": "Utility (General)",
    "Utilities - Regulated Gas": "Utility (General)",
    "Utilities - Regulated Water": "Utility (Water)",
    "Utilities - Renewable": "Green & Renewable Energy",
    "Waste Management": "Environmental & Waste Services",
}

# Industrias Damodaran (edición 2026-01-05) sin PER de referencia fiable: muestra
# pequeña (n<10), exceso de empresas en pérdidas (>75%), o contradicción entre
# el PER forward y el PER agregado (>50% de divergencia). Usado por el método B
# del motor de valor objetivo: si el PER histórico propio es inestable Y la
# industria de referencia está aquí, el método se EXCLUYE en vez de usar un
# múltiplo que la propia generación de tablas ya marcó como dudoso.
PER_INDUSTRIAS_SIN_REFERENCIA_FIABLE = {
    "Advertising": "perdidas=79%, fwd/agg=2.07",
    "Auto & Truck": "perdidas=82%, fwd/agg=0.41",
    "Cable TV": "n=9, fwd/agg=1.82",
    "Chemical (Basic)": "perdidas=76%",
    "Chemical (Diversified)": "n=4, perdidas=100%",
    "Coal & Related Energy": "perdidas=81%, fwd/agg=1.74",
    "Computer Services": "fwd/agg=2.17",
    "Diversified": "perdidas=80%",
    "Drugs (Biotechnology)": "perdidas=90%, fwd/agg=1.99",
    "Drugs (Pharmaceutical)": "perdidas=85%",
    "Electronics (Consumer & Office)": "n=8, perdidas=100%",
    "Entertainment": "perdidas=83%",
    "Environmental & Waste Services": "perdidas=79%, fwd/agg=1.78",
    "Green & Renewable Energy": "perdidas=87%, fwd/agg=1.65",
    "Healthcare Products": "perdidas=76%",
    "Healthcare Support Services": "fwd/agg=2.62",
    "Heathcare Information and Technology": "perdidas=77%",
    "Metals & Mining": "perdidas=85%",
    "Oil/Gas (Integrated)": "n=4",
    "Oil/Gas Distribution": "fwd/agg=2.29",
    "Paper/Forest Products": "n=6",
    "Precious Metals": "perdidas=86%",
    "R.E.I.T.": "fwd/agg=1.61",
    "Real Estate (Development)": "perdidas=79%",
    "Real Estate (Operations & Services)": "fwd/agg=2.13",
    "Recreation": "fwd/agg=2.09",
    "Reinsurance": "n=1",
    "Retail (Distributors)": "fwd/agg=1.95",
    "Rubber& Tires": "n=3, perdidas=100%",
    "Shipbuilding & Marine": "n=8",
    "Software (Internet)": "fwd/agg=1.86",
    "Telecom (Wireless)": "fwd/agg=1.83",
    "Telecom. Services": "perdidas=79%, fwd/agg=3.30",
    "Transportation (Railroads)": "n=4",
}

# Industrias Damodaran (edición 2026-01-05) sin EV/EBITDA de referencia fiable:
# muestra pequeña (n<10), o divergencia >50% entre el múltiplo de "solo
# empresas con EBITDA positivo" y el de "todas las empresas" (indica que la
# muestra positiva ya no representa a la industria real). Diagnóstico propio,
# independiente del de PER: las señales de contaminación son distintas.
# Usado por el método D: si la industria de referencia está aquí, se excluye
# en vez de usar el múltiplo (sin caer a sector: la industria SÍ tenía
# múltiplo, es que no es de fiar).
EV_EBITDA_INDUSTRIAS_SIN_REFERENCIA_FIABLE = {
    "Aerospace/Defense": "todas/positivas=1.55",
    "Cable TV": "n=9",
    "Chemical (Diversified)": "n=4",
    "Coal & Related Energy": "todas/positivas=1.88",
    "Drugs (Biotechnology)": "todas/positivas=3.26",
    "Electronics (Consumer & Office)": "n=8",
    "Financial Svcs. (Non-bank & Insurance)": "todas/positivas=1.56",
    "Oil/Gas (Integrated)": "n=4",
    "Paper/Forest Products": "n=6",
    "Precious Metals": "todas/positivas=1.62",
    "Real Estate (Operations & Services)": "todas/positivas=1.68",
    "Reinsurance": "n=1",
    "Rubber& Tires": "n=3",
    "Shipbuilding & Marine": "n=8",
    "Software (Internet)": "todas/positivas=3.32",
    "Transportation (Railroads)": "n=4",
}

# Industrias REIT: el BPA GAAP no es una magnitud económica válida para este tipo
# de negocio (la amortización del inmueble se come el beneficio contable sin
# reflejar la realidad económica; el estándar del sector es FFO/AFFO, no BPA).
# Los métodos A, B y C dependen todos de BPA y se EXCLUYEN para estas
# industrias en `calcular_fair_value` -- el fair value de un REIT se apoya
# solo en D (EV/EBITDA, no distorsionado por amortización) y en el consenso.
# Corrección PARCIAL y deliberadamente conservadora mientras no se implemente
# el método P/FFO completo (ver ESTADO_PROYECTO.md, mejora pendiente).
INDUSTRIAS_REIT = {
    "REIT - Diversified",
    "REIT - Healthcare Facilities",
    "REIT - Hotel & Motel",
    "REIT - Industrial",
    "REIT - Mortgage",
    "REIT - Office",
    "REIT - Residential",
    "REIT - Retail",
    "REIT - Specialty",
}

# EV/EBITDA por industria -- Damodaran edición 2026-01-05, vía
# INDUSTRIA_YF_A_DAMODARAN, con OVERRIDES_INDUSTRIA_EV_EBITDA aplicado encima.
EV_EBITDA_INDUSTRIA_DAMODARAN = {
    "Advertising Agencies": 12.0,
    "Aerospace & Defense": 21.6,
    "Agricultural Inputs": 8.6,
    "Airlines": 7.6,
    "Airports & Air Services": 12.5,
    "Aluminum": 11.4,
    "Apparel Manufacturing": 10.3,
    "Apparel Retail": 11.5,
    "Asset Management": 38.0,
    "Auto & Truck Dealerships": 14.8,
    "Auto Manufacturers": 47.8,
    "Auto Parts": 6.4,
    "Beverages - Brewers": 8.6,
    "Beverages - Non-Alcoholic": 16.9,
    "Beverages - Wineries & Distilleries": 8.6,
    "Biotechnology": 15.8,
    "Broadcasting": 7.8,
    "Building Materials": 11.6,
    "Building Products & Equipment": 16.8,
    "Business Equipment & Supplies": 8.6,
    "Chemicals": 8.4,
    "Coking Coal": 10.4,
    "Communication Equipment": 24.1,
    "Computer Hardware": 25.4,
    "Confectioners": 10.0,
    "Conglomerates": 11.4,
    "Consulting Services": 14.3,
    "Consumer Electronics": 30.7,
    "Copper": 11.4,
    "Credit Services": 57.5,
    "Department Stores": 17.4,
    "Diagnostics & Research": 19.8,
    "Discount Stores": 17.4,
    "Drug Manufacturers - General": 15.2,
    "Drug Manufacturers - Specialty & Generic": 15.2,
    "Education & Training Services": 9.3,
    "Electrical Equipment & Parts": 24.6,
    "Electronic Components": 20.0,
    "Electronic Gaming & Multimedia": 22.0,
    "Electronics & Computer Distribution": 13.7,
    "Engineering & Construction": 17.2,
    "Entertainment": 19.4,
    "Farm & Heavy Construction Machinery": 16.2,
    "Farm Products": 16.0,
    "Financial Conglomerates": 11.4,
    "Financial Data & Stock Exchanges": 11.5,
    "Food Distribution": 11.1,
    "Footwear & Accessories": 16.9,
    "Furnishings, Fixtures & Appliances": 11.3,
    "Gambling": 14.9,
    "Gold": 10.7,
    "Grocery Stores": 8.9,
    "Health Information Services": 21.3,
    "Healthcare Plans": 11.2,
    "Healthcare Providers & Services": 11.2,
    "Home Improvement Retail": 14.4,
    "Household & Personal Products": 13.2,
    "Industrial Distribution": 13.7,
    "Information Technology Services": 14.1,
    "Infrastructure Operations": 17.2,
    "Insurance - Diversified": 15.8,
    "Insurance - Life": 12.5,
    "Insurance - Property & Casualty": 8.4,
    "Insurance - Reinsurance": 8.7,
    "Insurance - Specialty": 15.8,
    "Insurance Brokers": 15.8,
    "Integrated Freight & Logistics": 12.5,
    "Internet Content & Information": 30.3,
    "Internet Retail": 17.4,
    "Leisure": 10.4,
    "Lodging": 14.9,
    "Lumber & Wood Production": 8.2,
    "Luxury Goods": 11.5,
    "Marine Shipping": 8.0,
    "Medical Care Facilities": 8.9,
    "Medical Devices": 19.8,
    "Medical Distribution": 11.2,
    "Medical Instruments & Supplies": 19.8,
    "Metal Fabrication": 16.2,
    "Mortgage Finance": 57.5,
    "Oil & Gas Drilling": 8.6,
    "Oil & Gas E&P": 5.1,
    "Oil & Gas Equipment & Services": 8.6,
    "Oil & Gas Integrated": 8.2,
    "Oil & Gas Midstream": 11.6,
    "Oil & Gas Refining & Marketing": 8.2,
    "Other Industrial Metals & Mining": 11.4,
    "Other Precious Metals & Mining": 10.7,
    "Packaged Foods": 10.0,
    "Packaging & Containers": 9.7,
    "Paper & Paper Products": 8.2,
    "Personal Services": 14.3,
    "Pharmaceutical Retailers": 17.4,
    "Pollution & Treatment Controls": 15.6,
    "Publishing": 11.2,
    "REIT - Diversified": 19.9,
    "REIT - Healthcare Facilities": 19.9,
    "REIT - Hotel & Motel": 19.9,
    "REIT - Industrial": 19.9,
    "REIT - Mortgage": 19.9,
    "REIT - Office": 19.9,
    "REIT - Residential": 19.9,
    "REIT - Retail": 16.7,
    "REIT - Specialty": 19.9,
    "Railroads": 13.5,
    "Real Estate - Development": 10.2,
    "Real Estate - Diversified": 17.3,
    "Real Estate Services": 22.0,
    "Recreational Vehicles": 10.4,
    "Rental & Leasing Services": 14.3,
    "Residential Construction": 8.9,
    "Resorts & Casinos": 14.9,
    "Restaurants": 17.5,
    "Scientific & Technical Instruments": 20.0,
    "Security & Protection Services": 14.3,
    "Semiconductor Equipment & Materials": 24.7,
    "Semiconductors": 34.8,
    "Silver": 10.7,
    "Software - Application": 24.5,
    "Software - Infrastructure": 24.5,
    "Solar": 13.4,
    "Specialty Business Services": 14.3,
    "Specialty Chemicals": 13.4,
    "Specialty Industrial Machinery": 16.2,
    "Specialty Retail": 11.5,
    "Staffing & Employment Services": 14.3,
    "Steel": 11.6,
    "Telecom Services": 6.5,
    "Textile Manufacturing": 10.3,
    "Thermal Coal": 10.4,
    "Tobacco": 13.5,
    "Tools & Accessories": 16.2,
    "Travel Services": 14.3,
    "Trucking": 10.4,
    "Uranium": 11.4,
    "Utilities - Diversified": 13.7,
    "Utilities - Independent Power Producers": 12.4,
    "Utilities - Regulated Electric": 13.7,
    "Utilities - Regulated Gas": 13.7,
    "Utilities - Regulated Water": 14.1,
    "Utilities - Renewable": 13.4,
    "Waste Management": 15.6,
}

# Ajustes manuales YA EXISTENTES antes de esta migración, preservados a
# propósito en vez de sobrescritos por el dato agregado de Damodaran (que da
# 21.6x, 34.8x y 11.6x respectivamente para estas tres). No se conoce con
# certeza la razón original de cada ajuste -- se preservan por precaución, no
# porque se haya reverificado el motivo. PENDIENTE: ejecutar el contraste
# completo (`generar_tablas_damodaran.py` con TABLAS_ACTUALES) sobre las 139
# industrias restantes para detectar si hay más overrides deliberados que
# esta migración haya pisado sin darse cuenta (ver ESTADO_PROYECTO.md).
OVERRIDES_INDUSTRIA_EV_EBITDA = {
    "Aerospace & Defense": 15.0,
    "Semiconductors": 18.0,
    "Steel": 7.0,
}

EV_EBITDA_MEDIANO_INDUSTRIA = {**EV_EBITDA_INDUSTRIA_DAMODARAN, **OVERRIDES_INDUSTRIA_EV_EBITDA}

EV_EBITDA_INDUSTRIAS_EXCLUIDAS = {
    # -- exclusión por RUIDO DE DATO en la industria (EBITDA no es magnitud
    #    estable a la que aplicar un múltiplo, motivo original) --
    "Biotechnology",
    "Shell Companies",
    "Mortgage Finance",
    "Financial Conglomerates",
    "Capital Markets",
    "REIT - Mortgage",
    # -- exclusión por AMBIGÜEDAD DE MAPEO (motivo distinto, añadido tras la
    #    calibración de enero 2026): dos categorías Damodaran igual de
    #    defendibles divergen >70% en el múltiplo, sin forma no arbitraria de
    #    elegir una. Probado con dato real sobre MELI (Internet Retail):
    #    1.187$ vs 2.176$ de fair value hipotético según la categoría elegida,
    #    cotizando a 1.963$ -- la elección sola decide si sale barata o cara.
    "Internet Retail",
    "Insurance Brokers",
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
