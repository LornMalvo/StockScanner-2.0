"""Bloque 5: calidad del momento de entrada (0-100) y señal resultante.

Cada componente puntúa de 0 a 100 y se pondera según `PESOS_TIMING`. Los
componentes sin dato se excluyen y su peso se reparte entre los demás.

Además de la puntuación, el motor devuelve `lecturas`: el valor REAL de cada
métrica en el momento del análisis (RSI 36,6; ADX 23,4; volumen ×1,42…) para
que la interfaz pueda enseñarlo junto a la puntuación sin recalcular nada ni
duplicar la lógica.
"""

from __future__ import annotations

from config.settings import (
    CONFLUENCIA_ATR_CERCA,
    CONFLUENCIA_ATR_LEJOS,
    CONFLUENCIA_PCT_CERCA,
    CONFLUENCIA_PCT_LEJOS,
    DCA_CONFLUENCIA_FUERTE,
    PESOS_TIMING,
    SALUD_MINIMA_TIMING,
    SENIALES_TIMING,
    TIMING_TOPE_SIN_SALUD,
    VOLUMEN_VARIACION_NEUTRA,
)
from core import plan_dca
from utils.formato import dias_hasta, es_valido, escalar, ponderar, primero_valido


def _puntuar_rsi(rsi: float | None) -> float | None:
    """Óptimo en zona 30-45 (sobreventa reciente sin capitulación)."""
    if not es_valido(rsi):
        return None
    r = float(rsi)
    if r < 20:
        return 70.0            # sobreventa extrema: oportunidad con riesgo de cuchillo
    if r < 30:
        return 95.0
    if r < 45:
        return 85.0
    if r < 55:
        return 65.0
    if r < 65:
        return 45.0
    if r < 75:
        return 20.0
    return 5.0


def _puntuar_macd(tec: dict) -> float | None:
    macd, senal = tec.get("macd"), tec.get("macd_senal")
    hist, hist_prev = tec.get("macd_hist"), tec.get("macd_hist_prev")
    if not es_valido(macd) or not es_valido(senal):
        return None
    cruce_alcista = macd > senal
    mejora = es_valido(hist) and es_valido(hist_prev) and hist > hist_prev
    if cruce_alcista and mejora:
        return 90.0
    if cruce_alcista:
        return 70.0
    if mejora:
        return 55.0  # todavía bajista pero el histograma se estrecha
    return 20.0


def _puntuar_distancia_media(precio: float | None, media: float | None) -> float | None:
    """Mejor cuanto más cerca por encima de la media; penaliza la sobreextensión."""
    if not es_valido(precio) or not es_valido(media) or media <= 0:
        return None
    desviacion = (precio - media) / media
    if desviacion < -0.20:
        return 30.0
    if desviacion < -0.05:
        return 65.0
    if desviacion < 0.05:
        return 90.0
    if desviacion < 0.15:
        return 70.0
    if desviacion < 0.30:
        return 40.0
    return 15.0


def _puntuar_ath_atl(tec: dict) -> float | None:
    precio, ath, atl = tec.get("precio"), tec.get("ath"), tec.get("atl")
    if not all(es_valido(x) for x in (precio, ath, atl)) or ath <= atl:
        return None
    posicion = (precio - atl) / (ath - atl)  # 0 = mínimo histórico, 1 = máximo
    if posicion > 0.97:
        return 35.0   # en máximos: momentum sí, margen no
    if posicion > 0.85:
        return 55.0
    if posicion > 0.55:
        return 75.0
    if posicion > 0.25:
        return 85.0
    return 55.0       # muy cerca de mínimos suele implicar deterioro estructural


def _puntuar_earnings(fecha_proxima) -> float | None:
    """Entrar justo antes de resultados es asumir riesgo de evento."""
    dias = dias_hasta(fecha_proxima)
    if dias is None:
        return None
    if dias < 0:
        return None
    if dias <= 5:
        return 20.0
    if dias <= 12:
        return 50.0
    if dias <= 25:
        return 80.0
    return 90.0


def _puntuar_adx(tec: dict) -> float | None:
    """ADX CON contexto direccional (+DI / −DI).

    El ADX mide fuerza de tendencia, no dirección. La versión anterior lo
    escalaba como "cuanto más alto mejor", de modo que una tendencia bajista
    fuerte y persistente —exactamente el cuchillo cayendo que este bloque
    debería detectar— puntuaba igual de bien que una subida sólida.

    Ahora la fuerza AMPLIFICA el signo del sesgo direccional en vez de sumar
    por sí sola: se parte de una base neutra de 55 y la fuerza de la tendencia
    empuja hacia arriba si domina +DI y hacia abajo si domina −DI. El castigo
    máximo (−55) es mayor que el premio máximo (+45) a propósito: una
    tendencia bajista intacta es motivo suficiente para esperar, mientras que
    una alcista fuerte es buena señal pero también encarece la entrada.
    """
    adx, di_mas, di_menos = tec.get("adx"), tec.get("di_mas"), tec.get("di_menos")
    if not es_valido(adx):
        return None
    fuerza = escalar(adx, 12.0, 35.0)  # 0-100: cuánta tendencia hay
    if fuerza is None:
        return None
    if not es_valido(di_mas) or not es_valido(di_menos) or (float(di_mas) + float(di_menos)) <= 0:
        return 50.0  # hay ADX pero no dirección: no se premia ni se castiga
    sesgo = (float(di_mas) - float(di_menos)) / (float(di_mas) + float(di_menos))  # −1..+1
    factor = 0.45 if sesgo >= 0 else 0.55
    return max(0.0, min(100.0, 55.0 + sesgo * fuerza * factor))


def _puntuar_volumen_relativo(tec: dict) -> float | None:
    """Intensidad del volumen reciente CRUZADA con la dirección del precio.

    El volumen por sí solo no es bueno ni malo: lo que informa es qué está
    haciendo el precio mientras ese volumen aparece. Una caída con volumen muy
    por encima de lo normal es capitulación (vendedor forzado agotándose,
    buena señal para empezar a acumular); la misma expansión de volumen con el
    precio subiendo es persecución del movimiento, justo lo que un sistema de
    entrada por tramos quiere evitar. El volumen seco con el precio cayendo
    indica presión vendedora que se está apagando sola.

    Hasta ahora el volumen solo entraba en el timing de forma indirecta vía
    OBV, que mide acumulación/distribución a 20 sesiones y no distingue la
    intensidad del movimiento más reciente.
    """
    ratio = tec.get("volumen_relativo")
    variacion = tec.get("variacion_corta_pct")
    if not es_valido(ratio):
        return None
    if not es_valido(variacion):
        return 55.0  # hay volumen pero no dirección fiable: neutro
    cayendo = float(variacion) < -VOLUMEN_VARIACION_NEUTRA
    subiendo = float(variacion) > VOLUMEN_VARIACION_NEUTRA
    r = float(ratio)
    if r >= 1.5:      # expansión fuerte de volumen
        return 85.0 if cayendo else (35.0 if subiendo else 60.0)
    if r >= 1.15:     # volumen por encima de lo normal
        return 75.0 if cayendo else (45.0 if subiendo else 60.0)
    if r >= 0.80:     # volumen normal
        return 60.0 if cayendo else (50.0 if subiendo else 55.0)
    return 70.0 if cayendo else (40.0 if subiendo else 50.0)  # volumen seco


def _puntuar_fuerza_relativa(tec: dict) -> float | None:
    """Comportamiento del valor frente a su sector (o al mercado) a 3 meses.

    Sin esta capa, el bloque no puede distinguir una caída sistémica (cae todo
    el sector: el descuento es real y la empresa no tiene por qué estar rota)
    de una caída idiosincrática (el sector sube y el valor cae: el mercado
    está descontando algo específico de esta empresa).

    Tiene forma de joroba, coherente con el resto del bloque (RSI y ATH/ATL ya
    penalizan ambos extremos): el mejor punto es ir en línea o algo rezagado
    respecto al sector; quedarse MUY descolgado apunta a deterioro propio, y
    despuntar mucho por encima significa que la buena noticia ya está en el
    precio.

    Es la métrica más discutible del bloque —un sistema puramente de momentum
    la puntuaría al revés— y la primera candidata a recalibrar con datos
    reales.
    """
    diferencial = tec.get("fuerza_relativa_pct")
    if not es_valido(diferencial):
        return None
    d = float(diferencial)  # puntos porcentuales frente a la referencia
    if d < -25:
        return 35.0   # descolgado del sector: probable problema propio
    if d < -10:
        return 70.0   # rezagado, con margen de recuperación
    if d < 5:
        return 85.0   # en línea con su sector: el descuento no es idiosincrático
    if d < 20:
        return 60.0   # lidera, pero ya recogido en el precio
    return 40.0       # muy extendido frente a su sector


def _puntuar_confluencia_dca(precio: float | None, tec: dict) -> tuple[float | None, dict]:
    """Proximidad del precio actual a una zona de confluencia del motor DCA.

    Hasta ahora el Timing y el motor de soportes del Plan DCA eran dos
    sistemas independientes que no se hablaban: el timing miraba MM50 y MM200
    sueltas mientras el motor DCA ya calculaba zonas donde coinciden medias,
    Fibonacci, gaps, pivotes y mínimos. Este componente los conecta.

    Puntúa alto cuando el precio está PEGADO POR ENCIMA de una zona de peso
    alto (comprar aquí es comprar justo donde el motor DCA dice que hay suelo)
    y bajo cuando la zona fuerte más cercana queda lejos por debajo. Se
    combinan dos factores de forma multiplicativa: proximidad (medida en ATR,
    no en % fijo) y fuerza de la zona. Una zona muy fuerte a 4 ATR no sirve de
    nada hoy, y una zona pegada al precio pero de confluencia mínima tampoco
    es un argumento.

    Devuelve (puntuación, lectura de la mejor zona) para que la interfaz pueda
    mostrar a qué zona corresponde la nota.
    """
    if not es_valido(precio) or float(precio) <= 0:
        return None, {}
    zonas = plan_dca.zonas_confluencia_soporte(precio, tec)
    if not zonas:
        return None, {}   # sin zonas por debajo: se excluye, no se puntúa a cero

    atr = tec.get("atr")
    usar_atr = es_valido(atr) and float(atr) > 0
    mejor_senal, mejor_zona, mejor_distancia = -1.0, None, None

    for zona in zonas:
        distancia = (float(precio) - zona["precio"]) / float(precio)
        if distancia < 0:
            continue
        if usar_atr:
            d = (float(precio) - zona["precio"]) / float(atr)
            proximidad = escalar(d, CONFLUENCIA_ATR_LEJOS, CONFLUENCIA_ATR_CERCA)
        else:
            proximidad = escalar(distancia, CONFLUENCIA_PCT_LEJOS, CONFLUENCIA_PCT_CERCA)
        fuerza = min(1.0, zona["peso"] / DCA_CONFLUENCIA_FUERTE)
        senal = (proximidad or 0.0) / 100 * fuerza
        if senal > mejor_senal:
            mejor_senal, mejor_zona, mejor_distancia = senal, zona, distancia * 100

    if mejor_zona is None:
        return None, {}

    lectura = {
        "precio": mejor_zona["precio"],
        "distancia_pct": -abs(mejor_distancia) if es_valido(mejor_distancia) else None,
        "peso": mejor_zona["peso"],
        "motivos": mejor_zona["motivos"],
    }
    return 25.0 + 70.0 * max(0.0, mejor_senal), lectura


def _distancia_pct(precio, referencia) -> float | None:
    """Distancia del precio a una referencia, en % sobre esa referencia."""
    if not es_valido(precio) or not es_valido(referencia) or float(referencia) <= 0:
        return None
    return (float(precio) / float(referencia) - 1) * 100


def _posicion_rango(tec: dict) -> float | None:
    """Posición del precio dentro del rango histórico ATL-ATH, en % (0-100)."""
    precio, ath, atl = tec.get("precio"), tec.get("ath"), tec.get("atl")
    if not all(es_valido(x) for x in (precio, ath, atl)) or ath <= atl:
        return None
    return (float(precio) - float(atl)) / (float(ath) - float(atl)) * 100


def _lecturas(paquete: dict, tec: dict, precio, upside, peg, salud, fecha_earnings, zona) -> dict:
    """Valor real de cada métrica, para que la interfaz lo muestre junto a su
    puntuación sin recalcular nada por su cuenta."""
    macd, macd_senal = tec.get("macd"), tec.get("macd_senal")
    hist, hist_prev = tec.get("macd_hist"), tec.get("macd_hist_prev")
    obv_t = tec.get("obv_tendencia")
    return {
        "rsi": tec.get("rsi"),
        "macd": macd,
        "macd_senal": macd_senal,
        "macd_cruce_alcista": (
            macd > macd_senal if es_valido(macd) and es_valido(macd_senal) else None
        ),
        "macd_mejora": (
            hist > hist_prev if es_valido(hist) and es_valido(hist_prev) else None
        ),
        "upside_pct": upside,
        "peg": peg,
        "salud": salud,
        "distancia_mm50_pct": _distancia_pct(precio, tec.get("mm50")),
        "distancia_mm200_pct": _distancia_pct(precio, tec.get("mm200")),
        "variacion_1a_pct": tec.get("variacion_1a_pct"),
        "posicion_ath_atl": _posicion_rango(tec),
        "obv_tendencia_pct": float(obv_t) * 100 if es_valido(obv_t) else None,
        "adx": tec.get("adx"),
        "di_mas": tec.get("di_mas"),
        "di_menos": tec.get("di_menos"),
        "volumen_relativo": tec.get("volumen_relativo"),
        "variacion_corta_pct": tec.get("variacion_corta_pct"),
        "fuerza_relativa_pct": tec.get("fuerza_relativa_pct"),
        "referencia_simbolo": tec.get("referencia_simbolo"),
        "referencia_nombre": tec.get("referencia_nombre"),
        "zona_confluencia": zona,
        # Sin peso propio: pura lectura de contexto (ver
        # `indicadores.cruce_medias`), consumida solo por la fila
        # informativa del desglose de la UI, nunca por `ponderar()`.
        "cruce_medias": tec.get("cruce_medias") or {},
        "dias_earnings": dias_hasta(fecha_earnings),
    }


def calcular_timing(paquete: dict, tecnico: dict, valoracion: dict, calidad: dict) -> dict:
    """Cruza técnico, valoración, salud fundamental y zonas DCA en una nota 0-100."""
    if not tecnico.get("disponible"):
        return {
            "puntuacion": None,
            "senal": "Sin histórico suficiente",
            "color": "#94a3b8",
            "componentes": {},
            "lecturas": {},
            "excluidos": list(PESOS_TIMING.keys()),
            "nota_salud": None,
        }

    precio = tecnico.get("precio") or paquete.get("precio")
    upside = valoracion.get("upside_pct")
    salud = calidad.get("puntuacion")

    peg = primero_valido(
        paquete.get("info", {}).get("trailingPegRatio"), paquete.get("info", {}).get("pegRatio")
    )
    fecha_earnings = paquete.get("earnings", {}).get("proxima_fecha")
    punt_confluencia, zona_confluencia = _puntuar_confluencia_dca(precio, tecnico)

    componentes = {
        "rsi": _puntuar_rsi(tecnico.get("rsi")),
        "macd": _puntuar_macd(tecnico),
        # `margen_seguridad` se ha FUNDIDO aquí: era el mismo numerador
        # (valor objetivo − precio) con otro denominador, de modo que un valor
        # objetivo mal estimado entraba dos veces en la nota en vez de
        # diluirse entre métricas independientes.
        "upside": escalar(upside, -20.0, 40.0),
        "peg": escalar(peg, 3.0, 0.8) if es_valido(peg) and peg > 0 else None,
        "salud_fundamental": escalar(salud, 30.0, 85.0),
        "mm50": _puntuar_distancia_media(precio, tecnico.get("mm50")),
        "mm200": _puntuar_distancia_media(precio, tecnico.get("mm200")),
        # INVERTIDA respecto a la versión anterior (que premiaba la subida
        # de los últimos 12 meses como si fuera momentum). Con -45/+25 como
        # anclas de "malo"/"bueno", una subida del +25% puntuaba casi
        # el máximo (caso real: NBIX +12,8% -> 82,6/100) — justo lo
        # contrario de lo que persigue este bloque: encontrar el MEJOR
        # MOMENTO DE ENTRADA, no premiar que la acción ya haya subido y esté
        # más cara. El resto del bloque es coherentemente de reversión a la
        # media (RSI en zona 30-45, distancia a medias "justo por encima",
        # ATH/ATL en 25-55% del rango); esta métrica ahora sigue el mismo
        # criterio: a más caída en 12 meses, más puntos; a más subida, menos.
        "variacion_1a": escalar(tecnico.get("variacion_1a_pct"), 25.0, -45.0),
        "distancia_ath_atl": _puntuar_ath_atl(tecnico),
        "obv": escalar(tecnico.get("obv_tendencia"), -0.05, 0.05),
        "adx": _puntuar_adx(tecnico),
        "volumen_relativo": _puntuar_volumen_relativo(tecnico),
        "fuerza_relativa": _puntuar_fuerza_relativa(tecnico),
        "confluencia_dca": punt_confluencia,
        "proximidad_earnings": _puntuar_earnings(fecha_earnings),
    }

    lecturas = _lecturas(
        paquete, tecnico, precio, upside, peg, salud, fecha_earnings, zona_confluencia
    )

    resultado = ponderar(componentes, PESOS_TIMING)
    puntuacion = resultado["valor"]
    nota_salud = None

    # Puerta de calidad: sin salud fundamental >= 60 el timing no puede ser "entrada".
    if es_valido(puntuacion) and es_valido(salud) and salud < SALUD_MINIMA_TIMING:
        if puntuacion > TIMING_TOPE_SIN_SALUD:
            nota_salud = (
                f"Timing limitado a {TIMING_TOPE_SIN_SALUD}: la salud fundamental "
                f"({salud:.0f}) no alcanza el mínimo de {SALUD_MINIMA_TIMING}."
            )
            puntuacion = float(TIMING_TOPE_SIN_SALUD)
        else:
            nota_salud = f"Salud fundamental por debajo de {SALUD_MINIMA_TIMING}."

    senal, color = clasificar_senal(puntuacion)
    return {
        "puntuacion": round(puntuacion, 1) if es_valido(puntuacion) else None,
        "senal": senal,
        "color": color,
        "componentes": componentes,
        "lecturas": lecturas,
        "pesos_aplicados": resultado["usados"],
        "excluidos": resultado["excluidos"],
        "cobertura": resultado["cobertura"],
        "nota_salud": nota_salud,
    }


def clasificar_senal(puntuacion: float | None) -> tuple[str, str]:
    if not es_valido(puntuacion):
        return "Señal no calculable", "#94a3b8"
    for umbral, etiqueta, color in SENIALES_TIMING:
        if puntuacion >= umbral:
            return etiqueta, color
    return "NO ES MOMENTO", SENIALES_TIMING[-1][2]
