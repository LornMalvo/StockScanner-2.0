"""Bloque 4: valor objetivo justo, Piotroski F-Score y puntuación de calidad.

Cada método de valoración devuelve `(valor, detalle)` donde `valor` puede ser
None. El combinador `calcular_fair_value` redistribuye los pesos de los métodos
que no han podido calcularse: jamás se introduce un 0 en la media.
"""

from __future__ import annotations

import statistics

import pandas as pd

from config.settings import (
    BANDAS_VALORACION,
    CONSENSO_MIN_ANALISTAS,
    DCF_ANIOS,
    DCF_CRECIMIENTO_MAX,
    DCF_CRECIMIENTO_MAX_ABSOLUTO,
    DCF_CRECIMIENTO_MAX_SECTOR,
    DCF_CRECIMIENTO_MIN,
    DCF_G_TERMINAL,
    DCF_WACC_DEFECTO,
    EV_EBITDA_MEDIANO_SECTOR,
    MARGEN_NETO_MEDIANO_SECTOR,
    PER_MEDIANO_SECTOR,
    PESOS_CALIDAD,
    PESOS_FAIR_VALUE,
    ROE_MEDIANO_SECTOR,
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
def valorar_dcf(paquete: dict) -> tuple[float | None, dict]:
    """Descuento de flujos de caja libres con crecimiento decreciente."""
    detalle = {"metodo": "DCF", "notas": []}
    estados = paquete.get("estados", {})
    info = paquete.get("info", {})

    fcf_serie = fila(estados.get("flujo_caja"), "Free Cash Flow")
    if fcf_serie is None:
        ocf = fila(estados.get("flujo_caja"), "Operating Cash Flow", "Total Cash From Operating Activities")
        capex = fila(estados.get("flujo_caja"), "Capital Expenditure", "Capital Expenditures")
        if ocf is not None and capex is not None:
            fcf_serie = (ocf + capex).dropna()

    fcf_base = valor_anio(fcf_serie) or primero_valido(info.get("freeCashflow"))
    if not es_valido(fcf_base) or fcf_base <= 0:
        detalle["notas"].append("Flujo de caja libre no disponible o negativo")
        return None, detalle

    acciones = primero_valido(info.get("sharesOutstanding"), info.get("impliedSharesOutstanding"))
    if not es_valido(acciones) or acciones <= 0:
        detalle["notas"].append("Número de acciones no disponible")
        return None, detalle

    # Crecimiento: estimación de analistas > CAGR histórico del FCF > 0 neutro.
    crecimiento = primero_valido(info.get("earningsGrowth"), info.get("revenueGrowth"))
    if not es_valido(crecimiento) and fcf_serie is not None and len(fcf_serie) >= 3:
        antiguo, reciente = valor_anio(fcf_serie, len(fcf_serie) - 1), fcf_base
        anios = len(fcf_serie) - 1
        if es_valido(antiguo) and antiguo > 0 and anios > 0:
            crecimiento = (reciente / antiguo) ** (1 / anios) - 1
    if not es_valido(crecimiento):
        detalle["notas"].append("Crecimiento no estimable; se usa el terminal")
        crecimiento = DCF_G_TERMINAL

    # Techo de crecimiento diferenciado por sector (en vez de un techo único
    # global): sectores de crecimiento estructural alto sostienen tasas más
    # altas sin que sea síntoma de exceso de optimismo. Si además hay
    # cobertura amplia de analistas (>= CONSENSO_MIN_ANALISTAS), se relaja
    # un 25% adicional sobre el techo del sector, con un tope absoluto de
    # seguridad: un consenso amplio corrobora de forma independiente que ese
    # crecimiento es sostenible, no un caso aislado o una lectura puntual
    # del dato de yfinance.
    techo_sector = DCF_CRECIMIENTO_MAX_SECTOR.get(paquete.get("sector"), DCF_CRECIMIENTO_MAX)
    n_analistas = paquete.get("consenso", {}).get("n_analistas")
    if es_valido(n_analistas) and float(n_analistas) >= CONSENSO_MIN_ANALISTAS:
        techo_crecimiento = min(techo_sector * 1.25, DCF_CRECIMIENTO_MAX_ABSOLUTO)
        detalle["notas"].append(
            f"Techo de crecimiento ampliado a {techo_crecimiento * 100:.0f}% "
            f"por alta cobertura de analistas (\u2265{CONSENSO_MIN_ANALISTAS})"
        )
    else:
        techo_crecimiento = techo_sector

    crecimiento = max(DCF_CRECIMIENTO_MIN, min(techo_crecimiento, float(crecimiento)))
    wacc = DCF_WACC_DEFECTO
    beta = primero_valido(info.get("beta"))
    if es_valido(beta):
        wacc = max(0.06, min(0.14, 0.042 + float(beta) * 0.045))  # CAPM simplificado

    caja = primero_valido(info.get("totalCash")) or 0.0
    deuda = primero_valido(info.get("totalDebt")) or 0.0

    valor_presente = 0.0
    flujo = fcf_base
    for anio in range(1, DCF_ANIOS + 1):
        g = crecimiento * (1 - (anio - 1) / DCF_ANIOS) + DCF_G_TERMINAL * ((anio - 1) / DCF_ANIOS)
        flujo *= 1 + g
        valor_presente += flujo / (1 + wacc) ** anio

    if wacc <= DCF_G_TERMINAL:
        detalle["notas"].append("WACC inferior al crecimiento terminal: DCF descartado")
        return None, detalle

    terminal = flujo * (1 + DCF_G_TERMINAL) / (wacc - DCF_G_TERMINAL)
    valor_presente += terminal / (1 + wacc) ** DCF_ANIOS
    equity = valor_presente + caja - deuda
    por_accion = equity / acciones

    detalle.update(
        {
            "fcf_base": fcf_base,
            "crecimiento": crecimiento,
            "wacc": wacc,
            "valor_empresa": valor_presente,
            "valor_accion": por_accion,
        }
    )
    return (por_accion if por_accion > 0 else None), detalle


def valorar_multiplos(paquete: dict) -> tuple[float | None, dict]:
    """PER justo = mediana entre PER histórico propio y PER sectorial."""
    detalle = {"metodo": "Múltiplos", "notas": []}
    info = paquete.get("info", {})

    bpa = primero_valido(info.get("forwardEps"), info.get("trailingEps"))
    if not es_valido(bpa) or bpa <= 0:
        detalle["notas"].append("BPA no disponible o negativo")
        return None, detalle

    per_sector = PER_MEDIANO_SECTOR.get(paquete.get("sector"))
    per_historico = calcular_per_historico(paquete)
    candidatos = [p for p in (per_sector, per_historico) if es_valido(p) and 0 < p < 60]
    if not candidatos:
        detalle["notas"].append("Sin referencia de PER sectorial ni histórica")
        return None, detalle

    per_justo = sum(candidatos) / len(candidatos)
    detalle.update(
        {
            "bpa": bpa,
            "per_sector": per_sector,
            "per_historico_5a": per_historico,
            "per_justo": per_justo,
            "valor_accion": per_justo * bpa,
        }
    )
    return per_justo * bpa, detalle


def valorar_ev_ebitda(paquete: dict) -> tuple[float | None, dict]:
    """EV/EBITDA sectorial. Sustituye al DDM (retirado: solo aplicaba a
    empresas con dividendo y quedaba inútil en el resto de casos).

    Equity Value = EBITDA x múltiplo objetivo del sector - Deuda neta;
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
    """
    detalle = {"metodo": "EV/EBITDA", "notas": []}
    info = paquete.get("info", {})

    ebitda = primero_valido(info.get("ebitda"))
    if not es_valido(ebitda) or ebitda <= 0:
        detalle["notas"].append("EBITDA no disponible o negativo")
        return None, detalle

    multiplo_sector = EV_EBITDA_MEDIANO_SECTOR.get(paquete.get("sector"))
    if not es_valido(multiplo_sector):
        detalle["notas"].append("Sin múltiplo EV/EBITDA de referencia para el sector")
        return None, detalle

    acciones = primero_valido(info.get("sharesOutstanding"), info.get("impliedSharesOutstanding"))
    if not es_valido(acciones) or acciones <= 0:
        detalle["notas"].append("Número de acciones no disponible")
        return None, detalle

    deuda_neta = (primero_valido(info.get("totalDebt")) or 0.0) - (primero_valido(info.get("totalCash")) or 0.0)
    equity_value = ebitda * multiplo_sector - deuda_neta
    por_accion = equity_value / acciones

    detalle.update(
        {
            "ebitda": ebitda,
            "multiplo_sector": multiplo_sector,
            "deuda_neta": deuda_neta,
            "equity_value": equity_value,
            "valor_accion": por_accion,
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


def calcular_fair_value(paquete: dict) -> dict:
    """Combina DCF, múltiplos, EV/EBITDA sectorial y consenso en un único
    valor objetivo."""
    dcf, det_dcf = valorar_dcf(paquete)
    mult, det_mult = valorar_multiplos(paquete)
    ev_ebitda, det_ev_ebitda = valorar_ev_ebitda(paquete)
    objetivo, multiplicador = _consenso_ponderable(paquete.get("consenso", {}))

    pesos = dict(PESOS_FAIR_VALUE)
    pesos["consenso"] = pesos["consenso"] * multiplicador
    resultado = ponderar(
        {"dcf": dcf, "multiplos": mult, "ev_ebitda": ev_ebitda, "consenso": objetivo}, pesos
    )

    precio = paquete.get("precio")
    fv = resultado["valor"]
    upside = ((fv / precio) - 1) * 100 if es_valido(fv) and es_valido(precio) and precio > 0 else None

    return {
        "fair_value": fv,
        "upside_pct": upside,
        "peso_consenso_doble": multiplicador == 2.0,
        "componentes": {
            "DCF": {"valor": dcf, "detalle": det_dcf},
            "Múltiplos": {"valor": mult, "detalle": det_mult},
            "EV/EBITDA sectorial": {"valor": ev_ebitda, "detalle": det_ev_ebitda},
            "Consenso analistas": {
                "valor": objetivo,
                "detalle": {
                    "metodo": "Consenso",
                    "n_analistas": paquete.get("consenso", {}).get("n_analistas"),
                    "unanimidad": paquete.get("consenso", {}).get("unanimidad"),
                    "notas": [] if es_valido(objetivo) else ["Sin cobertura de analistas"],
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


# ------------------------------------------------------ Piotroski F-Score ---
def piotroski_f_score(paquete: dict) -> dict:
    """9 criterios de Piotroski. Los no evaluables no suman ni restan."""
    estados = paquete.get("estados", {})
    resultados, balance, flujo = (
        estados.get("resultados"),
        estados.get("balance"),
        estados.get("flujo_caja"),
    )

    beneficio = fila(resultados, "Net Income", "Net Income Common Stockholders")
    activos = fila(balance, "Total Assets")
    ocf = fila(flujo, "Operating Cash Flow", "Total Cash From Operating Activities")
    deuda_lp = fila(balance, "Long Term Debt", "Long Term Debt And Capital Lease Obligation")
    circulante = fila(balance, "Current Assets", "Total Current Assets")
    pasivo_circ = fila(balance, "Current Liabilities", "Total Current Liabilities")
    acciones = fila(balance, "Ordinary Shares Number", "Share Issued")
    ingresos = fila(resultados, "Total Revenue", "Operating Revenue")
    bruto = fila(resultados, "Gross Profit")

    def roa(i: int) -> float | None:
        b, a = valor_anio(beneficio, i), valor_anio(activos, i)
        return b / a if es_valido(b) and es_valido(a) and a else None

    criterios: dict[str, bool | None] = {}

    criterios["ROA positivo"] = (lambda x: x > 0 if es_valido(x) else None)(roa(0))
    ocf0, act0 = valor_anio(ocf, 0), valor_anio(activos, 0)
    criterios["Flujo de caja operativo positivo"] = ocf0 > 0 if es_valido(ocf0) else None
    r0, r1 = roa(0), roa(1)
    criterios["ROA creciente"] = r0 > r1 if es_valido(r0) and es_valido(r1) else None
    criterios["Calidad del beneficio (FCO > Beneficio neto)"] = (
        ocf0 > valor_anio(beneficio, 0)
        if es_valido(ocf0) and es_valido(valor_anio(beneficio, 0))
        else None
    )

    dl0, dl1 = valor_anio(deuda_lp, 0), valor_anio(deuda_lp, 1)
    a0, a1 = valor_anio(activos, 0), valor_anio(activos, 1)
    if all(es_valido(x) for x in (dl0, dl1, a0, a1)) and a0 and a1:
        criterios["Apalancamiento decreciente"] = (dl0 / a0) <= (dl1 / a1)
    else:
        criterios["Apalancamiento decreciente"] = None

    c0, p0, c1, p1 = (
        valor_anio(circulante, 0),
        valor_anio(pasivo_circ, 0),
        valor_anio(circulante, 1),
        valor_anio(pasivo_circ, 1),
    )
    if all(es_valido(x) for x in (c0, p0, c1, p1)) and p0 and p1:
        criterios["Liquidez corriente creciente"] = (c0 / p0) > (c1 / p1)
    else:
        criterios["Liquidez corriente creciente"] = None

    ac0, ac1 = valor_anio(acciones, 0), valor_anio(acciones, 1)
    criterios["Sin dilución de accionistas"] = (
        ac0 <= ac1 * 1.01 if es_valido(ac0) and es_valido(ac1) else None
    )

    b0, i0, b1, i1 = (
        valor_anio(bruto, 0),
        valor_anio(ingresos, 0),
        valor_anio(bruto, 1),
        valor_anio(ingresos, 1),
    )
    if all(es_valido(x) for x in (b0, i0, b1, i1)) and i0 and i1:
        criterios["Margen bruto creciente"] = (b0 / i0) > (b1 / i1)
    else:
        criterios["Margen bruto creciente"] = None

    if all(es_valido(x) for x in (i0, a0, i1, a1)) and a0 and a1:
        criterios["Rotación de activos creciente"] = (i0 / a0) > (i1 / a1)
    else:
        criterios["Rotación de activos creciente"] = None

    evaluados = {k: v for k, v in criterios.items() if v is not None}
    puntos = sum(1 for v in evaluados.values() if v)
    return {
        "criterios": criterios,
        "puntos": puntos,
        "evaluados": len(evaluados),
        "normalizado": (puntos / len(evaluados) * 9) if evaluados else None,
    }


# --------------------------------------------- puntuación de calidad 0-100 --
def puntuar_calidad(paquete: dict, fair_value: dict) -> dict:
    """Algoritmo determinista de salud fundamental (0-100)."""
    info = paquete.get("info", {})
    sector = paquete.get("sector")
    estados = paquete.get("estados", {})

    piotroski = piotroski_f_score(paquete)
    sub: dict[str, float | None] = {}
    lecturas: dict[str, float | None] = {}

    # 1. Piotroski normalizado a 0-100
    sub["piotroski"] = (
        piotroski["normalizado"] / 9 * 100 if es_valido(piotroski["normalizado"]) else None
    )
    lecturas["piotroski"] = piotroski["puntos"]

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

    # 11. Calidad del beneficio: FCF / Beneficio neto
    fcf = primero_valido(info.get("freeCashflow"))
    neto = primero_valido(info.get("netIncomeToCommon"), valor_anio(beneficio, 0))
    calidad_beneficio = fcf / neto if es_valido(fcf) and es_valido(neto) and neto > 0 else None
    lecturas["fcf_sobre_beneficio"] = calidad_beneficio
    if es_valido(calidad_beneficio):
        sub["calidad_beneficio"] = escalar(calidad_beneficio, 0.4, 1.2)

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

    resultado = ponderar(sub, PESOS_CALIDAD)
    return {
        "puntuacion": round(resultado["valor"], 1) if es_valido(resultado["valor"]) else None,
        "subpuntuaciones": sub,
        "lecturas": lecturas,
        "excluidos": resultado["excluidos"],
        "cobertura": resultado["cobertura"],
        "piotroski": piotroski,
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
