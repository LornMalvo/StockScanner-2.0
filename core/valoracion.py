"""Bloque 4: valor objetivo justo y puntuación de calidad fundamental.

Cada método de valoración devuelve `(valor, detalle)` donde `valor` puede ser
None. El combinador `calcular_fair_value` redistribuye los pesos de los métodos
que no han podido calcularse: jamás se introduce un 0 en la media.
"""

from __future__ import annotations

import statistics

import pandas as pd

from config.settings import (
    BANDA_MIN_ANALISTAS,
    BANDA_SUELO,
    BANDA_TECHO,
    BANDAS_VALORACION,
    BLOQUES_CALIDAD,
    DCF_ANIOS,
    DCF_ANOMALIA_FCF,
    DCF_CRECIMIENTO_MAX,
    DCF_CRECIMIENTO_MAX_SECTOR,
    DCF_CRECIMIENTO_MIN,
    DCF_DEUDA_MKTCAP_MAX,
    DCF_G_TERMINAL,
    DCF_KD_MAX,
    DCF_KD_MIN,
    DCF_MULTIPLO_TERMINAL_MAX,
    DCF_PRIMA_MERCADO,
    DCF_SECTORES_APALANCADOS,
    DCF_TASA_LIBRE_RIESGO,
    DCF_TIPO_IMPOSITIVO_DEFECTO,
    DCF_WACC_DEFECTO,
    DCF_WACC_MAX,
    DCF_WACC_MAX_PONDERADO,
    DCF_WACC_MIN,
    DCF_WACC_MIN_PONDERADO,
    EV_EBITDA_INDUSTRIAS_EXCLUIDAS,
    EV_EBITDA_INDUSTRIAS_SIN_REFERENCIA_FIABLE,
    EV_EBITDA_MEDIANO_INDUSTRIA,
    EV_EBITDA_MEDIANO_SECTOR,
    EXCLUSION_SUELO,
    EXCLUSION_TECHO,
    FORWARD_PER_MEDIANO_SECTOR,
    INDUSTRIA_YF_A_DAMODARAN,
    INDUSTRIAS_REIT,
    MARGEN_BRUTO_MEDIANO_SECTOR,
    MARGEN_NETO_MEDIANO_SECTOR,
    PEG_CRECIMIENTO_MAX,
    PEG_CRECIMIENTO_MIN,
    PEG_OBJETIVO,
    PER_INDUSTRIAS_SIN_REFERENCIA_FIABLE,
    PER_MEDIANO_SECTOR,
    PESOS_CALIDAD,
    PESOS_FAIR_VALUE,
    ROE_MEDIANO_SECTOR,
    TRIMESTRES_EVOLUCION,
    UMBRAL_ESTABILIDAD_PER_HISTORICO,
    UMBRAL_PER_CARA_BARATA,
)
from utils.formato import es_valido, escalar, num, ponderar, primero_valido


# ------------------------------------------------- lectura de estados -------
def fila(df: pd.DataFrame, *etiquetas: str) -> pd.Series | None:
    """Extrae una partida contable probando varias etiquetas alternativas."""
    if df is None or df.empty:
        return None
    indice = {str(i).lower(): i for i in df.index}
    for etiqueta in etiquetas:
        clave = etiqueta.lower()
        if clave in indice:
            serie = df.loc[indice[clave]].dropna()
            if len(serie):
                return serie.astype(float)
    return None


def valor_anio(serie: pd.Series | None, desplazamiento: int = 0) -> float | None:
    """Valor del ejercicio n (0 = más reciente). Columnas ordenadas desc."""
    if serie is None or len(serie) <= desplazamiento:
        return None
    return num(serie.iloc[desplazamiento])


# ------------------------------------------------------------ métodos FV ----
def _base_fcf_normalizada(fcf_serie: pd.Series | None, info: dict, estados: dict) -> tuple[float | None, str]:
    """Base de FCF distinguiendo TENDENCIA de RUIDO, y ciclo inversor de
    declive real.

    Antes se sustituía por la mediana de 3 años en cuanto el último
    ejercicio se desviaba >35% en cualquier sentido. Eso penalizaba a
    empresas con tendencia real (AVGO: FCF 14,1 -> 16,3 -> 17,6 -> 19,4 M$;
    el último año no es un pico insostenible, es la tendencia) y no
    distinguía capex de crecimiento de declive real del negocio.

    Reglas, en orden:
      1. FCF más reciente <= 0 -> None (se excluye; mejor ausente que un
         número inventado a partir de un valle del ciclo).
      2. Serie de FCF monótona CRECIENTE -> se usa el último (es tendencia).
      3. Serie de FCF monótona DECRECIENTE:
           - si los INGRESOS crecen -> ciclo inversor (capex de crecimiento
             comiéndose el flujo, caso Amazon con la IA): se usa la media
             de los 3 años, no el mínimo reciente.
           - si los ingresos también caen -> declive real: se usa el
             último, que es la lectura correcta.
      4. Serie oscilante con desviación > DCF_ANOMALIA_FCF sobre la
         mediana -> mediana de los 3 años.
      5. Resto -> último.
    """
    if fcf_serie is None or len(fcf_serie) == 0:
        v = primero_valido(info.get("freeCashflow"))
        return (v if es_valido(v) and v > 0 else None), "FCF de `info` (sin serie histórica)"

    ultimos = [num(x) for x in list(fcf_serie.iloc[:4]) if es_valido(x)]
    if not ultimos:
        return None, "sin FCF"
    ultimo = ultimos[0]
    if ultimo <= 0:
        return None, f"último FCF negativo ({ultimo / 1e6:,.0f} M\\$)"
    if len(ultimos) < 3:
        return ultimo, "último ejercicio (serie corta)"

    tres = ultimos[:3]
    creciente = tres[0] > tres[1] > tres[2]
    decreciente = tres[0] < tres[1] < tres[2]

    if creciente:
        return ultimo, "último ejercicio (tendencia creciente)"

    if decreciente:
        ingresos = fila(estados.get("resultados"), "Total Revenue", "Operating Revenue")
        ingresos_crecen = None
        if ingresos is not None and len(ingresos) >= 3:
            ir = [num(x) for x in list(ingresos.iloc[:3]) if es_valido(x)]
            if len(ir) == 3:
                ingresos_crecen = ir[0] > ir[1] > ir[2]
        if ingresos_crecen:
            return sum(tres) / 3, "media 3 años (ciclo inversor: ingresos suben, FCF baja)"
        return ultimo, "último ejercicio (declive real: ingresos y FCF bajan)"

    mediana = statistics.median(tres)
    if mediana > 0 and abs(ultimo / mediana - 1) > DCF_ANOMALIA_FCF:
        return mediana, f"mediana 3 años (serie oscilante, último desvía {ultimo / mediana - 1:+.0%})"
    return ultimo, "último ejercicio"


def valorar_dcf(paquete: dict) -> tuple[float | None, dict]:
    """DCF con FCFF (flujo desapalancado) y WACC ponderado real.

    HUÉRFANA A PROPÓSITO: desde el motor de valor objetivo de cuatro métodos
    esta función ya NO se llama desde `calcular_fair_value()`. Se conserva
    (junto con sus constantes `DCF_*` en settings) porque está calibrada y
    documentada, y porque la decisión de retirar el DCF se basó en su
    desviación frente al consenso, no en un error de implementación: si el
    criterio cambia, volver a enchufarla es añadir una línea. Ver
    ESTADO_PROYECTO.md.

    Metodología revisada tras detectar dos errores en la versión anterior:

    1) El FCF de Yahoo (`Operating Cash Flow - CapEx`) ya viene neto de
       intereses pagados (US GAAP los incluye en el flujo operativo): es un
       flujo APALANCADO, disponible para el accionista. La versión anterior
       lo descontaba a una tasa de coste de recursos propios y ADEMÁS
       restaba la deuda completa al hacer el puente a equity — contando la
       deuda dos veces. En empresas apalancadas (REITs, utilities, telecos)
       esto producía valoraciones absurdas (AMT: 25,99 $ vs consenso de
       215,70 $). Ahora se desapalanca expresamente: FCFF = FCF + intereses
       x (1 - tipo impositivo), y el WACC pondera Ke y Kd por estructura de
       capital real, así que la deuda se cuenta una sola vez, en el puente.

    2) El valor terminal (Gordon growth) puede implicar múltiplos de salida
       de 30x+ el FCF del año 5 cuando el WACC es bajo, muy por encima de lo
       que paga el mercado. Se acota con DCF_MULTIPLO_TERMINAL_MAX.

    Aviso honesto sobre el método: en la calibración sobre 29 tickers
    multisector, el DCF -incluso con esta metodología corregida- siguió
    siendo el método más alejado del consenso de analistas (mediana de
    desviación ~50%, frente a ~25-35% de multiplos/ev_ebitda/peg). Para
    empresas de alto crecimiento (AVGO, MSFT) ninguna tasa de descuento
    defendible acerca el DCF al consenso: el mercado paga múltiplos de
    salida que un DCF ortodoxo no puede sostener. Por eso su peso en
    PESOS_FAIR_VALUE se redujo a 0,10 en vez de retirarlo: sigue aportando
    señal en empresas de FCF estable y deuda normal, pero pesa poco donde
    es sistemáticamente ruidoso.
    """
    detalle = {"metodo": "DCF", "notas": []}
    estados = paquete.get("estados", {})
    info = paquete.get("info", {})
    sector = paquete.get("sector")

    fcf_serie = fila(estados.get("flujo_caja"), "Free Cash Flow")
    if fcf_serie is None:
        ocf = fila(estados.get("flujo_caja"), "Operating Cash Flow", "Total Cash From Operating Activities")
        capex = fila(estados.get("flujo_caja"), "Capital Expenditure", "Capital Expenditures")
        if ocf is not None and capex is not None:
            fcf_serie = (ocf + capex).dropna()

    fcf_base, origen_fcf = _base_fcf_normalizada(fcf_serie, info, estados)
    if not es_valido(fcf_base) or fcf_base <= 0:
        detalle["notas"].append(f"Flujo de caja libre no disponible o negativo ({origen_fcf})")
        return None, detalle

    acciones = primero_valido(info.get("sharesOutstanding"), info.get("impliedSharesOutstanding"))
    if not es_valido(acciones) or acciones <= 0:
        detalle["notas"].append("Número de acciones no disponible")
        return None, detalle

    caja = primero_valido(info.get("totalCash")) or 0.0
    deuda = primero_valido(info.get("totalDebt")) or 0.0

    # Guardarraíl: deuda contaminada por financiera cautiva (Ford Credit y
    # similares no son estructura de capital del negocio industrial).
    equity_mercado = primero_valido(info.get("marketCap"))
    if (
        es_valido(equity_mercado) and equity_mercado > 0 and deuda > 0
        and sector not in DCF_SECTORES_APALANCADOS
        and deuda / equity_mercado > DCF_DEUDA_MKTCAP_MAX
    ):
        detalle["notas"].append(
            f"Deuda/capitalización {deuda / equity_mercado:.1f}× en sector no apalancado: "
            "posible financiera cautiva incluida en la deuda total, dato no fiable"
        )
        return None, detalle

    # Tipo impositivo efectivo, para desapalancar el flujo y el Kd.
    tipo_impositivo = primero_valido(info.get("effectiveTaxRate"))
    if not es_valido(tipo_impositivo) or not (0.0 <= tipo_impositivo <= 0.45):
        tipo_impositivo = DCF_TIPO_IMPOSITIVO_DEFECTO

    # FCFF = FCF (ya neto de intereses) + intereses x (1 - t): desapalanca
    # el flujo para que sea coherente con un WACC que también pondera deuda.
    gasto_interes = valor_anio(
        fila(estados.get("resultados"), "Interest Expense", "Interest Expense Non Operating")
    )
    intereses = abs(gasto_interes) if es_valido(gasto_interes) else 0.0
    fcff = fcf_base + intereses * (1 - tipo_impositivo)

    # Ke: coste de recursos propios (CAPM).
    ke = DCF_WACC_DEFECTO
    beta = primero_valido(info.get("beta"))
    if es_valido(beta):
        ke = max(DCF_WACC_MIN, min(DCF_WACC_MAX, DCF_TASA_LIBRE_RIESGO + float(beta) * DCF_PRIMA_MERCADO))

    # Kd: coste de deuda REAL (intereses/deuda) con preferencia sobre un
    # suelo forzado, que arregla un ticker con deuda cara y rompe otro con
    # deuda genuinamente barata.
    if deuda > 0 and intereses > 0:
        kd = intereses / deuda
        origen_kd = "real (intereses / deuda)"
    else:
        kd = DCF_TASA_LIBRE_RIESGO + 0.015
        origen_kd = "estimado (sin dato de intereses)"
    kd_antes_suelo = kd
    kd = max(DCF_KD_MIN, min(DCF_KD_MAX, kd))
    if kd != kd_antes_suelo and origen_kd.startswith("real"):
        origen_kd = "real, ajustado al suelo mínimo"

    # WACC ponderado por estructura de capital real (equity a precio de
    # mercado, deuda contable).
    if not es_valido(equity_mercado) and es_valido(paquete.get("precio")):
        equity_mercado = float(paquete["precio"]) * acciones
    if not es_valido(equity_mercado) or equity_mercado <= 0:
        wacc = ke
    else:
        capital_total = equity_mercado + deuda
        wacc = (equity_mercado / capital_total) * ke + (deuda / capital_total) * kd * (1 - tipo_impositivo)
    wacc = max(DCF_WACC_MIN_PONDERADO, min(DCF_WACC_MAX_PONDERADO, wacc))

    # Crecimiento, por orden de fiabilidad: consenso de analistas -> CAGR
    # de ingresos -> CAGR de FCF. Ya no se usa `earningsGrowth`, que es
    # crecimiento interanual TRIMESTRAL (ruidoso, no una tasa de largo
    # plazo) y podía pegar el crecimiento al suelo para empresas con
    # trimestres puntuales flojos (Amazon: -5% perpetuo con 60 analistas
    # cubriendo un consenso al alza).
    estimaciones = paquete.get("estimaciones") or {}
    crecimiento = primero_valido(estimaciones.get("crecimiento_1y"))
    origen_g = "consenso de analistas (+1y)"
    if not es_valido(crecimiento):
        ingresos = fila(estados.get("resultados"), "Total Revenue", "Operating Revenue")
        if ingresos is not None and len(ingresos) >= 3:
            antiguo, reciente = valor_anio(ingresos, len(ingresos) - 1), valor_anio(ingresos, 0)
            anios = len(ingresos) - 1
            if es_valido(antiguo) and antiguo > 0 and es_valido(reciente) and reciente > 0 and anios > 0:
                crecimiento = (reciente / antiguo) ** (1 / anios) - 1
                origen_g = "CAGR de ingresos"
    if not es_valido(crecimiento) and fcf_serie is not None and len(fcf_serie) >= 3:
        antiguo = valor_anio(fcf_serie, len(fcf_serie) - 1)
        anios = len(fcf_serie) - 1
        if es_valido(antiguo) and antiguo > 0 and anios > 0:
            crecimiento = (fcf_base / antiguo) ** (1 / anios) - 1
            origen_g = "CAGR del FCF"
    if not es_valido(crecimiento):
        crecimiento, origen_g = DCF_G_TERMINAL, "terminal (sin dato estimable)"

    techo_crecimiento = DCF_CRECIMIENTO_MAX_SECTOR.get(sector, DCF_CRECIMIENTO_MAX)
    # Suelo a 0%: proyectar decrecimiento perpetuo no es un caso base
    # defendible para una empresa con cobertura de analistas.
    crecimiento = max(0.0, min(techo_crecimiento, float(crecimiento)))

    if wacc <= DCF_G_TERMINAL:
        detalle["notas"].append("WACC inferior al crecimiento terminal: DCF descartado")
        return None, detalle

    valor_presente = 0.0
    flujo = fcff
    for anio in range(1, DCF_ANIOS + 1):
        g = crecimiento * (1 - (anio - 1) / DCF_ANIOS) + DCF_G_TERMINAL * ((anio - 1) / DCF_ANIOS)
        flujo *= 1 + g
        valor_presente += flujo / (1 + wacc) ** anio

    # Valor terminal con tope explícito al múltiplo de salida implícito.
    terminal_gordon = flujo * (1 + DCF_G_TERMINAL) / (wacc - DCF_G_TERMINAL)
    terminal_tope = flujo * DCF_MULTIPLO_TERMINAL_MAX
    terminal = min(terminal_gordon, terminal_tope)
    topado = terminal_gordon > terminal_tope
    valor_presente += terminal / (1 + wacc) ** DCF_ANIOS

    equity = valor_presente + caja - deuda
    por_accion = equity / acciones
    multiplo_terminal_real = terminal / flujo

    detalle.update(
        {
            "fcf_base": fcf_base,
            "origen_fcf": origen_fcf,
            "fcff": fcff,
            "crecimiento": crecimiento,
            "origen_crecimiento": origen_g,
            "ke": ke,
            "kd": kd,
            "origen_kd": origen_kd,
            "wacc": wacc,
            "multiplo_terminal": multiplo_terminal_real,
            "valor_empresa": valor_presente,
            "valor_accion": por_accion,
            "formula": (
                f"FCF base {fcf_base / 1e6:,.0f} M\\$ ({origen_fcf}) → FCFF (desapalancado) "
                f"{fcff / 1e6:,.0f} M\\$ → proyectado {DCF_ANIOS} años con crecimiento inicial "
                f"{crecimiento * 100:.1f}% ({origen_g}) decayendo a terminal {DCF_G_TERMINAL * 100:.1f}%, "
                f"descontado a WACC ponderado {wacc * 100:.1f}% (Ke {ke * 100:.1f}% / Kd {kd * 100:.1f}%, "
                f"{origen_kd}). Valor terminal a {multiplo_terminal_real:.1f}× el flujo del año "
                f"{DCF_ANIOS}{' (topado)' if topado else ''}. "
                f"Equity = VP flujos ({valor_presente / 1e6:,.0f} M\\$) + caja ({caja / 1e6:,.0f} M\\$) "
                f"− deuda ({deuda / 1e6:,.0f} M\\$), ÷ {acciones / 1e6:,.0f} M acciones → {por_accion:,.2f} \\$"
            ),
        }
    )
    return (por_accion if por_accion > 0 else None), detalle



def valorar_peg(paquete: dict) -> tuple[float | None, dict]:
    """Valoración por PEG con estimaciones reales de analistas a 1 año.

    PER justo = PEG objetivo x crecimiento estimado (en puntos porcentuales),
    aplicado al BPA estimado del próximo ejercicio. Es la regla de Lynch: una
    empresa que crece al 17% anual "merece" un PER en torno a 17x.

    Se usa exclusivamente el horizonte +1y porque es el más lejano que Yahoo
    publica de forma fiable: no existen estimaciones a 2-3 años vista (la
    fila LTG viene vacía en buena parte de los valores), así que cualquier
    proyección más larga sería una extrapolación nuestra disfrazada de dato
    de analista.
    """
    detalle = {"metodo": "PEG (estimaciones a 1 año)", "notas": []}
    info = paquete.get("info", {})
    estimaciones = paquete.get("estimaciones") or {}

    bpa = primero_valido(estimaciones.get("eps_1y"), info.get("forwardEps"))
    if not es_valido(bpa) or bpa <= 0:
        detalle["notas"].append("BPA estimado no disponible o negativo")
        return None, detalle

    crecimiento = primero_valido(estimaciones.get("crecimiento_1y"), info.get("earningsGrowth"))
    if not es_valido(crecimiento):
        detalle["notas"].append("Sin estimación de crecimiento: método no aplicable")
        return None, detalle
    if crecimiento < PEG_CRECIMIENTO_MIN:
        detalle["notas"].append(
            f"Crecimiento estimado {crecimiento * 100:.1f}% por debajo del {PEG_CRECIMIENTO_MIN * 100:.0f}%: "
            "el PEG no es aplicable a empresas de crecimiento bajo (implicaría un PER "
            "justo indefendiblemente bajo). Método excluido, no pinzado."
        )
        return None, detalle

    g = min(PEG_CRECIMIENTO_MAX, float(crecimiento))
    if g != float(crecimiento):
        detalle["notas"].append(
            f"Crecimiento acotado de {float(crecimiento) * 100:.1f}% a {g * 100:.1f}%"
        )

    per_justo = PEG_OBJETIVO * (g * 100)
    valor = per_justo * bpa

    detalle.update(
        {
            "bpa_estimado": bpa,
            "crecimiento": g,
            "peg_objetivo": PEG_OBJETIVO,
            "per_justo": per_justo,
            "valor_accion": valor,
            "formula": (
                f"PER justo = PEG objetivo {PEG_OBJETIVO:.1f} × crecimiento {g * 100:.1f}% "
                f"= {per_justo:.1f}× · BPA estimado +1a {bpa:,.2f} \\$ → {valor:,.2f} \\$"
            ),
        }
    )
    return (valor if valor > 0 else None), detalle


def valorar_ev_ebitda(paquete: dict) -> tuple[float | None, dict]:
    """EV/EBITDA por industria (con fallback a sector). Sustituye al DDM
    (retirado: solo aplicaba a empresas con dividendo y quedaba inútil en
    el resto de casos).

    Equity Value = EBITDA x múltiplo objetivo - Deuda neta;
    Precio = Equity Value / acciones en circulación. Se separa Enterprise
    Value de Equity Value explícitamente en vez de escalar el precio
    linealmente por el ratio de múltiplos (ese atajo asume implícitamente
    que la deuda neta escala en proporción al equity, lo cual es falso
    salvo que la empresa no tenga deuda, y sesga el resultado en empresas
    apalancadas).

    A diferencia del PER, EV/EBITDA no lo distorsiona el apalancamiento ni
    el tipo impositivo, y aplica igual de bien con o sin reparto de
    dividendo -- por eso cubre el hueco que dejaba el DDM sin depender de
    la política de dividendo de la empresa.

    El múltiplo se busca primero por INDUSTRIA (más específico que el
    sector: un único 14x para Healthcare no distinguía biotecnología en
    crecimiento de una aseguradora médica o una farmacéutica madura) y solo
    cae al múltiplo de sector si la industria no está en la tabla.

    Si SÍ hay múltiplo de industria pero la industria de Damodaran
    correspondiente (`INDUSTRIA_YF_A_DAMODARAN`) está marcada en
    `EV_EBITDA_INDUSTRIAS_SIN_REFERENCIA_FIABLE` (muestra pequeña, o el
    múltiplo de "solo EBITDA positivo" diverge >50% del de "todas las
    empresas" -- señal de que la muestra positiva ya no representa a la
    industria real), el método se EXCLUYE directamente: NO cae a sector,
    porque el problema no es que falte múltiplo de industria, es que el que
    hay no es de fiar. Validado sobre la cesta de 29 tickers: sin este
    filtro, GOOGL y META (Internet Content & Information → Software
    (Internet), divergencia 3,3×) recibían un fair value vía EV/EBITDA de
    914$ y 1.495$ respectivamente muy por encima de precio (ver
    ESTADO_PROYECTO.md).
    """
    detalle = {"metodo": "EV/EBITDA", "notas": []}
    info = paquete.get("info", {})
    industria = (paquete.get("industria") or "").strip()

    if industria in EV_EBITDA_INDUSTRIAS_EXCLUIDAS:
        detalle["notas"].append(
            f"«{industria}»: el EBITDA no es una base fiable para este tipo de negocio, o dos "
            "categorías de referencia igual de defendibles divergen demasiado para elegir una sin "
            "arbitrariedad; método excluido en vez de forzar un múltiplo que no representa la realidad."
        )
        return None, detalle

    ebitda = primero_valido(info.get("ebitda"))
    if not es_valido(ebitda) or ebitda <= 0:
        detalle["notas"].append("EBITDA no disponible o negativo")
        return None, detalle

    multiplo = EV_EBITDA_MEDIANO_INDUSTRIA.get(industria)
    origen_multiplo = f"industria «{industria}»"
    industria_damodaran = INDUSTRIA_YF_A_DAMODARAN.get(industria)
    if es_valido(multiplo) and industria_damodaran and industria_damodaran in EV_EBITDA_INDUSTRIAS_SIN_REFERENCIA_FIABLE:
        detalle["notas"].append(
            f"Múltiplo de industria «{industria}» (→ Damodaran «{industria_damodaran}») marcado sin "
            f"EV/EBITDA de referencia fiable "
            f"({EV_EBITDA_INDUSTRIAS_SIN_REFERENCIA_FIABLE[industria_damodaran]}); método excluido "
            "sin caer a sector, porque la industria sí tiene múltiplo, es que no es de fiar."
        )
        return None, detalle
    if not es_valido(multiplo):
        multiplo = EV_EBITDA_MEDIANO_SECTOR.get(paquete.get("sector"))
        origen_multiplo = "sector (sin múltiplo específico de industria)"
    if not es_valido(multiplo):
        detalle["notas"].append("Sin múltiplo EV/EBITDA de referencia para el sector ni la industria")
        return None, detalle

    acciones = primero_valido(info.get("sharesOutstanding"), info.get("impliedSharesOutstanding"))
    if not es_valido(acciones) or acciones <= 0:
        detalle["notas"].append("Número de acciones no disponible")
        return None, detalle

    deuda_neta = (primero_valido(info.get("totalDebt")) or 0.0) - (primero_valido(info.get("totalCash")) or 0.0)
    equity_value = ebitda * multiplo - deuda_neta
    por_accion = equity_value / acciones

    detalle.update(
        {
            "ebitda": ebitda,
            "multiplo": multiplo,
            "origen_multiplo": origen_multiplo,
            "deuda_neta": deuda_neta,
            "equity_value": equity_value,
            "valor_accion": por_accion,
            "formula": (
                f"[ EBITDA {ebitda / 1e6:,.0f} M\\$ × múltiplo {origen_multiplo} {multiplo:.1f}× "
                f"− deuda neta {deuda_neta / 1e6:,.0f} M\\$ ] ÷ {acciones / 1e6:,.0f} M acciones "
                f"→ {por_accion:,.2f} \\$"
            ),
        }
    )
    return (por_accion if por_accion > 0 else None), detalle


def _serie_per_historico(paquete: dict, anios: int = 5) -> list[float]:
    """PER de cada uno de los últimos `anios` ejercicios (precio medio anual
    / BPA del ejercicio), año a año.

    Se extrae como función propia para que la mediana pública
    (`calcular_per_historico`, usada por el método A del motor de valor
    objetivo) y el filtro de estabilidad del método B compartan exactamente
    el mismo cálculo -- no dos implementaciones que podrían desincronizarse.
    """
    estados = paquete.get("estados", {})
    historico = paquete.get("historico")
    beneficio = fila(estados.get("resultados"), "Net Income", "Net Income Common Stockholders")
    acciones = primero_valido(paquete.get("info", {}).get("sharesOutstanding"))
    if beneficio is None or historico is None or historico.empty or not es_valido(acciones):
        return []

    pers: list[float] = []
    for fecha in list(beneficio.index)[:anios]:
        try:
            ejercicio = pd.Timestamp(fecha)
        except Exception:
            continue
        ventana = historico.loc[
            (historico.index >= ejercicio - pd.Timedelta(days=365)) & (historico.index <= ejercicio)
        ]
        bpa = num(beneficio.loc[fecha])
        if ventana.empty or not es_valido(bpa) or bpa <= 0:
            continue
        pers.append(float(ventana["Close"].mean()) / (bpa / acciones))
    return [p for p in pers if 0 < p < 100]


def calcular_per_historico(paquete: dict, anios: int = 5) -> float | None:
    """PER medio de los últimos 5 años: precio medio anual / BPA de cada ejercicio.

    Mediana en vez de media: un solo año con BPA distorsionado (cargos
    puntuales, amortización de intangibles por una adquisición, etc.) infla
    la media pero apenas mueve la mediana.
    """
    validos = _serie_per_historico(paquete, anios)
    return statistics.median(validos) if validos else None


def _per_historico_es_estable(paquete: dict, anios: int = 5) -> bool:
    """Si el PER histórico propio es lo bastante consistente para usarse tal
    cual en el método B del motor de valor objetivo, o si conviene caer al
    PER del sector.

    Dos condiciones: (1) al menos 3 ejercicios válidos -- con menos, la
    mediana es poco más que un dato suelto -- y (2) que el ejercicio más
    caro no supere en más de `UMBRAL_ESTABILIDAD_PER_HISTORICO` veces al más
    barato. Una empresa que cotizó a 15x un año y a 60x otro (rampa de
    crecimiento, o un cargo puntual que casi anula el BPA de un ejercicio)
    no tiene un "PER propio" fiable: tiene una serie inestable que hay que
    sustituir por la referencia del sector en vez de tomarla al pie de la
    letra.
    """
    serie = _serie_per_historico(paquete, anios)
    if len(serie) < 3:
        return False
    return (max(serie) / min(serie)) <= UMBRAL_ESTABILIDAD_PER_HISTORICO


def valorar_per_ttm_propio(paquete: dict) -> tuple[float | None, dict]:
    """Método A del motor de valor objetivo: PER histórico propio (mediana
    de los últimos 5 años) x BPA TTM (trailing).

    El más simple de los cuatro: una sola multiplicación, sin más filtro que
    los que ya trae `calcular_per_historico()`. Representa "lo que el
    mercado ha pagado habitualmente por esta empresa concreta", aplicado a
    su beneficio ya conocido -- sin apostar por si el histórico es fiable o
    no, que es precisamente lo que sí hace el método B.
    """
    detalle = {"metodo": "PER histórico propio × BPA TTM", "notas": []}
    per_historico = calcular_per_historico(paquete)
    bpa_ttm = primero_valido(paquete.get("info", {}).get("trailingEps"))

    if not es_valido(per_historico):
        detalle["notas"].append(
            "PER histórico propio no calculable (BPA negativo en los ejercicios "
            "disponibles o sin suficiente serie de precios)"
        )
        return None, detalle
    if not es_valido(bpa_ttm) or bpa_ttm <= 0:
        detalle["notas"].append("BPA TTM (trailing) no disponible o negativo")
        return None, detalle

    valor = per_historico * bpa_ttm
    detalle.update(
        per_historico_5a=per_historico,
        bpa_ttm=bpa_ttm,
        valor_accion=valor,
        formula=(
            f"PER histórico propio (mediana 5a) {per_historico:.1f}× × BPA TTM "
            f"{bpa_ttm:,.2f} \\$ = {valor:,.2f} \\$"
        ),
    )
    return valor, detalle


def valorar_per_razonable_forward(paquete: dict) -> tuple[float | None, dict]:
    """Método B del motor de valor objetivo: PER razonable x BPA forward
    (consenso de analistas a 1 año).

    El PER histórico propio SOLO se usa si pasa `_per_historico_es_estable()`;
    si no, se cae al PER medio del sector -- en base FORWARD
    (`FORWARD_PER_MEDIANO_SECTOR`), nunca a la tabla trailing, para no
    mezclar un BPA futuro con un múltiplo del pasado (el mismo error, ya
    identificado y evitado aquí desde el principio, que tenía la antigua
    `valorar_multiplos`).

    Antes de caer al sector, se comprueba la FIABILIDAD de la industria de
    Damodaran a la que traduce la industria de yfinance
    (`INDUSTRIA_YF_A_DAMODARAN`): si está en
    `PER_INDUSTRIAS_SIN_REFERENCIA_FIABLE` (muestra pequeña, exceso de
    empresas en pérdidas, o contradicción entre PER forward y PER agregado
    -- ver `generar_tablas_damodaran.py`), el método se EXCLUYE en vez de
    usar una referencia que la propia generación de tablas ya marcó como
    dudosa. Validado sobre la cesta de 29 tickers: sin este filtro, XOM y
    CVX (Oil/Gas Integrated, n=4 empresas) y NEM/FCX (Precious Metals/Metals
    & Mining, >85% de empresas en pérdidas) heredaban un salto de upside que
    era en gran parte ruido de la industria de referencia, no revalorización
    real (ver ESTADO_PROYECTO.md).
    """
    detalle = {"metodo": "PER razonable × BPA forward", "notas": []}
    info = paquete.get("info", {})
    sector = paquete.get("sector")
    industria = (paquete.get("industria") or "").strip()

    bpa_forward = primero_valido(info.get("forwardEps"))
    if not es_valido(bpa_forward) or bpa_forward <= 0:
        detalle["notas"].append("BPA forward (consenso de analistas) no disponible o negativo")
        return None, detalle

    estable = _per_historico_es_estable(paquete)
    per_historico = calcular_per_historico(paquete) if estable else None

    if estable and es_valido(per_historico):
        per_usado = per_historico
        origen = "histórico propio (pasa el filtro de estabilidad)"
    else:
        industria_damodaran = INDUSTRIA_YF_A_DAMODARAN.get(industria)
        if industria_damodaran and industria_damodaran in PER_INDUSTRIAS_SIN_REFERENCIA_FIABLE:
            detalle["notas"].append(
                f"PER histórico inestable y la industria «{industria}» (→ Damodaran "
                f"«{industria_damodaran}») está marcada sin PER de referencia fiable "
                f"({PER_INDUSTRIAS_SIN_REFERENCIA_FIABLE[industria_damodaran]}); método excluido "
                "en vez de usar una referencia ya señalada como dudosa."
            )
            return None, detalle

        per_usado = FORWARD_PER_MEDIANO_SECTOR.get(sector)
        origen = (
            "mediano del sector, base forward (histórico inestable o insuficiente)"
            if not estable
            else "mediano del sector, base forward (sin PER histórico calculable)"
        )
        if not es_valido(per_usado):
            detalle["notas"].append(
                f"PER histórico inestable y sin PER forward de referencia para el sector «{sector}»"
            )
            return None, detalle

    valor = per_usado * bpa_forward
    detalle.update(
        per_usado=per_usado,
        origen_per=origen,
        bpa_forward=bpa_forward,
        valor_accion=valor,
        formula=(
            f"PER {origen} {per_usado:.1f}× × BPA forward {bpa_forward:,.2f} \\$ = {valor:,.2f} \\$"
        ),
    )
    return valor, detalle



def racha_sorpresas(historial: list, trimestres: int = TRIMESTRES_EVOLUCION) -> dict:
    """Resume el historial de sorpresas de BPA de Finnhub.

    `earnings["historial"]` trae hasta 8 trimestres (EPS real, estimado,
    sorpresa %) y se descargaba en cada análisis sin que ningún módulo lo
    consumiera. Devuelve los N más recientes (del más reciente al más
    antiguo, que es como se lee una racha) y el recuento de veces que se
    superó la estimación.
    """
    if not historial:
        return {"trimestres": [], "superados": 0, "total": 0}

    filas = []
    for t in historial[:trimestres]:
        real = num(t.get("actual"))
        estimado = num(t.get("estimate"))
        sorpresa = num(t.get("surprisePercent"))
        if not es_valido(sorpresa) and es_valido(real) and es_valido(estimado) and estimado:
            sorpresa = (real - estimado) / abs(estimado) * 100
        filas.append(
            {
                "periodo": t.get("period"),
                "real": real,
                "estimado": estimado,
                "sorpresa_pct": sorpresa,
                "supera": (real > estimado) if es_valido(real) and es_valido(estimado) else None,
            }
        )
    comparables = [f for f in filas if f["supera"] is not None]
    return {
        "trimestres": filas,
        "superados": sum(1 for f in comparables if f["supera"]),
        "total": len(comparables),
    }


def comparativa_per(paquete: dict) -> dict:
    """Los cuatro PER que la app ya calcula o consume, reunidos para
    compararlos de un vistazo: actual (trailing), forward, histórico propio
    (mediana 5 años) y mediano del sector (base trailing, la referencia
    "de siempre" con la que se suele comparar un PER actual).

    Ninguno es un dato nuevo: `trailingPE`/`forwardPE` vienen de `info`, el
    histórico propio ya lo calcula `calcular_per_historico()` (usado por el
    método A del motor de valor objetivo) y la mediana sectorial es
    `PER_MEDIANO_SECTOR`. Aquí solo se agrupan para la lectura visual.
    """
    info = paquete.get("info", {})
    return {
        "actual": primero_valido(info.get("trailingPE")),
        "forward": primero_valido(info.get("forwardPE")),
        "historico": calcular_per_historico(paquete),
        "sector": PER_MEDIANO_SECTOR.get(paquete.get("sector")),
    }


def interpretacion_per(pers: dict) -> str | None:
    """Traduce la comparativa de PER a un mensaje de una línea: cara/barata
    frente al sector y cara/barata frente a su propia historia.

    Se compara el PER ACTUAL (trailing) contra el sector y contra el
    histórico propio -- son las dos preguntas distintas que responde el
    gráfico ("¿cara para lo que paga el mercado por este tipo de negocio?" y
    "¿cara para lo que ha cotizado ella misma?"), y pueden dar respuestas
    distintas sin contradecirse: una empresa puede cotizar barata frente a
    su sector y cara frente a su propia historia a la vez.
    """
    actual = pers.get("actual")
    sector = pers.get("sector")
    historico = pers.get("historico")
    if not es_valido(actual):
        return None

    partes = []
    if es_valido(sector) and sector > 0:
        ratio = actual / sector
        if ratio <= 1 / UMBRAL_PER_CARA_BARATA:
            partes.append("barata frente a su sector")
        elif ratio >= UMBRAL_PER_CARA_BARATA:
            partes.append("cara frente a su sector")
        else:
            partes.append("en línea con su sector")
    if es_valido(historico) and historico > 0:
        ratio = actual / historico
        if ratio <= 1 / UMBRAL_PER_CARA_BARATA:
            partes.append("barata frente a su propia historia")
        elif ratio >= UMBRAL_PER_CARA_BARATA:
            partes.append("cara frente a su propia historia")
        else:
            partes.append("en línea con su propia historia")

    if not partes:
        return None
    return (partes[0][0].upper() + partes[0][1:] + (f", {partes[1]}" if len(partes) > 1 else "")) + "."


def _aplicar_banda_cordura(valores: dict, ancla: float | None) -> tuple[dict, dict]:
    """Recorta o excluye cada método según su distancia al ancla MIXTA
    (mediana de los métodos propios junto con el consenso de analistas,
    cuando este tiene cobertura suficiente).

    Dos niveles, asimétricos:
      - Dentro de [ancla/BANDA_SUELO, ancla*BANDA_TECHO]: el valor se usa
        tal cual.
      - Hasta [ancla/EXCLUSION_SUELO, ancla*EXCLUSION_TECHO]: se recorta al
        borde de la banda. El método discrepa, pero su dirección (caro /
        barato) sigue siendo información real que vale la pena conservar.
      - Más allá de eso: se EXCLUYE (no se recorta). Ahí el método no está
        discrepando, ha fallado, y forzarlo al borde solo arrastraría la
        media con un número que ya no refleja el cálculo del método.

    Asimétrica porque el consenso del sell-side corre de media un 10-20%
    por encima del precio en el que termina cotizando el valor: ser más
    permisivo por debajo que por encima evita importar ese sesgo alcista
    al plan de DCA.
    """
    if not es_valido(ancla) or ancla <= 0:
        return dict(valores), {"recortes": {}, "excluidos": {}}

    ancla = float(ancla)
    suelo, techo = ancla / BANDA_SUELO, ancla * BANDA_TECHO
    fuera_min, fuera_max = ancla / EXCLUSION_SUELO, ancla * EXCLUSION_TECHO

    ajustados = dict(valores)
    recortes: dict[str, tuple[str, float, float]] = {}
    excluidos: dict[str, float] = {}
    for clave, v in valores.items():
        if not es_valido(v):
            continue
        v = float(v)
        if v < fuera_min or v > fuera_max:
            ajustados[clave] = None
            excluidos[clave] = v
        elif v < suelo:
            ajustados[clave] = suelo
            recortes[clave] = ("suelo", v, suelo)
        elif v > techo:
            ajustados[clave] = techo
            recortes[clave] = ("techo", v, techo)
    return ajustados, {"recortes": recortes, "excluidos": excluidos}


def calcular_fair_value(paquete: dict) -> dict:
    """Motor de valor objetivo: cuatro métodos de una sola multiplicación
    (sin DCF) más el consenso de analistas.

    Diseñado en 'Dudas Generales 2' para sustituir al motor anterior
    (DCF + múltiplos + EV/EBITDA + PEG + consenso), que tenía dos problemas:
    el DCF era, con diferencia, el método más alejado del consenso incluso
    tras corregir su metodología (ver nota histórica en `valorar_dcf`, que
    se conserva en el módulo pero deja de llamarse desde aquí); y el
    consenso podía ser SIMULTÁNEAMENTE el ancla de la banda de cordura y,
    con cobertura amplia, el componente de más peso de la media -- se
    vigilaba a sí mismo.

    Los cuatro métodos:
      A. PER histórico propio × BPA TTM           (`valorar_per_ttm_propio`)
      B. PER razonable × BPA forward               (`valorar_per_razonable_forward`)
      C. PEG                                        (`valorar_peg`, sin cambios)
      D. EV/EBITDA sectorial/industria              (`valorar_ev_ebitda`, sin cambios)
    más el consenso de analistas, con pesos fijos (`PESOS_FAIR_VALUE`). Ver
    más abajo la excepción para REIT (A/B/C excluidos).

    La banda de cordura usa una ANCLA MIXTA: la mediana de los cuatro
    métodos propios junto con el consenso (si tiene cobertura suficiente),
    todos con el mismo peso en la ancla -- ya no "consenso si hay >=N
    analistas, si no la mediana de los métodos", que es lo que generaba la
    circularidad. El consenso sigue sin pasar por la propia banda de
    cordura (no tiene sentido recortarlo contra un ancla de la que él mismo
    forma parte); los cuatro métodos propios sí.

    EXCEPCIÓN REIT: si la industria está en `INDUSTRIAS_REIT`, A, B y C se
    excluyen de raíz (ni siquiera se calculan) porque los tres dependen de
    BPA -- GAAP, TTM o estimado -- y el BPA no es una magnitud económica
    válida para un REIT (la amortización del inmueble se come el beneficio
    contable sin reflejar la realidad del negocio; el estándar del sector es
    FFO/AFFO). El fair value de un REIT se apoya solo en D (EV/EBITDA, no
    distorsionado por amortización) y en el consenso -- `ponderar()` muestra
    la cobertura reducida (35%) en vez de esconderla. Corrección PARCIAL y
    deliberadamente conservadora mientras no se implemente P/FFO completo
    (ver ESTADO_PROYECTO.md). Validado con datos reales: O pasa de +19,5% a
    +7,0% de upside y PLD de -9,6% a -3,4% al quitar la contaminación de A/B/C.
    """
    es_reit = (paquete.get("industria") or "").strip() in INDUSTRIAS_REIT

    if es_reit:
        nota_reit = [
            "REIT: BPA GAAP no es una magnitud económica válida para este tipo de negocio "
            "(la amortización del inmueble distorsiona el beneficio contable); método excluido."
        ]
        a_val, det_a = None, {"metodo": "PER histórico propio × BPA TTM", "notas": list(nota_reit)}
        b_val, det_b = None, {"metodo": "PER razonable × BPA forward", "notas": list(nota_reit)}
        c_val, det_c = None, {"metodo": "PEG", "notas": list(nota_reit)}
    else:
        a_val, det_a = valorar_per_ttm_propio(paquete)
        b_val, det_b = valorar_per_razonable_forward(paquete)
        c_val, det_c = valorar_peg(paquete)
    d_val, det_d = valorar_ev_ebitda(paquete)

    consenso = paquete.get("consenso", {})
    objetivo = primero_valido(consenso.get("precio_objetivo"))
    n_analistas = consenso.get("n_analistas")
    consenso_fiable = es_valido(objetivo) and es_valido(n_analistas) and float(n_analistas) >= BANDA_MIN_ANALISTAS
    consenso_val = float(objetivo) if consenso_fiable else None

    valores_metodos = {"per_ttm": a_val, "per_forward": b_val, "peg": c_val, "ev_ebitda": d_val}

    pool_ancla = [v for v in valores_metodos.values() if es_valido(v)]
    if es_valido(consenso_val):
        pool_ancla.append(consenso_val)
    ancla = statistics.median(pool_ancla) if pool_ancla else None

    valores_ajustados, info_banda = _aplicar_banda_cordura(valores_metodos, ancla)

    resultado = ponderar({**valores_ajustados, "consenso": consenso_val}, PESOS_FAIR_VALUE)

    precio = paquete.get("precio")
    fv = resultado["valor"]
    upside = ((fv / precio) - 1) * 100 if es_valido(fv) and es_valido(precio) and precio > 0 else None

    # Anotar en el detalle de cada método si la banda de cordura intervino,
    # para que la interfaz pueda mostrarlo junto a la fórmula.
    for clave, det in (
        ("per_ttm", det_a), ("per_forward", det_b), ("peg", det_c), ("ev_ebitda", det_d),
    ):
        if clave in info_banda["excluidos"]:
            original = info_banda["excluidos"][clave]
            det["banda_cordura"] = {"accion": "excluido", "valor_original": original, "ancla": ancla}
            det["notas"].append(
                f"Banda de cordura: {original:,.2f} \\$ se desvía demasiado del ancla mixta "
                f"({ancla:,.2f} \\$) para ser fiable; método excluido de esta valoración."
            )
        elif clave in info_banda["recortes"]:
            borde, original, recortado = info_banda["recortes"][clave]
            det["banda_cordura"] = {
                "accion": "recortado", "borde": borde,
                "valor_original": original, "valor_recortado": recortado, "ancla": ancla,
            }
            det["notas"].append(
                f"Banda de cordura: recortado de {original:,.2f} \\$ a {recortado:,.2f} \\$ "
                f"({'techo' if borde == 'techo' else 'suelo'} de la banda respecto al ancla mixta)."
            )

    return {
        "fair_value": fv,
        "upside_pct": upside,
        "ancla_banda_cordura": ancla,
        "componentes": {
            "PER histórico propio × BPA TTM": {"valor": a_val, "detalle": det_a},
            "PER razonable × BPA forward": {"valor": b_val, "detalle": det_b},
            "Valoración PEG": {"valor": c_val, "detalle": det_c},
            "EV/EBITDA sectorial": {"valor": d_val, "detalle": det_d},
            "Consenso analistas": {
                "valor": consenso_val,
                "detalle": {
                    "metodo": "Consenso",
                    "n_analistas": n_analistas,
                    "unanimidad": consenso.get("unanimidad"),
                    "notas": [] if consenso_fiable else [
                        f"Sin cobertura suficiente (mínimo {BANDA_MIN_ANALISTAS} analistas)"
                        if es_valido(objetivo) else "Sin cobertura de analistas"
                    ],
                    "formula": (
                        f"Precio objetivo medio de {n_analistas:.0f} analistas → {objetivo:,.2f} \\$"
                        if consenso_fiable
                        else None
                    ),
                },
            },
        },
        "pesos_aplicados": resultado["usados"],
        "excluidos": resultado["excluidos"],
        "cobertura": resultado["cobertura"],
        "alerta": clasificar_valoracion(upside),
    }


def clasificar_valoracion(upside_pct: float | None) -> dict:
    """Traduce el % de upside a etiqueta y color según las bandas definidas."""
    if not es_valido(upside_pct):
        return {"etiqueta": "Valoración no calculable", "color": "#94a3b8", "upside": None}
    u = float(upside_pct)
    for minimo, maximo, etiqueta, color in BANDAS_VALORACION:
        if (minimo is None or u >= minimo) and (maximo is None or u < maximo):
            return {"etiqueta": etiqueta, "color": color, "upside": u}
    return {"etiqueta": "Valoración no calculable", "color": "#94a3b8", "upside": u}


# --------------------------------------------- puntuación de calidad 0-100 --
def puntuar_calidad(paquete: dict, fair_value: dict) -> dict:
    """Salud fundamental (0-100) en 4 bloques analíticos del 25% cada uno.

    Los 9 criterios binarios del antiguo Piotroski F-Score están disueltos
    aquí en métricas individuales con peso propio (rotación de activos,
    margen bruto, ROA, apalancamiento, liquidez corriente, dilución), de
    modo que se ve qué falla exactamente y cuánto cuesta, en vez de quedar
    agregado en un único número opaco.
    """
    info = paquete.get("info", {})
    sector = paquete.get("sector")
    estados = paquete.get("estados", {})

    sub: dict[str, float | None] = {}
    lecturas: dict[str, float | None] = {}

    # 2-3. PER frente a sector e histórico (menos es mejor)
    per = primero_valido(info.get("trailingPE"))
    per_sector = PER_MEDIANO_SECTOR.get(sector)
    per_hist = calcular_per_historico(paquete)
    lecturas["per"] = per
    lecturas["per_sector"] = per_sector
    lecturas["per_historico_5a"] = per_hist
    if es_valido(per) and es_valido(per_sector) and per > 0:
        sub["per_vs_sector"] = escalar(per / per_sector, 1.6, 0.6)
    if es_valido(per) and es_valido(per_hist) and per > 0:
        sub["per_vs_historico"] = escalar(per / per_hist, 1.6, 0.6)

    # 4. Forward PER frente a PER actual (expectativa de mejora)
    fwd = primero_valido(info.get("forwardPE"))
    lecturas["forward_per"] = fwd
    if es_valido(fwd) and es_valido(per) and per > 0 and fwd > 0:
        sub["forward_per"] = escalar(fwd / per, 1.2, 0.7)

    # 5. Margen neto vs. sector
    margen = primero_valido(info.get("profitMargins"))
    lecturas["margen_neto"] = margen
    ref_margen = MARGEN_NETO_MEDIANO_SECTOR.get(sector)
    if es_valido(margen):
        sub["margen_neto"] = (
            escalar(margen / ref_margen, 0.4, 1.8)
            if es_valido(ref_margen) and ref_margen
            else escalar(margen, 0.0, 0.25)
        )

    # 6. ROE vs. sector
    roe = primero_valido(info.get("returnOnEquity"))
    lecturas["roe"] = roe
    ref_roe = ROE_MEDIANO_SECTOR.get(sector)
    if es_valido(roe):
        sub["roe"] = (
            escalar(roe / ref_roe, 0.4, 1.8) if es_valido(ref_roe) and ref_roe else escalar(roe, 0.0, 0.25)
        )

    # 7. ROIC = NOPAT / (deuda + fondos propios)
    roic = calcular_roic(paquete)
    lecturas["roic"] = roic
    if es_valido(roic):
        sub["roic"] = escalar(roic, 0.02, 0.20)

    # 8. PEG (por debajo de 1 es excelente)
    peg = primero_valido(info.get("trailingPegRatio"), info.get("pegRatio"))
    lecturas["peg"] = peg
    if es_valido(peg) and peg > 0:
        sub["peg"] = escalar(peg, 3.0, 0.8)

    # 8b. EV/EBITDA frente a la mediana del sector. A diferencia del PER, no
    # lo distorsionan ni el apalancamiento ni el tipo impositivo ni el peso
    # de las amortizaciones, así que aporta una lectura de valoración
    # independiente de las tres basadas en PER.
    ev = primero_valido(info.get("enterpriseValue"))
    ebitda_info = primero_valido(info.get("ebitda"))
    if not es_valido(ev):
        cap = primero_valido(info.get("marketCap"))
        deuda_ev = primero_valido(info.get("totalDebt"))
        caja_ev = primero_valido(info.get("totalCash"))
        if es_valido(cap):
            ev = cap + (deuda_ev or 0.0) - (caja_ev or 0.0)
    ev_ebitda = (
        ev / ebitda_info if es_valido(ev) and es_valido(ebitda_info) and ebitda_info > 0 else None
    )
    ref_ev_ebitda = EV_EBITDA_MEDIANO_SECTOR.get(sector)
    lecturas["ev_ebitda"] = ev_ebitda
    lecturas["ev_ebitda_sector"] = ref_ev_ebitda
    if es_valido(ev_ebitda) and ev_ebitda > 0:
        sub["ev_ebitda"] = (
            escalar(ev_ebitda / ref_ev_ebitda, 1.6, 0.6)
            if es_valido(ref_ev_ebitda) and ref_ev_ebitda
            else escalar(ev_ebitda, 25.0, 8.0)
        )

    # 9-10. Tendencia de ingresos y beneficios: CAGR anual ponderado por
    # estabilidad trimestral. Un CAGR alto pero errático (un solo trimestre
    # extraordinario, o uno muy malo, distorsionando el conjunto) premia
    # menos que uno más modesto pero consistente.
    ingresos = fila(estados.get("resultados"), "Total Revenue", "Operating Revenue")
    beneficio = fila(estados.get("resultados"), "Net Income", "Net Income Common Stockholders")
    cagr_ing = _cagr(ingresos)
    cagr_ben = _cagr(beneficio)
    lecturas["cagr_ingresos"] = cagr_ing
    lecturas["cagr_beneficios"] = cagr_ben

    ingresos_trim = fila(estados.get("resultados_trim"), "Total Revenue", "Operating Revenue")
    beneficio_trim = fila(estados.get("resultados_trim"), "Net Income", "Net Income Common Stockholders")
    estab_ing = _calc_estabilidad_crecimiento(ingresos_trim)
    estab_ben = _calc_estabilidad_crecimiento(beneficio_trim)
    lecturas["estabilidad_ingresos"] = estab_ing
    lecturas["estabilidad_beneficios"] = estab_ben

    if es_valido(cagr_ing):
        sub["tendencia_ingresos"] = escalar(cagr_ing, -0.10, 0.20) * estab_ing
    if es_valido(cagr_ben):
        sub["tendencia_beneficios"] = escalar(cagr_ben, -0.15, 0.25) * estab_ben

    # 11. Calidad del beneficio: FCF / Beneficio neto.
    # Escala 0,5x -> 1,0x: convertir en caja el 100% del beneficio contable
    # ya es lo máximo exigible, así que 1,0x satura la puntuación. Los
    # anclajes anteriores (0,4 -> 1,2) exigían generar un 120% del beneficio
    # en caja para llegar al máximo -- algo que solo ocurre de forma
    # sostenida en negocios con fuertes cargos no-caja (amortización de
    # intangibles) -- y dejaban una conversión sana de 0,9x en un pobre
    # 3,1/5, penalizando a empresas sin nada que reprochar.
    fcf = primero_valido(info.get("freeCashflow"))
    neto = primero_valido(info.get("netIncomeToCommon"), valor_anio(beneficio, 0))
    calidad_beneficio = fcf / neto if es_valido(fcf) and es_valido(neto) and neto > 0 else None
    lecturas["fcf_sobre_beneficio"] = calidad_beneficio
    if es_valido(calidad_beneficio):
        sub["calidad_beneficio"] = escalar(calidad_beneficio, 0.5, 1.0)

    # 12. Solidez del FCF: no es lo mismo un FCF negativo por CAPEX de
    # expansión (CFO sigue positivo -- negocio operativo sano, invirtiendo
    # fuerte en fábricas, centros de datos, capacidad) que uno causado por
    # quema de caja operativa real (CFO también negativo -- el día a día
    # del negocio no genera caja, señal mucho más grave). Es un criterio
    # independiente de "calidad_beneficio" (que mide FCF/beneficio neto y
    # exige beneficio neto positivo para poder calcularse).
    ocf = valor_anio(fila(estados.get("flujo_caja"), "Operating Cash Flow", "Total Cash From Operating Activities"))
    lecturas["fcf"] = fcf
    lecturas["ocf"] = ocf
    if es_valido(fcf):
        if fcf > 0:
            sub["fcf_solidez"] = 100.0
        elif es_valido(ocf) and ocf > 0:
            sub["fcf_solidez"] = 50.0
        else:
            sub["fcf_solidez"] = 0.0

    # 13. Cobertura de intereses: EBIT / Gasto en intereses -- mide si la
    # empresa puede PAGAR los intereses de su deuda con el beneficio
    # operativo actual, algo que Deuda/Equity o Net Debt/EBITDA no capturan
    # por sí solos (mirar cuánta deuda hay no dice si se puede atender).
    ebit = valor_anio(fila(estados.get("resultados"), "EBIT", "Operating Income"))
    gasto_intereses = valor_anio(
        fila(estados.get("resultados"), "Interest Expense", "Interest Expense Non Operating")
    )
    cobertura_intereses = (
        ebit / abs(gasto_intereses)
        if es_valido(ebit) and es_valido(gasto_intereses) and gasto_intereses
        else None
    )
    lecturas["cobertura_intereses"] = cobertura_intereses
    if es_valido(cobertura_intereses):
        sub["cobertura_intereses"] = escalar(cobertura_intereses, 1.5, 6.0)

    # --- Métricas antes agregadas dentro del Piotroski F-Score --------------
    # Mismas fuentes de datos que usaba aquel (ya probadas en producción),
    # pero ahora cada una con peso propio y lectura visible.
    balance = estados.get("balance")
    flujo = estados.get("flujo_caja")
    activos = fila(balance, "Total Assets")
    bruto = fila(estados.get("resultados"), "Gross Profit")
    deuda_lp = fila(balance, "Long Term Debt", "Long Term Debt And Capital Lease Obligation")
    circulante = fila(balance, "Current Assets", "Total Current Assets")
    pasivo_circ = fila(balance, "Current Liabilities", "Total Current Liabilities")
    acciones_serie = fila(balance, "Ordinary Shares Number", "Share Issued")

    i0, i1 = valor_anio(ingresos, 0), valor_anio(ingresos, 1)
    a0, a1 = valor_anio(activos, 0), valor_anio(activos, 1)
    b0, b1 = valor_anio(beneficio, 0), valor_anio(beneficio, 1)

    # Rotación de activos: ingresos por unidad de activo, vs. año anterior
    if all(es_valido(x) for x in (i0, a0, i1, a1)) and a0 and a1:
        rot0, rot1 = i0 / a0, i1 / a1
        lecturas["rotacion_activos"] = rot0
        lecturas["rotacion_activos_prev"] = rot1
        # Escala continua sobre la variación relativa: -10% -> 0, +10% -> 100
        sub["rotacion_activos"] = escalar(rot0 / rot1 - 1 if rot1 else 0.0, -0.10, 0.10)

    # Margen bruto vs. mediana del sector (nivel, no solo tendencia)
    bruto0 = valor_anio(bruto, 0)
    if es_valido(bruto0) and es_valido(i0) and i0:
        margen_bruto = bruto0 / i0
        lecturas["margen_bruto"] = margen_bruto
        ref_bruto = MARGEN_BRUTO_MEDIANO_SECTOR.get(sector)
        sub["margen_bruto"] = (
            escalar(margen_bruto / ref_bruto, 0.5, 1.5)
            if es_valido(ref_bruto) and ref_bruto
            else escalar(margen_bruto, 0.15, 0.65)
        )

    # ROA: nivel actual (fusiona los antiguos "ROA positivo" y "ROA creciente")
    if es_valido(b0) and es_valido(a0) and a0:
        roa = b0 / a0
        lecturas["roa"] = roa
        sub["roa"] = escalar(roa, 0.0, 0.12)

    # Apalancamiento: deuda a largo plazo sobre activos, vs. año anterior
    dl0, dl1 = valor_anio(deuda_lp, 0), valor_anio(deuda_lp, 1)
    if all(es_valido(x) for x in (dl0, dl1, a0, a1)) and a0 and a1:
        apal0, apal1 = dl0 / a0, dl1 / a1
        lecturas["apalancamiento"] = apal0
        lecturas["apalancamiento_prev"] = apal1
        # Menos apalancamiento que el año pasado puntúa mejor (escala invertida)
        sub["apalancamiento"] = escalar(apal0 - apal1, 0.05, -0.05)

    # Liquidez corriente creciente (activo circulante / pasivo circulante)
    c0, p0 = valor_anio(circulante, 0), valor_anio(pasivo_circ, 0)
    c1, p1 = valor_anio(circulante, 1), valor_anio(pasivo_circ, 1)
    if all(es_valido(x) for x in (c0, p0, c1, p1)) and p0 and p1:
        cr0, cr1 = c0 / p0, c1 / p1
        lecturas["current_ratio"] = cr0
        lecturas["current_ratio_prev"] = cr1
        sub["current_ratio"] = escalar(cr0, 0.8, 2.0)
        sub["liquidez_creciente"] = escalar(cr0 - cr1, -0.3, 0.3)
    elif es_valido(c0) and es_valido(p0) and p0:
        lecturas["current_ratio"] = c0 / p0
        sub["current_ratio"] = escalar(c0 / p0, 0.8, 2.0)

    # Dilución: variación de acciones en circulación vs. año anterior.
    # Emitir papel nuevo diluye al accionista aunque el negocio crezca.
    ac0, ac1 = valor_anio(acciones_serie, 0), valor_anio(acciones_serie, 1)
    if es_valido(ac0) and es_valido(ac1) and ac1:
        dilucion = (ac0 - ac1) / ac1
        lecturas["dilucion"] = dilucion
        # +8% de dilución -> 0 pts; recompra del 2% -> 100 pts
        sub["dilucion"] = escalar(dilucion, 0.08, -0.02)

    # Debt/Equity y Net Debt/EBITDA (solvencia estructural)
    deuda_total = primero_valido(info.get("totalDebt"))
    caja_total = primero_valido(info.get("totalCash"))
    ebitda = primero_valido(info.get("ebitda"))
    debt_equity = primero_valido(info.get("debtToEquity"))
    if es_valido(debt_equity):
        lecturas["debt_equity"] = debt_equity  # yfinance lo da en %
        sub["debt_equity"] = escalar(debt_equity, 150.0, 20.0)
    if es_valido(deuda_total) and es_valido(ebitda) and ebitda > 0:
        net_debt_ebitda = (deuda_total - (caja_total or 0.0)) / ebitda
        lecturas["net_debt_ebitda"] = net_debt_ebitda
        sub["net_debt_ebitda"] = escalar(net_debt_ebitda, 4.0, 0.5)

    resultado = ponderar(sub, PESOS_CALIDAD)

    # Puntos obtenidos y disponibles por bloque analítico (para la interfaz).
    bloques = {}
    for nombre_bloque, metricas in BLOQUES_CALIDAD.items():
        obtenidos = sum(
            sub[m] / 100 * peso for m, peso in metricas.items() if es_valido(sub.get(m))
        )
        disponibles = sum(peso for m, peso in metricas.items() if es_valido(sub.get(m)))
        bloques[nombre_bloque] = {
            "obtenidos": obtenidos,
            "disponibles": disponibles,
            "maximo": sum(metricas.values()),
        }

    return {
        "puntuacion": round(resultado["valor"], 1) if es_valido(resultado["valor"]) else None,
        "subpuntuaciones": sub,
        "lecturas": lecturas,
        "excluidos": resultado["excluidos"],
        "cobertura": resultado["cobertura"],
        "bloques": bloques,
    }


def calcular_roic(paquete: dict) -> float | None:
    estados = paquete.get("estados", {})
    info = paquete.get("info", {})
    ebit = valor_anio(fila(estados.get("resultados"), "EBIT", "Operating Income"))
    impuestos = primero_valido(info.get("effectiveTaxRate")) or 0.21
    patrimonio = primero_valido(
        valor_anio(fila(estados.get("balance"), "Stockholders Equity", "Total Stockholder Equity"))
    )
    deuda = primero_valido(info.get("totalDebt"))
    if not es_valido(ebit) or not es_valido(patrimonio):
        return None
    capital = patrimonio + (deuda or 0.0)
    if capital <= 0:
        return None
    return (ebit * (1 - float(impuestos))) / capital


def _cagr(serie: pd.Series | None) -> float | None:
    """Tasa compuesta anual entre el ejercicio más antiguo y el más reciente."""
    if serie is None or len(serie) < 3:
        return None
    reciente, antiguo = num(serie.iloc[0]), num(serie.iloc[-1])
    anios = len(serie) - 1
    if not es_valido(reciente) or not es_valido(antiguo) or antiguo <= 0 or anios <= 0:
        return None
    if reciente <= 0:
        return -1.0
    return (reciente / antiguo) ** (1 / anios) - 1


def _calc_estabilidad_crecimiento(serie_trimestral: pd.Series | None) -> float:
    """Multiplicador 0.55-1.0 según la estabilidad del crecimiento trimestral.

    Se calcula el coeficiente de variación (desviación típica / media) de las
    tasas de variación intertrimestral. Cuanto más errático el crecimiento
    (trimestres muy dispares entre sí), menor el multiplicador aplicado sobre
    el CAGR anual -- así un +25% CAGR sostenido y regular puntúa más que un
    +25% CAGR que en realidad es un solo trimestre extraordinario arrastrando
    tres flojos (o viceversa). Sin datos suficientes, no penaliza (1.0).
    """
    if serie_trimestral is None or len(serie_trimestral) < 4:
        return 1.0
    valores = serie_trimestral.dropna().astype(float)
    if len(valores) < 4:
        return 1.0
    tasas = valores.pct_change().dropna()
    tasas = tasas[tasas.abs() < 5]  # descarta variaciones disparatadas (base casi cero)
    if len(tasas) < 2:
        return 1.0
    media, dispersion = float(tasas.mean()), float(tasas.std())
    if not es_valido(media) or media == 0 or not es_valido(dispersion):
        return 0.85
    cv = abs(dispersion / media)
    if cv <= 0.5:
        return 1.0
    if cv <= 1.0:
        return 0.85
    if cv <= 2.0:
        return 0.7
    return 0.55
