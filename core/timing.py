"""Bloque 5: calidad del momento de entrada (0-100) y señal resultante.

Cada componente puntúa de 0 a 100 y se pondera según `PESOS_TIMING`. Los
componentes sin dato se excluyen y su peso se reparte entre los demás.
"""

from __future__ import annotations

from config.settings import (
    PESOS_TIMING,
    SALUD_MINIMA_TIMING,
    SENIALES_TIMING,
    TIMING_TOPE_SIN_SALUD,
)
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


def calcular_timing(paquete: dict, tecnico: dict, valoracion: dict, calidad: dict) -> dict:
    """Cruza técnico, valoración y salud fundamental en una nota 0-100."""
    if not tecnico.get("disponible"):
        return {
            "puntuacion": None,
            "senal": "Sin histórico suficiente",
            "color": "#94a3b8",
            "componentes": {},
            "excluidos": list(PESOS_TIMING.keys()),
            "nota_salud": None,
        }

    precio = tecnico.get("precio") or paquete.get("precio")
    fair_value = valoracion.get("fair_value")
    upside = valoracion.get("upside_pct")
    salud = calidad.get("puntuacion")

    margen_seguridad = (
        (fair_value - precio) / fair_value * 100
        if es_valido(fair_value) and es_valido(precio) and fair_value > 0
        else None
    )
    peg = primero_valido(
        paquete.get("info", {}).get("trailingPegRatio"), paquete.get("info", {}).get("pegRatio")
    )

    componentes = {
        "rsi": _puntuar_rsi(tecnico.get("rsi")),
        "macd": _puntuar_macd(tecnico),
        "margen_seguridad": escalar(margen_seguridad, -20.0, 35.0),
        "upside": escalar(upside, -20.0, 40.0),
        "peg": escalar(peg, 3.0, 0.8) if es_valido(peg) and peg > 0 else None,
        "salud_fundamental": escalar(salud, 30.0, 85.0),
        "mm50": _puntuar_distancia_media(precio, tecnico.get("mm50")),
        "mm200": _puntuar_distancia_media(precio, tecnico.get("mm200")),
        "variacion_1a": escalar(tecnico.get("variacion_1a_pct"), -45.0, 25.0),
        "distancia_ath_atl": _puntuar_ath_atl(tecnico),
        "obv": escalar(tecnico.get("obv_tendencia"), -0.05, 0.05),
        "adx": escalar(tecnico.get("adx"), 12.0, 30.0),
        "proximidad_earnings": _puntuar_earnings(paquete.get("earnings", {}).get("proxima_fecha")),
    }

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
        "pesos_aplicados": resultado["usados"],
        "excluidos": resultado["excluidos"],
        "cobertura": resultado["cobertura"],
        "margen_seguridad_pct": margen_seguridad,
        "nota_salud": nota_salud,
    }


def clasificar_senal(puntuacion: float | None) -> tuple[str, str]:
    if not es_valido(puntuacion):
        return "Señal no calculable", "#94a3b8"
    for umbral, etiqueta, color in SENIALES_TIMING:
        if puntuacion >= umbral:
            return etiqueta, color
    return "NO ES MOMENTO", SENIALES_TIMING[-1][2]
