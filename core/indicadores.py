"""Indicadores técnicos implementados con pandas/numpy.

Se evita TA-Lib a propósito: requiere compilación nativa y Streamlit Community
Cloud no la soporta sin fricción. Todas las funciones devuelven None cuando no
hay histórico suficiente, nunca un 0.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from config.settings import (
    ATR_PERCENTIL_VENTANA,
    CRUCE_PROXIMO_PCT,
    CRUCE_VENTANA_BUSQUEDA,
    CRUCE_VENTANA_PENDIENTE,
    DIAGONAL_MIN_TOQUES,
    DIAGONAL_SESIONES,
    DIAGONAL_TOLERANCIA_ATR,
    FUERZA_RELATIVA_SESIONES,
    NIVEL_REDONDO_MAX,
    PIVOTE_VENTANA_SEMANAL,
    VOLUMEN_SESIONES_RECIENTES,
    VP_BANDAS,
    VP_SESIONES,
    VP_VALUE_AREA_PCT,
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
def _agrupar_toques(
    serie: pd.Series, tolerancia_abs: float | None, fecha_final=None
) -> list[dict]:
    """Convierte pivotes locales sueltos en niveles con recuento de toques.

    Dos pivotes que caen casi al mismo precio no son dos soportes distintos:
    son el MISMO soporte tocado dos veces, y eso es justamente la señal de
    fiabilidad que interesa (un nivel respetado tres veces vale más que uno
    tocado una sola vez). Devuelve, por nivel: precio medio, nº de toques y
    fecha del toque más reciente —esta última alimenta la decadencia por
    antigüedad del motor de confluencia—.
    """
    limpio = serie.dropna()
    if limpio.empty:
        return []
    puntos = sorted(((float(v), f) for f, v in limpio.items()), key=lambda x: x[0])
    if not tolerancia_abs or tolerancia_abs <= 0:
        referencia = puntos[len(puntos) // 2][0]
        tolerancia_abs = abs(referencia) * 0.015

    niveles: list[dict] = []
    for precio, fecha in puntos:
        if niveles and abs(precio - niveles[-1]["precio"]) <= tolerancia_abs:
            n = niveles[-1]
            n["precio"] = (n["precio"] * n["toques"] + precio) / (n["toques"] + 1)
            n["toques"] += 1
            if fecha > n["fecha"]:
                n["fecha"] = fecha
        else:
            niveles.append({"precio": precio, "toques": 1, "fecha": fecha})

    # La antigüedad se calcula aquí, no en `plan_dca`: el motor de confluencia
    # recibe solo números y no debe saber nada de Timestamps ni de pandas.
    referencia = fecha_final if fecha_final is not None else limpio.index[-1]
    for n in niveles:
        try:
            n["antiguedad_anos"] = max(0.0, (referencia - n["fecha"]).days / 365.25)
        except (TypeError, AttributeError):
            n["antiguedad_anos"] = None
    return niveles


def pivotes(
    df: pd.DataFrame, ventana: int = 10, tolerancia_abs: float | None = None
) -> dict[str, list]:
    """Máximos y mínimos locales usados como resistencias y soportes.

    Las claves `soportes`/`resistencias` se mantienen como listas planas de
    precios por retrocompatibilidad. Las claves `detalle_*` añaden, por nivel,
    el nº de toques y la fecha del más reciente, que el motor de confluencia
    usa para ponderar fiabilidad y antigüedad.
    """
    alto, bajo = df["High"], df["Low"]
    max_local = alto[(alto == alto.rolling(ventana * 2 + 1, center=True).max())]
    min_local = bajo[(bajo == bajo.rolling(ventana * 2 + 1, center=True).min())]
    return {
        "resistencias": sorted(round(float(v), 4) for v in max_local.dropna().unique()),
        "soportes": sorted(round(float(v), 4) for v in min_local.dropna().unique()),
        "detalle_resistencias": _agrupar_toques(max_local, tolerancia_abs, df.index[-1]),
        "detalle_soportes": _agrupar_toques(min_local, tolerancia_abs, df.index[-1]),
    }


def pivotes_semanales(df: pd.DataFrame, ventana: int = 4) -> dict[str, list]:
    """Los mismos pivotes, pero sobre velas SEMANALES (multi-temporalidad).

    Un mínimo que existe tanto en diario como en semanal es estructuralmente
    más fiable: no es ruido de una sesión suelta, es una zona que aguantó
    varias semanas. El motor de confluencia los emite como candidatos de peso
    superior al pivote diario, y al caer en el mismo precio se funden con él
    reforzando la zona.
    """
    if df is None or df.empty or len(df) < 60:
        return {"soportes": [], "resistencias": [], "detalle_soportes": [], "detalle_resistencias": []}
    semanal = df.resample("W-FRI").agg(
        {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}
    ).dropna(subset=["High", "Low"])
    if len(semanal) < ventana * 2 + 3:
        return {"soportes": [], "resistencias": [], "detalle_soportes": [], "detalle_resistencias": []}
    return pivotes(semanal, ventana=ventana)


def volume_profile(
    df: pd.DataFrame, bandas: int = 60, sesiones: int = 504, value_area_pct: float = 0.70
) -> dict:
    """Perfil de volumen por bandas de precio: POC y Value Area.

    Diferencia "el precio pasó por aquí" de "aquí se acumuló posición de
    verdad", que es la pieza que más fiabilidad añade al motor de confluencia
    y la única fuente que no depende de dónde tocó el precio sino de cuánto se
    negoció. Sin coste de API: `Volume` ya viene en el histórico de yfinance.

    El volumen de cada sesión se reparte PROPORCIONALMENTE entre todas las
    bandas que cruza su rango High-Low, en vez de asignarse entero al cierre:
    una sesión de rango amplio no debe concentrar todo su volumen en un único
    precio en el que apenas cotizó.
    """
    if df is None or df.empty or "Volume" not in df or len(df) < 30:
        return {}
    tramo = df.tail(sesiones)
    bajo, alto = float(tramo["Low"].min()), float(tramo["High"].max())
    if not np.isfinite(bajo) or not np.isfinite(alto) or alto <= bajo:
        return {}

    bordes = np.linspace(bajo, alto, bandas + 1)
    centros = (bordes[:-1] + bordes[1:]) / 2
    acumulado = np.zeros(bandas)
    ancho_banda = (alto - bajo) / bandas

    for low, high, vol in zip(tramo["Low"].values, tramo["High"].values, tramo["Volume"].values):
        if not np.isfinite(low) or not np.isfinite(high) or not np.isfinite(vol) or vol <= 0:
            continue
        low, high = float(low), float(high)
        if high < low:
            low, high = high, low
        solape = np.clip(np.minimum(bordes[1:], high) - np.maximum(bordes[:-1], low), 0, None)
        total = solape.sum()
        if total > 0:
            acumulado += vol * solape / total
        else:  # sesión sin rango (low == high): cae entera en su banda
            idx = min(int((low - bajo) / ancho_banda), bandas - 1)
            acumulado[idx] += vol

    if acumulado.sum() <= 0:
        return {}

    i_poc = int(np.argmax(acumulado))
    objetivo = acumulado.sum() * value_area_pct
    incluidas = {i_poc}
    dentro = acumulado[i_poc]
    izq, der = i_poc - 1, i_poc + 1
    while dentro < objetivo and (izq >= 0 or der < bandas):
        v_izq = acumulado[izq] if izq >= 0 else -1
        v_der = acumulado[der] if der < bandas else -1
        if v_der >= v_izq:
            incluidas.add(der)
            dentro += v_der
            der += 1
        else:
            incluidas.add(izq)
            dentro += v_izq
            izq -= 1

    indices = sorted(incluidas)
    return {
        "poc": float(centros[i_poc]),
        "val": float(centros[indices[0]]),
        "vah": float(centros[indices[-1]]),
        "ancho_banda": float(ancho_banda),
        "volumen_poc_pct": float(acumulado[i_poc] / acumulado.sum() * 100),
    }


def atr_percentil(df: pd.DataFrame, ventana_atr: int = 14, ventana: int = 504) -> float | None:
    """Percentil (0-100) del ATR relativo actual frente a su propia historia.

    Un ATR de 5,4 no significa lo mismo si es el más alto de los últimos dos
    años (mercado nervioso, los niveles se rompen con facilidad) que si es el
    más bajo (mercado tranquilo, los niveles se respetan). Se mide en ATR/precio
    y no en ATR absoluto para que la comparación siga siendo válida aunque la
    acción se haya multiplicado por tres en el periodo.
    """
    if df is None or df.empty or len(df) < 60:
        return None
    serie = (atr(df, ventana_atr) / df["Close"]).dropna().tail(ventana)
    if len(serie) < 40:
        return None
    actual = float(serie.iloc[-1])
    return float((serie <= actual).sum() / len(serie) * 100)


def niveles_redondos(precio: float, cantidad: int = 3) -> list[float]:
    """Números redondos cercanos al precio (50 $, 100 $, 150 $...).

    Como factor único son poco fiables, pero existen: hay órdenes reales
    apiladas en ellos. En el motor entran con peso bajo, sirviendo de
    desempate cuando coinciden con una zona que ya tiene otra evidencia.
    El paso se escala con la magnitud del precio: para una acción de 4 $ los
    redondos relevantes son 0,50 $, no 50 $.
    """
    if not np.isfinite(precio) or precio <= 0:
        return []
    magnitud = 10 ** np.floor(np.log10(precio))
    paso = magnitud / 2 if precio / magnitud < 2 else magnitud
    base = np.floor(precio / paso) * paso
    salida = []
    for k in range(-cantidad, cantidad + 1):
        nivel = base + k * paso
        if nivel > 0 and abs(nivel - precio) / precio > 0.005:
            salida.append(round(float(nivel), 6))
    return sorted(set(salida))


def diagonales(
    df: pd.DataFrame,
    ventana_pivote: int = 10,
    sesiones: int = 378,
    min_toques: int = 3,
    tolerancia_atr: float = 0.75,
) -> list[dict]:
    """Líneas de tendencia DIAGONALES proyectadas al día de hoy.

    Todo el resto del motor trabaja con niveles horizontales, pero en una
    tendencia clara el soporte real es una diagonal que se desplaza con el
    tiempo. Se prueban todas las rectas que unen dos pivotes, se cuenta cuántos
    otros pivotes quedan a menos de `tolerancia_atr` ATR de la recta, y se
    conservan las que acumulan al menos `min_toques`. La salida es el valor que
    la recta toma HOY, de modo que el resto del motor la trata como un
    candidato de precio más, sin lógica especial.

    Se descartan las rectas que el precio ya ha perforado de forma clara: una
    directriz rota deja de ser soporte (y suele pasar a ser resistencia, cosa
    que aquí no se modela: se prefiere no emitir el candidato a emitirlo mal).
    """
    if df is None or df.empty or len(df) < 90:
        return []
    tramo = df.tail(sesiones)
    atr_actual = atr(tramo).dropna()
    if atr_actual.empty:
        return []
    tol = float(atr_actual.iloc[-1]) * tolerancia_atr
    if not np.isfinite(tol) or tol <= 0:
        return []

    x = np.arange(len(tramo), dtype=float)
    hoy = float(len(tramo) - 1)
    alto, bajo = tramo["High"], tramo["Low"]
    ancho = ventana_pivote * 2 + 1
    max_local = alto == alto.rolling(ancho, center=True).max()
    min_local = bajo == bajo.rolling(ancho, center=True).min()

    salida: list[dict] = []
    for tipo, mascara, serie, penaliza in (
        ("soporte", min_local, bajo, alto),
        ("resistencia", max_local, alto, bajo),
    ):
        idx = np.where(mascara.fillna(False).values)[0]
        if len(idx) < min_toques:
            continue
        valores = serie.values
        mejores: list[dict] = []
        for a in range(len(idx)):
            for b in range(a + 1, len(idx)):
                i, j = idx[a], idx[b]
                if j - i < ventana_pivote:
                    continue
                pendiente = (valores[j] - valores[i]) / (j - i)
                recta = valores[i] + pendiente * (x - i)
                toques = int(np.sum(np.abs(valores[idx] - recta[idx]) <= tol))
                if toques < min_toques:
                    continue
                # Perforación: el precio ha cerrado claramente al otro lado.
                desde = int(i)
                if tipo == "soporte":
                    roto = np.sum(penaliza.values[desde:] < recta[desde:] - tol)
                else:
                    roto = np.sum(penaliza.values[desde:] > recta[desde:] + tol)
                if roto > max(3, (len(tramo) - desde) * 0.05):
                    continue
                proyeccion = float(valores[i] + pendiente * (hoy - i))
                if not np.isfinite(proyeccion) or proyeccion <= 0:
                    continue
                mejores.append(
                    {
                        "tipo": tipo,
                        "precio": proyeccion,
                        "toques": toques,
                        "pendiente_pct": float(pendiente / valores[i] * 100) if valores[i] else 0.0,
                    }
                )
        mejores.sort(key=lambda d: (-d["toques"], abs(d["pendiente_pct"])))
        # Se conservan como mucho dos por tipo, y no dos casi idénticas.
        elegidas: list[dict] = []
        for cand in mejores:
            if all(abs(cand["precio"] - e["precio"]) > tol for e in elegidas):
                elegidas.append(cand)
            if len(elegidas) >= 2:
                break
        salida.extend(elegidas)
    return salida


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
        "pivotes": pivotes(df, tolerancia_abs=_ultimo(atr_s)),
        "pivotes_semanales": pivotes_semanales(df, PIVOTE_VENTANA_SEMANAL),
        "fibonacci": fibonacci(min_52, max_52) if min_52 and max_52 else {},
        "gaps": gaps_sin_rellenar(df),
        # --- fuentes del motor de confluencia rediseñado -------------------
        # Se calculan aquí y no en `plan_dca` a propósito: el motor DCA recibe
        # únicamente este diccionario, nunca el DataFrame. Mantener el cálculo
        # en la capa de indicadores respeta la separación de capas y evita
        # cambiar la firma de `plan_dca.zonas_confluencia_soporte()`, que es el
        # punto de acoplamiento con `core/timing.py`.
        "volume_profile": volume_profile(df, VP_BANDAS, VP_SESIONES, VP_VALUE_AREA_PCT),
        "atr_percentil": atr_percentil(df, ventana=ATR_PERCENTIL_VENTANA),
        "diagonales": diagonales(
            df,
            sesiones=DIAGONAL_SESIONES,
            min_toques=DIAGONAL_MIN_TOQUES,
            tolerancia_atr=DIAGONAL_TOLERANCIA_ATR,
        ),
        "niveles_redondos": niveles_redondos(precio, NIVEL_REDONDO_MAX) if precio else [],
    }
