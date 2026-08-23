"""Indicadores técnicos implementados con pandas/numpy.

Se evita TA-Lib a propósito: requiere compilación nativa y Streamlit Community
Cloud no la soporta sin fricción. Todas las funciones devuelven None cuando no
hay histórico suficiente, nunca un 0.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from config.settings import (
    CRUCE_PROXIMO_PCT,
    CRUCE_VENTANA_BUSQUEDA,
    CRUCE_VENTANA_PENDIENTE,
    FUERZA_RELATIVA_SESIONES,
    VOLUMEN_SESIONES_RECIENTES,
)


# ------------------------------------------------------------- básicos ------
def sma(serie: pd.Series, ventana: int) -> pd.Series:
    return serie.rolling(window=ventana, min_periods=ventana).mean()


def ema(serie: pd.Series, ventana: int) -> pd.Series:
    return serie.ewm(span=ventana, adjust=False).mean()


def rsi(serie: pd.Series, ventana: int = 14) -> pd.Series:
    delta = serie.diff()
    ganancia = delta.clip(lower=0)
    perdida = -delta.clip(upper=0)
    media_g = ganancia.ewm(alpha=1 / ventana, adjust=False).mean()
    media_p = perdida.ewm(alpha=1 / ventana, adjust=False).mean()
    rs = media_g / media_p.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def macd(serie: pd.Series, rapida: int = 12, lenta: int = 26, senal: int = 9) -> pd.DataFrame:
    linea = ema(serie, rapida) - ema(serie, lenta)
    linea_senal = ema(linea, senal)
    return pd.DataFrame(
        {"macd": linea, "senal": linea_senal, "histograma": linea - linea_senal}
    )


def atr(df: pd.DataFrame, ventana: int = 14) -> pd.Series:
    alto, bajo, cierre = df["High"], df["Low"], df["Close"]
    tr = pd.concat(
        [alto - bajo, (alto - cierre.shift()).abs(), (bajo - cierre.shift()).abs()],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1 / ventana, adjust=False).mean()


def adx(df: pd.DataFrame, ventana: int = 14) -> pd.DataFrame:
    """ADX junto con sus dos direccionales (+DI y −DI).

    Devuelve el DataFrame completo y no solo la línea ADX porque el ADX mide
    FUERZA de tendencia, no dirección: sin +DI/−DI, un ADX de 30 en plena
    caída es indistinguible de un ADX de 30 en plena subida. Quien puntúe el
    ADX necesita las tres series para saber hacia dónde apunta esa fuerza.
    """
    alto, bajo = df["High"], df["Low"]
    up = alto.diff()
    down = -bajo.diff()
    plus_dm = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)
    tr = atr(df, ventana)
    plus_di = 100 * pd.Series(plus_dm, index=df.index).ewm(
        alpha=1 / ventana, adjust=False
    ).mean() / tr.replace(0, np.nan)
    minus_di = 100 * pd.Series(minus_dm, index=df.index).ewm(
        alpha=1 / ventana, adjust=False
    ).mean() / tr.replace(0, np.nan)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return pd.DataFrame(
        {
            "adx": dx.ewm(alpha=1 / ventana, adjust=False).mean(),
            "di_mas": plus_di,
            "di_menos": minus_di,
        }
    )


def obv(df: pd.DataFrame) -> pd.Series:
    direccion = np.sign(df["Close"].diff()).fillna(0)
    return (direccion * df["Volume"]).cumsum()


# ------------------------------------------------- estructura de precios ----
def pivotes(df: pd.DataFrame, ventana: int = 10) -> dict[str, list[float]]:
    """Máximos y mínimos locales usados como resistencias y soportes."""
    alto, bajo = df["High"], df["Low"]
    max_local = alto[(alto == alto.rolling(ventana * 2 + 1, center=True).max())]
    min_local = bajo[(bajo == bajo.rolling(ventana * 2 + 1, center=True).min())]
    return {
        "resistencias": sorted(round(float(v), 4) for v in max_local.dropna().unique()),
        "soportes": sorted(round(float(v), 4) for v in min_local.dropna().unique()),
    }


def fibonacci(minimo: float, maximo: float) -> dict[str, float]:
    rango = maximo - minimo
    return {
        "0.236": maximo - rango * 0.236,
        "0.382": maximo - rango * 0.382,
        "0.500": maximo - rango * 0.500,
        "0.618": maximo - rango * 0.618,
        "0.786": maximo - rango * 0.786,
    }


def gaps_sin_rellenar(df: pd.DataFrame, umbral: float = 0.02, maximo: int = 8) -> list[dict]:
    """Huecos de apertura que el precio todavía no ha vuelto a cubrir."""
    salida: list[dict] = []
    cierre_prev = df["Close"].shift()
    apertura = df["Open"]
    for fecha in df.index[1:]:
        cp, ap = cierre_prev.get(fecha), apertura.get(fecha)
        if pd.isna(cp) or pd.isna(ap) or cp <= 0:
            continue
        salto = (ap - cp) / cp
        if abs(salto) < umbral:
            continue
        posterior = df.loc[fecha:]
        if salto > 0 and posterior["Low"].min() <= cp:
            continue  # gap alcista ya rellenado
        if salto < 0 and posterior["High"].max() >= cp:
            continue  # gap bajista ya rellenado
        salida.append(
            {
                "fecha": fecha,
                "desde": float(min(cp, ap)),
                "hasta": float(max(cp, ap)),
                "tipo": "alcista" if salto > 0 else "bajista",
            }
        )
    return salida[-maximo:]


# --------------------------------------------------- volumen y contexto -----
def volumen_relativo(df: pd.DataFrame, sesiones: int = 5, referencia: int = 63) -> float | None:
    """Volumen medio de las últimas `sesiones` frente a la media de 3 meses.

    Un 1,0 significa "volumen normal"; 1,5 es un 50% por encima de lo
    habitual. Por sí solo no dice si es bueno o malo: hay que cruzarlo con la
    dirección del precio (capitulación vs. euforia), cosa que hace el motor
    de timing, no este indicador.
    """
    if "Volume" not in df or len(df) < referencia:
        return None
    reciente = df["Volume"].tail(sesiones).mean()
    base = df["Volume"].tail(referencia).mean()
    if not base or pd.isna(base) or pd.isna(reciente) or base <= 0:
        return None
    return float(reciente / base)


def variacion_pct(serie: pd.Series, sesiones: int) -> float | None:
    """Variación porcentual del cierre en las últimas `sesiones` sesiones."""
    limpio = serie.dropna()
    if len(limpio) <= sesiones:
        return None
    anterior = float(limpio.iloc[-sesiones - 1])
    if anterior <= 0:
        return None
    return float((float(limpio.iloc[-1]) / anterior - 1) * 100)


def fuerza_relativa(cierre: pd.Series, cierre_ref: pd.Series, sesiones: int = 63) -> float | None:
    """Diferencial de rentabilidad (en puntos porcentuales) frente a la
    referencia sectorial o de mercado en la misma ventana temporal.

    Positivo = el valor lo ha hecho mejor que su sector; negativo = peor. Se
    calcula solo sobre las fechas comunes a ambas series para que un festivo
    de un mercado no descuadre la comparación.
    """
    if cierre is None or cierre_ref is None or cierre.empty or cierre_ref.empty:
        return None
    comun = cierre.dropna().index.intersection(cierre_ref.dropna().index)
    if len(comun) <= sesiones:
        return None
    a = cierre.reindex(comun).tail(sesiones + 1)
    b = cierre_ref.reindex(comun).tail(sesiones + 1)
    if float(a.iloc[0]) <= 0 or float(b.iloc[0]) <= 0:
        return None
    ret_valor = (float(a.iloc[-1]) / float(a.iloc[0]) - 1) * 100
    ret_ref = (float(b.iloc[-1]) / float(b.iloc[0]) - 1) * 100
    return float(ret_valor - ret_ref)


def cruce_medias(
    mm50: pd.Series,
    mm200: pd.Series,
    ventana_busqueda: int = 120,
    ventana_pendiente: int = 10,
    proximo_pct: float = 3.0,
) -> dict:
    """Estado del cruce entre MM50 y MM200 (Golden Cross / Death Cross).

    PURAMENTE INFORMATIVO: no genera puntuación, no tiene peso propio en
    `PESOS_TIMING`. La fuerza y dirección de tendencia que un cruce refleja
    ya las captura el ADX direccional, y la distancia del precio a cada
    media ya la capturan `mm50`/`mm200`; darle un peso propio duplicaría esa
    señal en vez de aportar una nueva (mismo problema que llevó a fundir
    `margen_seguridad` en `upside`).

    Devuelve:
      - `estado_actual`: "alcista" (MM50 > MM200) o "bajista" (MM50 < MM200)
        en este momento, con independencia de cuándo se cruzaron.
      - `distancia_pct`: separación entre ambas medias, en % sobre la MM200.
      - `sesiones_desde_cruce` / `tipo_ultimo_cruce`: si hay un cambio de
        signo dentro de `ventana_busqueda` sesiones, cuántas lleva y si fue
        "golden" o "death". `None` si el estado actual viene de más atrás.
      - `proximo_a_cruzar`: True si las medias están cerca (`proximo_pct`) Y
        convergiendo hacia el cruce contrario al estado actual, no solo
        cerca por casualidad con tendencia a separarse de nuevo.
    """
    if mm50 is None or mm200 is None:
        return {}
    diff = (mm50 - mm200).dropna()
    if len(diff) < 2:
        return {}

    ultimo = float(diff.iloc[-1])
    mm200_ultimo = mm200.dropna()
    mm200_ultimo = float(mm200_ultimo.iloc[-1]) if len(mm200_ultimo) else None
    distancia_pct = (ultimo / mm200_ultimo * 100) if mm200_ultimo else None
    estado_actual = "alcista" if ultimo > 0 else ("bajista" if ultimo < 0 else None)

    ventana = diff.tail(ventana_busqueda)
    signo = np.sign(ventana.values)
    sesiones_cruce, tipo_cruce = None, None
    for i in range(len(signo) - 1, 0, -1):
        if signo[i] != 0 and signo[i - 1] != 0 and signo[i] != signo[i - 1]:
            sesiones_cruce = len(signo) - 1 - i
            tipo_cruce = "golden" if signo[i] > 0 else "death"
            break

    # Convergencia: el diferencial se acerca a cero (pendiente de signo
    # opuesto al estado actual), no simplemente "es pequeño" — un
    # diferencial pequeño que se está ALEJANDO de cero no es una
    # convergencia real, aunque hoy esté cerca.
    convergiendo = False
    tramo = diff.tail(ventana_pendiente)
    if len(tramo) >= ventana_pendiente:
        pendiente = float(np.polyfit(range(len(tramo)), tramo.values, 1)[0])
        if estado_actual == "alcista" and pendiente < 0:
            convergiendo = True
        elif estado_actual == "bajista" and pendiente > 0:
            convergiendo = True

    proximo = (
        convergiendo
        and distancia_pct is not None
        and abs(distancia_pct) <= proximo_pct
    )

    return {
        "estado_actual": estado_actual,
        "distancia_pct": distancia_pct,
        "sesiones_desde_cruce": sesiones_cruce,
        "tipo_ultimo_cruce": tipo_cruce,
        "convergiendo": convergiendo,
        "proximo_a_cruzar": proximo,
    }


# ------------------------------------------------------------ resumen -------
def _ultimo(serie: pd.Series) -> float | None:
    if serie is None or len(serie) == 0:
        return None
    valor = serie.dropna()
    return float(valor.iloc[-1]) if len(valor) else None


def calcular_todo(historico: pd.DataFrame, referencia: dict | None = None) -> dict:
    """Devuelve el paquete técnico completo a partir del histórico OHLCV.

    `referencia` es el paquete del ETF sectorial/de mercado
    (`datos_api.obtener_referencia_mercado`) usado para la fuerza relativa.
    Es opcional: sin él, todo lo demás se calcula igual y la fuerza relativa
    queda como dato no disponible (se excluye del timing, no se pone a cero).
    """
    if historico is None or historico.empty or len(historico) < 30:
        return {"disponible": False}

    df = historico.copy()
    cierre = df["Close"]
    macd_df = macd(cierre)
    rsi_s = rsi(cierre)
    adx_df = adx(df)
    obv_s = obv(df)
    atr_s = atr(df)
    mm50, mm200 = sma(cierre, 50), sma(cierre, 200)

    precio = _ultimo(cierre)
    ventana_52 = df.tail(252)
    max_52 = float(ventana_52["High"].max()) if len(ventana_52) else None
    min_52 = float(ventana_52["Low"].min()) if len(ventana_52) else None
    ath = float(df["High"].max())
    atl = float(df["Low"].min())

    # Pendiente del OBV en las últimas 20 sesiones, normalizada.
    obv_tendencia = None
    obv_limpio = obv_s.dropna()
    if len(obv_limpio) >= 20:
        tramo = obv_limpio.tail(20)
        escala = abs(tramo).mean()
        if escala:
            obv_tendencia = float(np.polyfit(range(len(tramo)), tramo.values, 1)[0] / escala)

    variacion_1a = None
    if len(cierre) >= 252 and cierre.iloc[-252] > 0:
        variacion_1a = float((precio / cierre.iloc[-252] - 1) * 100)

    hist_ref = (referencia or {}).get("historico")
    cierre_referencia = (
        hist_ref["Close"] if hist_ref is not None and not hist_ref.empty and "Close" in hist_ref
        else None
    )

    return {
        "disponible": True,
        "precio": precio,
        "series": {"macd": macd_df, "mm50": mm50, "mm200": mm200, "rsi": rsi_s},
        "rsi": _ultimo(rsi_s),
        "macd": _ultimo(macd_df["macd"]),
        "macd_senal": _ultimo(macd_df["senal"]),
        "macd_hist": _ultimo(macd_df["histograma"]),
        "macd_hist_prev": float(macd_df["histograma"].dropna().iloc[-2])
        if len(macd_df["histograma"].dropna()) > 1
        else None,
        "adx": _ultimo(adx_df["adx"]),
        "di_mas": _ultimo(adx_df["di_mas"]),
        "di_menos": _ultimo(adx_df["di_menos"]),
        "atr": _ultimo(atr_s),
        "obv": _ultimo(obv_s),
        "obv_tendencia": obv_tendencia,
        "mm50": _ultimo(mm50),
        "mm200": _ultimo(mm200),
        "max_52s": max_52,
        "min_52s": min_52,
        "ath": ath,
        "atl": atl,
        "variacion_1a_pct": variacion_1a,
        "variacion_corta_pct": variacion_pct(cierre, VOLUMEN_SESIONES_RECIENTES),
        "volumen_medio_3m": float(df["Volume"].tail(63).mean()) if "Volume" in df else None,
        "volumen_relativo": volumen_relativo(df, VOLUMEN_SESIONES_RECIENTES),
        "fuerza_relativa_pct": fuerza_relativa(
            cierre, cierre_referencia, FUERZA_RELATIVA_SESIONES
        )
        if cierre_referencia is not None
        else None,
        "referencia_simbolo": (referencia or {}).get("simbolo"),
        "referencia_nombre": (referencia or {}).get("nombre"),
        "cruce_medias": cruce_medias(
            mm50, mm200, CRUCE_VENTANA_BUSQUEDA, CRUCE_VENTANA_PENDIENTE, CRUCE_PROXIMO_PCT
        ),
        "pivotes": pivotes(df),
        "fibonacci": fibonacci(min_52, max_52) if min_52 and max_52 else {},
        "gaps": gaps_sin_rellenar(df),
    }
