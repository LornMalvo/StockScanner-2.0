"""Bloque 6: plan DCA (3 entradas, 3 salidas, 1 stop) y veredicto final.

Motor de confluencia: se agrupan candidatos técnicos cercanos entre sí (medias
móviles, Fibonacci, gaps sin rellenar, soportes/resistencias históricos). Cuanta
más evidencia distinta apunte a una misma zona, mayor su puntuación.
"""

from __future__ import annotations

from config.settings import (
    DCA_PESOS_ENTRADA,
    DCA_PESOS_SALIDA,
    DCA_SEPARACION_MIN_ENTRADAS,
    DCA_STOP_ATR_MULT,
    DCA_STOP_MAX_CAIDA,
)
from utils.formato import es_valido


TOLERANCIA_CLUSTER = 0.025  # 2,5%: dos referencias más cercanas se funden en una


def _agrupar(candidatos: list[dict]) -> list[dict]:
    """Funde candidatos próximos en zonas de confluencia."""
    zonas: list[dict] = []
    for c in sorted(candidatos, key=lambda x: x["precio"]):
        if zonas and abs(c["precio"] - zonas[-1]["precio"]) / zonas[-1]["precio"] <= TOLERANCIA_CLUSTER:
            zona = zonas[-1]
            total = zona["peso"] + c["peso"]
            zona["precio"] = (zona["precio"] * zona["peso"] + c["precio"] * c["peso"]) / total
            zona["peso"] = total
            zona["motivos"].append(c["motivo"])
        else:
            zonas.append({"precio": c["precio"], "peso": c["peso"], "motivos": [c["motivo"]]})
    return zonas


def _candidatos_soporte(precio: float, tec: dict) -> list[dict]:
    c: list[dict] = []
    for clave, etiqueta, peso in (("mm50", "Media móvil 50", 2.0), ("mm200", "Media móvil 200", 2.5)):
        v = tec.get(clave)
        if es_valido(v) and v < precio:
            c.append({"precio": float(v), "peso": peso, "motivo": etiqueta})

    for nivel, valor in (tec.get("fibonacci") or {}).items():
        if es_valido(valor) and valor < precio:
            c.append({"precio": float(valor), "peso": 1.5, "motivo": f"Fibonacci {nivel}"})

    for gap in tec.get("gaps", []):
        if gap["tipo"] == "alcista" and gap["desde"] < precio:
            c.append({"precio": gap["desde"], "peso": 1.5, "motivo": "Gap alcista sin rellenar"})

    for soporte in (tec.get("pivotes") or {}).get("soportes", []):
        if soporte < precio * 0.99:
            c.append({"precio": float(soporte), "peso": 1.0, "motivo": "Soporte histórico"})

    if es_valido(tec.get("min_52s")) and tec["min_52s"] < precio:
        c.append({"precio": float(tec["min_52s"]), "peso": 1.5, "motivo": "Mínimo de 52 semanas"})
    return c


def _candidatos_resistencia(precio: float, tec: dict, fair_value: float | None) -> list[dict]:
    c: list[dict] = []
    for clave, etiqueta, peso in (("mm50", "Media móvil 50", 1.5), ("mm200", "Media móvil 200", 2.0)):
        v = tec.get(clave)
        if es_valido(v) and v > precio:
            c.append({"precio": float(v), "peso": peso, "motivo": f"Recuperación de {etiqueta}"})

    for resistencia in (tec.get("pivotes") or {}).get("resistencias", []):
        if resistencia > precio * 1.01:
            c.append({"precio": float(resistencia), "peso": 1.2, "motivo": "Resistencia histórica"})

    for clave, etiqueta, peso in (
        ("max_52s", "Máximo de 52 semanas", 2.0),
        ("ath", "Máximo histórico", 2.2),
    ):
        v = tec.get(clave)
        if es_valido(v) and v > precio:
            c.append({"precio": float(v), "peso": peso, "motivo": etiqueta})

    for gap in tec.get("gaps", []):
        if gap["tipo"] == "bajista" and gap["hasta"] > precio:
            c.append({"precio": gap["hasta"], "peso": 1.3, "motivo": "Gap bajista sin rellenar"})

    # El valor objetivo apoya, pero no limita: peso moderado.
    if es_valido(fair_value) and fair_value > precio:
        c.append({"precio": float(fair_value), "peso": 1.8, "motivo": "Valor objetivo justo"})
    return c


def _separar(zonas: list[dict], precio_ref: float, n: int, separacion: float, ascendente: bool) -> list[dict]:
    """Selecciona n zonas respetando la separación mínima entre ellas."""
    ordenadas = sorted(zonas, key=lambda z: z["precio"], reverse=not ascendente)
    elegidas: list[dict] = []
    ultimo = precio_ref
    for zona in ordenadas:
        if len(elegidas) >= n:
            break
        distancia = abs(zona["precio"] - ultimo) / ultimo if ultimo else 0
        if distancia >= separacion:
            elegidas.append(zona)
            ultimo = zona["precio"]
    return elegidas


def construir_plan(paquete: dict, tecnico: dict, valoracion: dict) -> dict:
    """Genera 3 niveles de entrada, 3 de salida y 1 stop loss."""
    precio = tecnico.get("precio") or paquete.get("precio")
    if not es_valido(precio) or not tecnico.get("disponible"):
        return {"disponible": False, "motivo": "Sin precio o histórico suficiente"}

    fair_value = valoracion.get("fair_value")

    # ------------------------------------------------------------ entradas --
    zonas_entrada = _agrupar(_candidatos_soporte(precio, tecnico))
    entradas = _separar(zonas_entrada, precio, 3, DCA_SEPARACION_MIN_ENTRADAS, ascendente=False)

    # Si la confluencia no da los 3 niveles, se completan por escalones fijos.
    referencia = entradas[-1]["precio"] if entradas else precio
    while len(entradas) < 3:
        siguiente = referencia * (1 - DCA_SEPARACION_MIN_ENTRADAS * 1.2)
        entradas.append(
            {"precio": siguiente, "peso": 0.5, "motivos": ["Escalón técnico (sin confluencia)"]}
        )
        referencia = siguiente

    niveles_entrada = [
        {
            "nivel": i + 1,
            "precio": z["precio"],
            "distancia_pct": (z["precio"] / precio - 1) * 100,
            "peso_capital": DCA_PESOS_ENTRADA[i],
            "confluencia": z["peso"],
            "motivos": z["motivos"],
        }
        for i, z in enumerate(entradas[:3])
    ]

    # -------------------------------------------------------------- salidas --
    zonas_salida = _agrupar(_candidatos_resistencia(precio, tecnico, fair_value))
    salidas = _separar(zonas_salida, precio, 3, 0.06, ascendente=True)
    referencia = salidas[-1]["precio"] if salidas else precio
    while len(salidas) < 3:
        siguiente = referencia * 1.12
        salidas.append(
            {"precio": siguiente, "peso": 0.5, "motivos": ["Extensión técnica (sin confluencia)"]}
        )
        referencia = siguiente

    niveles_salida = [
        {
            "nivel": i + 1,
            "precio": z["precio"],
            "distancia_pct": (z["precio"] / precio - 1) * 100,
            "peso_posicion": DCA_PESOS_SALIDA[i],
            "confluencia": z["peso"],
            "motivos": z["motivos"],
        }
        for i, z in enumerate(salidas[:3])
    ]

    # ------------------------------------------------------------ stop loss --
    entrada_baja = niveles_entrada[-1]["precio"]
    atr = tecnico.get("atr")
    stop_atr = entrada_baja - DCA_STOP_ATR_MULT * atr if es_valido(atr) else None
    stop_estructural = min(
        [s for s in (tecnico.get("min_52s"),) if es_valido(s) and s < entrada_baja],
        default=None,
    )
    candidatos_stop = [s for s in (stop_atr, stop_estructural) if es_valido(s)]
    stop = min(candidatos_stop) if candidatos_stop else entrada_baja * 0.85
    stop = max(stop, niveles_entrada[0]["precio"] * (1 - DCA_STOP_MAX_CAIDA))

    precio_medio = sum(n["precio"] * n["peso_capital"] for n in niveles_entrada)
    objetivo_medio = sum(n["precio"] * n["peso_posicion"] for n in niveles_salida)
    riesgo = precio_medio - stop
    recompensa = objetivo_medio - precio_medio

    return {
        "disponible": True,
        "precio_referencia": precio,
        "entradas": niveles_entrada,
        "salidas": niveles_salida,
        "stop_loss": {
            "precio": stop,
            "distancia_pct": (stop / precio - 1) * 100,
            "base": "ATR(14) x 2,5 sobre la última entrada" if es_valido(stop_atr) else "Estructural",
        },
        "precio_medio_estimado": precio_medio,
        "objetivo_medio_estimado": objetivo_medio,
        "ratio_riesgo_recompensa": recompensa / riesgo if riesgo > 0 else None,
        "ejecutable": precio <= niveles_entrada[0]["precio"],
    }


def veredicto_final(calidad: dict, valoracion: dict, timing: dict, plan: dict) -> dict:
    """Etiqueta escueta que combina calidad, precio y timing."""
    salud = calidad.get("puntuacion")
    upside = valoracion.get("upside_pct")
    punt_timing = timing.get("puntuacion")

    if not any(es_valido(x) for x in (salud, upside, punt_timing)):
        return {
            "etiqueta": "SIN DATOS SUFICIENTES",
            "color": "#94a3b8",
            "motivos": ["No hay métricas suficientes para emitir un veredicto"],
        }

    motivos: list[str] = []
    if es_valido(salud):
        motivos.append(f"Calidad {salud:.0f}/100")
    if es_valido(upside):
        motivos.append(f"Upside {upside:+.1f} %")
    if es_valido(punt_timing):
        motivos.append(f"Timing {punt_timing:.0f}/100")
    if plan.get("disponible"):
        motivos.append("Precio en nivel 1" if plan.get("ejecutable") else "Aún sobre el nivel 1")

    buena_calidad = es_valido(salud) and salud >= 60
    calidad_alta = es_valido(salud) and salud >= 75
    infravalorada = es_valido(upside) and upside >= 12
    precio_razonable = es_valido(upside) and upside >= 3
    timing_bueno = es_valido(punt_timing) and punt_timing >= 60
    timing_ideal = es_valido(punt_timing) and punt_timing >= 80

    if calidad_alta and infravalorada and timing_ideal:
        return {"etiqueta": "COMPRA YA", "color": "#065f46", "motivos": motivos}
    if buena_calidad and infravalorada and timing_bueno:
        return {"etiqueta": "COMPRA POSIBLE", "color": "#10b981", "motivos": motivos}
    if buena_calidad and precio_razonable:
        return {"etiqueta": "ACUMULAR POR TRAMOS", "color": "#25a18e", "motivos": motivos}
    if buena_calidad and not precio_razonable:
        return {"etiqueta": "BUENA EMPRESA, MAL PRECIO", "color": "#ffcb77", "motivos": motivos}
    if es_valido(salud) and salud < 45:
        return {"etiqueta": "EVITAR POR AHORA", "color": "#dc2626", "motivos": motivos}
    return {"etiqueta": "PRECAUCIÓN", "color": "#f97316", "motivos": motivos}
