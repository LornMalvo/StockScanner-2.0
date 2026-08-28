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
    CONSENSO_MIN_ANALISTAS,
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
    EV_EBITDA_MEDIANO_INDUSTRIA,
    EV_EBITDA_MEDIANO_SECTOR,
    EXCLUSION_SUELO,
    EXCLUSION_TECHO,
    FORWARD_PER_MEDIANO_SECTOR,
    MARGEN_BRUTO_MEDIANO_SECTOR,
    MARGEN_NETO_MEDIANO_SECTOR,
    PEG_CRECIMIENTO_MAX,
    PEG_CRECIMIENTO_MIN,
    PEG_OBJETIVO,
    PER_HIST_TECHO_VS_SECTOR,
    PER_MEDIANO_SECTOR,
    PESO_PER_SECTOR,
    PESOS_CALIDAD,
    PESOS_FAIR_VALUE,
    ROE_MEDIANO_SECTOR,
    TRIMESTRES_EVOLUCION,
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


def valorar_multiplos(paquete: dict) -> tuple[float | None, dict]:
    """PER justo = media ponderada entre PER sectorial y PER histórico propio.

    Dos correcciones sobre la versión anterior:

    1) Coherencia forward/trailing. El BPA usado es forward cuando existe,
       pero se comparaba contra `PER_MEDIANO_SECTOR`, una tabla TRAILING —
       mezclar un BPA futuro con un múltiplo pasado infla el método de
       forma sistemática. Ahora, con BPA forward se usa
       `FORWARD_PER_MEDIANO_SECTOR` y el PER histórico (que es trailing por
       construcción) se reescala por la relación forward/trailing del
       sector para que ambos términos hablen el mismo idioma.

    2) Techo relativo en vez de absoluto. El filtro anterior descartaba
       solo PER > 60, dejando pasar valores como un PER histórico de 44,1x
       (mediana real de 5 años) en un sector cuya referencia forward es
       ~24x. Ahora el histórico no puede superar PER_HIST_TECHO_VS_SECTOR
       veces el sectorial.
    """
    detalle = {"metodo": "Múltiplos", "notas": []}
    info = paquete.get("info", {})
    sector = paquete.get("sector")

    bpa_forward = primero_valido(info.get("forwardEps"))
    es_forward = es_valido(bpa_forward) and bpa_forward > 0
    bpa = bpa_forward if es_forward else primero_valido(info.get("trailingEps"))
    if not es_valido(bpa) or bpa <= 0:
        detalle["notas"].append("BPA no disponible o negativo")
        return None, detalle

    tabla_sector = FORWARD_PER_MEDIANO_SECTOR if es_forward else PER_MEDIANO_SECTOR
    per_sector = tabla_sector.get(sector)
    per_historico = calcular_per_historico(paquete)

    recortado = False
    if es_valido(per_historico) and es_forward:
        per_trailing_sector = PER_MEDIANO_SECTOR.get(sector)
        per_forward_sector = FORWARD_PER_MEDIANO_SECTOR.get(sector)
        if es_valido(per_trailing_sector) and es_valido(per_forward_sector) and per_trailing_sector > 0:
            per_historico = per_historico * (per_forward_sector / per_trailing_sector)

    if es_valido(per_historico) and es_valido(per_sector):
        techo = per_sector * PER_HIST_TECHO_VS_SECTOR
        if per_historico > techo:
            per_historico, recortado = techo, True

    if es_valido(per_sector) and es_valido(per_historico):
        per_justo = PESO_PER_SECTOR * per_sector + (1 - PESO_PER_SECTOR) * per_historico
    elif es_valido(per_sector) or es_valido(per_historico):
        per_justo = per_sector if es_valido(per_sector) else per_historico
    else:
        detalle["notas"].append("Sin referencia de PER sectorial ni histórica")
        return None, detalle

    partes = []
    if es_valido(per_sector):
        partes.append(f"PER sector {'forward' if es_forward else 'trailing'} {per_sector:.1f}×")
    if es_valido(per_historico):
        partes.append(
            f"PER histórico propio 5a (mediana){' [recortado al techo sectorial]' if recortado else ''} "
            f"{per_historico:.1f}×"
        )
    bpa_origen = "Forward" if es_forward else "TTM"
    detalle.update(
        {
            "bpa": bpa,
            "per_sector": per_sector,
            "per_historico_5a": per_historico,
            "per_recortado": recortado,
            "per_justo": per_justo,
            "valor_accion": per_justo * bpa,
            "formula": (
                f"PER justo = {PESO_PER_SECTOR * 100:.0f}% sector + {(1 - PESO_PER_SECTOR) * 100:.0f}% "
                f"histórico [ {' ; '.join(partes)} ] = {per_justo:.1f}× "
                f"× BPA {bpa_origen} {bpa:,.2f} \\$ → {per_justo * bpa:,.2f} \\$"
            ),
        }
    )
    return per_justo * bpa, detalle


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
    """
    detalle = {"metodo": "EV/EBITDA", "notas": []}
    info = paquete.get("info", {})
    industria = (paquete.get("industria") or "").strip()

    if industria in EV_EBITDA_INDUSTRIAS_EXCLUIDAS:
        detalle["notas"].append(
            f"«{industria}»: el EBITDA no es una base fiable para este tipo de negocio "
            "(p. ej. biotecnología en rampa comercial, sin ingresos de producto estables); "
            "método excluido en vez de forzar un múltiplo que no representa la realidad."
        )
        return None, detalle

    ebitda = primero_valido(info.get("ebitda"))
    if not es_valido(ebitda) or ebitda <= 0:
        detalle["notas"].append("EBITDA no disponible o negativo")
        return None, detalle

    multiplo = EV_EBITDA_MEDIANO_INDUSTRIA.get(industria)
    origen_multiplo = f"industria «{industria}»"
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


def calcular_per_historico(paquete: dict, anios: int = 5) -> float | None:
    """PER medio de los últimos 5 años: precio medio anual / BPA de cada ejercicio."""
    estados = paquete.get("estados", {})
    historico = paquete.get("historico")
    beneficio = fila(estados.get("resultados"), "Net Income", "Net Income Common Stockholders")
    acciones = primero_valido(paquete.get("info", {}).get("sharesOutstanding"))
    if beneficio is None or historico is None or historico.empty or not es_valido(acciones):
        return None

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
    # Mediana en vez de media: un solo año con BPA distorsionado (cargos
    # puntuales, amortización de intangibles por una adquisición, etc.)
    # infla la media pero apenas mueve la mediana.
    validos = [p for p in pers if 0 < p < 100]
    return statistics.median(validos) if validos else None


def _serie_trimestral(df: pd.DataFrame | None, periodos: list, *etiquetas: str) -> list:
    """Valores de una partida para una lista concreta de columnas (periodos).

    El eje de periodos se pasa desde fuera para que las cuatro series (BPA,
    ingresos, margen, FCF) queden ALINEADAS trimestre a trimestre aunque a
    una le falte un dato: si falta, va `None` y el gráfico deja el hueco en
    su sitio, en vez de desplazar la serie un trimestre y comparar peras con
    manzanas.
    """
    serie = fila(df, *etiquetas)
    if serie is None:
        return [None] * len(periodos)
    return [num(serie.loc[p]) if p in serie.index else None for p in periodos]


def _etiqueta_trimestre(periodo) -> str:
    """'2026-06-30' -> '2T26'. Si no se puede interpretar, se deja tal cual."""
    try:
        ts = pd.Timestamp(periodo)
    except Exception:
        return str(periodo)[:10]
    return f"{(ts.month - 1) // 3 + 1}T{ts.year % 100:02d}"


def series_trimestrales(paquete: dict, trimestres: int = TRIMESTRES_EVOLUCION) -> dict:
    """BPA, ingresos, margen neto y FCF de los últimos N trimestres cerrados.

    Devuelve las cuatro series ya alineadas sobre el mismo eje de periodos
    (del más antiguo al más reciente, que es como se lee una evolución) para
    que la interfaz solo tenga que pintarlas.

    El eje de periodos lo marca la cuenta de resultados trimestral (trae tres
    de las cuatro magnitudes); el flujo de caja trimestral se reindexa contra
    ella.
    """
    estados = paquete.get("estados", {})
    resultados = estados.get("resultados_trim")
    flujo = estados.get("flujo_caja_trim")
    vacio = {"periodos": [], "bpa": [], "ingresos": [], "margen_neto": [], "fcf": []}
    if resultados is None or getattr(resultados, "empty", True):
        return vacio

    # Columnas ordenadas de más reciente a más antigua: se cogen las N
    # primeras y se invierte, para que el gráfico se lea en orden cronológico.
    periodos = list(resultados.columns)[:trimestres][::-1]
    if not periodos:
        return vacio

    ingresos = _serie_trimestral(resultados, periodos, "Total Revenue", "Operating Revenue")
    beneficio = _serie_trimestral(
        resultados, periodos, "Net Income", "Net Income Common Stockholders"
    )
    bpa = _serie_trimestral(resultados, periodos, "Diluted EPS", "Basic EPS")
    fcf = _serie_trimestral(flujo, periodos, "Free Cash Flow")

    # Respaldo si la fila "Free Cash Flow" no viene: caja operativa menos
    # capex (que en Yahoo llega en negativo, de ahí la suma).
    if not any(es_valido(x) for x in fcf):
        ocf = _serie_trimestral(
            flujo, periodos, "Operating Cash Flow", "Total Cash From Operating Activities"
        )
        capex = _serie_trimestral(flujo, periodos, "Capital Expenditure")
        fcf = [
            (o + c) if es_valido(o) and es_valido(c) else None for o, c in zip(ocf, capex)
        ]

    margen = [
        (b / i * 100) if es_valido(b) and es_valido(i) and i else None
        for b, i in zip(beneficio, ingresos)
    ]

    return {
        "periodos": [_etiqueta_trimestre(p) for p in periodos],
        "bpa": bpa,
        "ingresos": ingresos,
        "margen_neto": margen,
        "fcf": fcf,
    }


def _consenso_ponderable(consenso: dict) -> tuple[float | None, float]:
    """Devuelve (precio objetivo, multiplicador de peso 1 o 2).

    Peso doble si lo cubren >= CONSENSO_MIN_ANALISTAS analistas. Ya no se
    exige además unanimidad del 100%: con cobertura amplia esa condición
    casi nunca se cumplía (basta un solo "mantener" entre 45 analistas para
    desactivarla), dejando el peso doble inerte en la práctica incluso en
    los valores mejor cubiertos.
    """
    objetivo = consenso.get("precio_objetivo")
    if not es_valido(objetivo):
        return None, 1.0
    n = consenso.get("n_analistas")
    doble = es_valido(n) and float(n) >= CONSENSO_MIN_ANALISTAS
    return float(objetivo), (2.0 if doble else 1.0)


def _aplicar_banda_cordura(valores: dict, ancla: float | None) -> tuple[dict, dict]:
    """Recorta o excluye cada método según su distancia al ancla (consenso
    de analistas, o mediana de los métodos si no hay cobertura suficiente).

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
    """Combina DCF, múltiplos, EV/EBITDA sectorial, PEG y consenso en un
    único valor objetivo, pasando primero por la banda de cordura."""
    dcf, det_dcf = valorar_dcf(paquete)
    mult, det_mult = valorar_multiplos(paquete)
    ev_ebitda, det_ev_ebitda = valorar_ev_ebitda(paquete)
    peg_val, det_peg = valorar_peg(paquete)
    objetivo, multiplicador = _consenso_ponderable(paquete.get("consenso", {}))
    n_analistas = paquete.get("consenso", {}).get("n_analistas")

    valores_metodos = {"dcf": dcf, "multiplos": mult, "ev_ebitda": ev_ebitda, "peg": peg_val}

    if es_valido(objetivo) and es_valido(n_analistas) and float(n_analistas) >= BANDA_MIN_ANALISTAS:
        ancla = objetivo
    else:
        disponibles = [v for v in valores_metodos.values() if es_valido(v)]
        ancla = statistics.median(disponibles) if disponibles else None

    valores_ajustados, info_banda = _aplicar_banda_cordura(valores_metodos, ancla)

    pesos = dict(PESOS_FAIR_VALUE)
    pesos["consenso"] = pesos["consenso"] * multiplicador
    resultado = ponderar({**valores_ajustados, "consenso": objetivo}, pesos)

    precio = paquete.get("precio")
    fv = resultado["valor"]
    upside = ((fv / precio) - 1) * 100 if es_valido(fv) and es_valido(precio) and precio > 0 else None

    # Anotar en el detalle de cada método si la banda de cordura intervino,
    # para que la interfaz pueda mostrarlo junto a la fórmula.
    for clave, det in (
        ("dcf", det_dcf), ("multiplos", det_mult),
        ("ev_ebitda", det_ev_ebitda), ("peg", det_peg),
    ):
        if clave in info_banda["excluidos"]:
            original = info_banda["excluidos"][clave]
            det["banda_cordura"] = {"accion": "excluido", "valor_original": original, "ancla": ancla}
            det["notas"].append(
                f"Banda de cordura: {original:,.2f} \\$ se desvía demasiado del consenso/mediana "
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
                f"({'techo' if borde == 'techo' else 'suelo'} de la banda respecto al consenso/mediana)."
            )

    return {
        "fair_value": fv,
        "upside_pct": upside,
        "peso_consenso_doble": multiplicador == 2.0,
        "ancla_banda_cordura": ancla,
        "componentes": {
            "DCF": {"valor": dcf, "detalle": det_dcf},
            "Múltiplos": {"valor": mult, "detalle": det_mult},
            "EV/EBITDA sectorial": {"valor": ev_ebitda, "detalle": det_ev_ebitda},
            "Valoración PEG": {"valor": peg_val, "detalle": det_peg},
            "Consenso analistas": {
                "valor": objetivo,
                "detalle": {
                    "metodo": "Consenso",
                    "n_analistas": paquete.get("consenso", {}).get("n_analistas"),
                    "unanimidad": paquete.get("consenso", {}).get("unanimidad"),
                    "notas": [] if es_valido(objetivo) else ["Sin cobertura de analistas"],
                    "formula": (
                        f"Precio objetivo medio de {n_analistas:.0f} analistas"
                        + (" (⩾10 → peso doble en la media)" if multiplicador == 2.0 else "")
                        + f" → {objetivo:,.2f} \\$"
                        if es_valido(objetivo) and es_valido(n_analistas)
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
