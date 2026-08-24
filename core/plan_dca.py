"""Bloque 6: plan DCA (3 entradas, 3 salidas, 1 stop) y veredicto final.

MOTOR DE CONFLUENCIA (rediseñado). El planteamiento anterior era: reunir
candidatos técnicos, fundir los que estuvieran a menos de un 2,5% entre sí, y
recorrer las zonas resultantes POR ORDEN DE PRECIO quedándose con las que
respetaran una separación fija del 10%. Ese diseño tenía tres defectos
estructurales, todos confirmados con simulación sobre casos reales:

1. La tolerancia de fusión fija (2,5%) no se adapta a la volatilidad: en una
   acción tranquila dejaba sin fundir niveles prácticamente idénticos, y en una
   volátil fundía niveles que en realidad estaban lejos. Dos referencias
   separadas un 2,73% quedaban como zonas independientes por 0,23 puntos.
2. La selección recorría las zonas por precio, así que el peso de confluencia
   decidía CÓMO se formaban las zonas pero nunca CUÁL sobrevivía: la zona más
   fuerte de toda la tabla podía quedar fuera del plan simplemente por no
   tocarle turno en el recorrido.
3. La separación mínima fija (10% entradas / 6% salidas) descartaba zonas
   fuertes por márgenes de décimas (9,87% frente a 10%).

El motor actual sustituye los tres umbrales fijos por magnitudes adaptativas:
agrupación por densidad gaussiana con anchura proporcional al ATR, selección
ordenada POR PESO con separación en múltiplos de ATR, y una regla de excepción
acotada para las zonas fuertes que fallan la separación por poco margen.

Fuentes de candidatos: medias móviles, Fibonacci, gaps sin rellenar (anclados
por su rango completo, no por un punto), pivotes diarios con recuento de toques
y decadencia por antigüedad, pivotes SEMANALES, Volume Profile (POC y Value
Area), líneas de tendencia diagonales proyectadas a hoy y niveles psicológicos
redondos. Todas se calculan en `core/indicadores.py` y llegan aquí dentro del
diccionario técnico.
"""

from __future__ import annotations

import math

import numpy as np

from config.settings import (
    CONFIANZA_VOLATILIDAD_MAX,
    CONFIANZA_VOLATILIDAD_MIN,
    CONFLUENCIA_PESO_MIN_ZONA,
    CONFLUENCIA_REJILLA,
    CONFLUENCIA_SIGMA_ATR,
    CONFLUENCIA_SIGMA_MAX_PCT,
    CONFLUENCIA_SIGMA_MIN_PCT,
    CONFLUENCIA_SIGMA_PCT,
    DCA_EXCEPCION_COBERTURA_MIN,
    DCA_EXCEPCION_DISTANCIA_MIN,
    DCA_EXCEPCION_RATIO_PESO,
    DCA_DISTANCIA_MAX_ATR,
    DCA_DISTANCIA_MAX_ENTRADAS,
    DCA_DISTANCIA_MAX_SALIDAS,
    DCA_DISTANCIA_MIN_ENTRADAS,
    DCA_DISTANCIA_MIN_SALIDAS,
    DCA_PESOS_ENTRADA,
    DCA_PESOS_SALIDA,
    DCA_SEPARACION_ATR_ENTRADAS,
    DCA_SEPARACION_ATR_SALIDAS,
    DCA_SEPARACION_MAX_ABS,
    DCA_SEPARACION_MIN_ABS,
    DCA_SEPARACION_MIN_ENTRADAS,
    DCA_STOP_ATR_MULT,
    DCA_STOP_MARGEN_MIN,
    DCA_STOP_MAX_CAIDA,
    DIAGONAL_PESO,
    NIVEL_REDONDO_PESO,
    PIVOTE_DECADENCIA_ANOS,
    PIVOTE_DECADENCIA_MIN,
    PIVOTE_PESO_SEMANAL,
    PIVOTE_TOQUES_MULT,
    VP_PESO_POC,
    VP_PESO_VALUE_AREA,
)
from utils.formato import es_valido


# =========================================================== utilidades =======
def _num(valor) -> float | None:
    """Float utilizable o None. Evita repetir `es_valido` + `float` por todas partes."""
    return float(valor) if es_valido(valor) else None


def _sigma_base(precio: float, atr: float | None) -> float:
    """Anchura de la campana de influencia de un candidato.

    Proporcional al ATR: una acción volátil "contagia" confluencia a un rango
    de precio más ancho, una tranquila a uno más estrecho. Es lo que sustituye
    a la antigua tolerancia fija del 2,5%.
    """
    if atr and atr > 0:
        s = atr * CONFLUENCIA_SIGMA_ATR
        # Acotada por arriba y por abajo: con un ATR muy alto las campanas
        # fundirían la tabla entera en dos o tres zonas gigantes, y con un ATR
        # degenerado no fundirían nada.
        return min(max(s, precio * CONFLUENCIA_SIGMA_MIN_PCT), precio * CONFLUENCIA_SIGMA_MAX_PCT)
    return precio * CONFLUENCIA_SIGMA_PCT


def _rango_maximo(precio: float, atr: float | None, techo: float, suelo: float) -> float:
    """Hasta dónde mira el motor. Ver DCA_DISTANCIA_* en settings."""
    if atr and atr > 0 and precio > 0:
        bruto = DCA_DISTANCIA_MAX_ATR * atr / precio
    else:
        bruto = techo
    return min(max(bruto, suelo), techo)


def _en_rango(
    candidatos: list[dict], precio: float, atr: float | None, techo: float, suelo: float
) -> list[dict]:
    """Descarta candidatos fuera del rango de trabajo, ANTES de agrupar.

    Se filtra antes y no después a propósito: si se filtrara al final, un
    candidato lejanísimo seguiría aportando su peso a la zona vecina y la
    inflaría sin representar evidencia utilizable.
    """
    limite = _rango_maximo(precio, atr, techo, suelo)
    return [
        c for c in candidatos
        if es_valido(c.get("precio")) and abs(c["precio"] - precio) / precio <= limite
    ]


def _factor_confianza(tec: dict) -> float:
    """Modulador global del peso de la tabla según el régimen de volatilidad.

    Con el ATR relativo en máximos de dos años el mercado está nervioso y TODOS
    los niveles son menos fiables; con el ATR en mínimos, se respetan mejor. No
    cambia qué zonas se eligen (afecta por igual a todas), pero sí la confianza
    que el resto del sistema deposita en ellas: `core/timing.py` compara el peso
    contra `DCA_CONFLUENCIA_FUERTE`, así que un régimen de alta volatilidad se
    traduce automáticamente en menos puntuación de timing.
    """
    pct = _num(tec.get("atr_percentil"))
    if pct is None:
        return 1.0  # sin dato no se modula nada: nunca se inventa un 1,0 castigado
    pct = min(100.0, max(0.0, pct))
    return CONFIANZA_VOLATILIDAD_MAX + (
        CONFIANZA_VOLATILIDAD_MIN - CONFIANZA_VOLATILIDAD_MAX
    ) * (pct / 100.0)


def _separacion_minima(precio: float, atr: float | None, multiplo: float) -> float:
    """Separación mínima entre niveles, en múltiplos de ATR y no en % fijo.

    Con ATR grande se exige más separación real —un movimiento del 5% en un día
    no significa nada en un valor así—, y con ATR pequeño se permiten niveles
    más próximos sin que el plan pierda sentido. Acotada entre un suelo y un
    techo para que un ATR extremo no genere planes degenerados.
    """
    if atr and atr > 0 and precio > 0:
        bruta = multiplo * atr / precio
    else:
        bruta = DCA_SEPARACION_MIN_ENTRADAS
    return min(max(bruta, DCA_SEPARACION_MIN_ABS), DCA_SEPARACION_MAX_ABS)


# ======================================================= agrupación ==========
def _agrupar(candidatos: list[dict], precio: float, atr: float | None,
             confianza: float = 1.0) -> list[dict]:
    """Funde candidatos en zonas de confluencia por DENSIDAD, sin umbral binario.

    Cada candidato es una campana gaussiana de altura igual a su peso y anchura
    proporcional al ATR (o mayor, si el propio candidato representa un rango —un
    gap o la Value Area traen su propio `sigma`—). Se suman todas las campanas a
    lo largo de una rejilla de precios y las zonas de confluencia son los
    MÁXIMOS LOCALES de la curva resultante.

    Esto elimina de raíz el problema del corte binario: dos candidatos cercanos
    en términos de ATR generan un único pico aunque su distancia en porcentaje
    supere cualquier umbral, y dos candidatos lejanos en ATR no se funden aunque
    en porcentaje parezcan próximos.

    El precio de cada zona es la media ponderada de sus candidatos (no la
    posición del pico) y su peso, la suma de los pesos: así la masa total se
    conserva exactamente igual que en la fusión secuencial anterior.
    """
    validos = [c for c in candidatos if es_valido(c.get("precio")) and c["precio"] > 0]
    if not validos:
        return []

    sigma_def = _sigma_base(precio, atr)
    for c in validos:
        c["sigma"] = max(float(c.get("sigma") or 0.0), sigma_def)

    minimo = min(c["precio"] - 3 * c["sigma"] for c in validos)
    maximo = max(c["precio"] + 3 * c["sigma"] for c in validos)
    minimo = max(minimo, 1e-9)
    if maximo <= minimo:
        return []

    rejilla = np.linspace(minimo, maximo, CONFLUENCIA_REJILLA)
    densidad = np.zeros_like(rejilla)
    for c in validos:
        densidad += c["peso"] * np.exp(-0.5 * ((rejilla - c["precio"]) / c["sigma"]) ** 2)

    # Máximos locales de la curva de densidad (con los extremos incluidos).
    picos: list[float] = []
    for i in range(len(rejilla)):
        izq = densidad[i - 1] if i > 0 else -np.inf
        der = densidad[i + 1] if i < len(rejilla) - 1 else -np.inf
        if densidad[i] >= izq and densidad[i] > der:
            picos.append(float(rejilla[i]))
    if not picos:
        picos = [float(rejilla[int(np.argmax(densidad))])]

    # Cada candidato se asigna al pico más cercano; la zona es el resumen
    # ponderado de los candidatos que le tocaron.
    cubos: dict[int, list[dict]] = {}
    picos_arr = np.array(picos)
    for c in validos:
        idx = int(np.argmin(np.abs(picos_arr - c["precio"])))
        cubos.setdefault(idx, []).append(c)

    zonas: list[dict] = []
    for idx, grupo in cubos.items():
        peso = sum(c["peso"] for c in grupo)
        if peso < CONFLUENCIA_PESO_MIN_ZONA:
            continue
        zonas.append(
            {
                "precio": sum(c["precio"] * c["peso"] for c in grupo) / peso,
                "peso": peso * confianza,
                "peso_bruto": peso,
                "motivos": [c["motivo"] for c in grupo],
                # Desglose candidato a candidato. No lo consume la app: existe
                # para poder AUDITAR el motor contra una fuente externa y ver
                # exactamente de dónde sale cada zona y con qué precio entró
                # cada evidencia antes de fundirse.
                "detalle": [
                    {"motivo": c["motivo"], "precio": c["precio"], "peso": c["peso"]}
                    for c in sorted(grupo, key=lambda x: -x["peso"])
                ],
            }
        )
    return sorted(zonas, key=lambda z: z["precio"])


# ======================================================== candidatos =========
def _peso_pivote(base: float, detalle: dict) -> float:
    """Ajusta el peso de un pivote por nº de toques y por antigüedad.

    Toques: multiplicador NO lineal (logarítmico). Un nivel respetado tres veces
    es claramente más fiable que uno tocado una vez, pero seis toques no valen
    seis veces —a partir de cierto punto es el mismo nivel, no más evidencia—.

    Antigüedad: un mínimo de hace cuatro años pesa menos que uno de hace tres
    meses, pero no se anula (la memoria del mercado es larga): el descuento tiene
    suelo en `PIVOTE_DECADENCIA_MIN`.
    """
    toques = max(1, int(detalle.get("toques") or 1))
    peso = base * (1 + PIVOTE_TOQUES_MULT * math.log(toques))
    anos = detalle.get("antiguedad_anos")
    if es_valido(anos) and PIVOTE_DECADENCIA_ANOS > 0:
        factor = 1 - (1 - PIVOTE_DECADENCIA_MIN) * min(1.0, float(anos) / PIVOTE_DECADENCIA_ANOS)
        peso *= factor
    return peso


def _candidatos_pivotes(tec: dict, precio: float, lado: str) -> list[dict]:
    """Pivotes diarios y semanales del lado pedido ('soportes' o 'resistencias')."""
    c: list[dict] = []
    filtro = (lambda v: v < precio * 0.99) if lado == "soportes" else (lambda v: v > precio * 1.01)
    etiqueta = "Soporte histórico" if lado == "soportes" else "Resistencia histórica"
    base = 1.0 if lado == "soportes" else 1.2

    detalle = (tec.get("pivotes") or {}).get(f"detalle_{lado}") or []
    if detalle:
        for d in detalle:
            v = _num(d.get("precio"))
            if v is not None and filtro(v):
                c.append({"precio": v, "peso": _peso_pivote(base, d), "motivo": etiqueta})
    else:  # respaldo si el histórico no trae detalle (formato antiguo)
        for v in (tec.get("pivotes") or {}).get(lado, []):
            v = _num(v)
            if v is not None and filtro(v):
                c.append({"precio": v, "peso": base, "motivo": etiqueta})

    # Multi-temporalidad: el mismo pivote en velas semanales pesa bastante más.
    etiqueta_sem = "Soporte semanal" if lado == "soportes" else "Resistencia semanal"
    for d in (tec.get("pivotes_semanales") or {}).get(f"detalle_{lado}") or []:
        v = _num(d.get("precio"))
        if v is not None and filtro(v):
            c.append(
                {"precio": v, "peso": _peso_pivote(PIVOTE_PESO_SEMANAL, d), "motivo": etiqueta_sem}
            )
    return c


def _candidatos_volumen(tec: dict, precio: float, arriba: bool) -> list[dict]:
    """Volume Profile: POC y bordes de la Value Area.

    Es la única fuente que no mide por dónde PASÓ el precio sino dónde se
    NEGOCIÓ de verdad, y por eso entra con el peso más alto de toda la tabla.
    Los bordes de la Value Area se emiten con `sigma` ancho porque representan
    una zona, no un precio exacto.
    """
    vp = tec.get("volume_profile") or {}
    if not vp:
        return []
    ancho = _num(vp.get("ancho_banda")) or 0.0
    c: list[dict] = []

    poc = _num(vp.get("poc"))
    if poc is not None and ((poc > precio) if arriba else (poc < precio)):
        c.append(
            {
                "precio": poc,
                "peso": VP_PESO_POC,
                "motivo": "Zona de máximo volumen (POC)",
                "sigma": ancho * 1.5,
            }
        )

    borde = _num(vp.get("vah")) if arriba else _num(vp.get("val"))
    if borde is not None and ((borde > precio) if arriba else (borde < precio)):
        c.append(
            {
                "precio": borde,
                "peso": VP_PESO_VALUE_AREA,
                "motivo": "Borde de área de valor" + (" (VAH)" if arriba else " (VAL)"),
                "sigma": ancho * 2.0,
            }
        )
    return c


def _candidatos_diagonales(tec: dict, precio: float, arriba: bool) -> list[dict]:
    """Directrices de canal proyectadas a hoy, ya convertidas a un precio."""
    tipo = "resistencia" if arriba else "soporte"
    c: list[dict] = []
    for d in tec.get("diagonales") or []:
        if d.get("tipo") != tipo:
            continue
        v = _num(d.get("precio"))
        if v is None or ((v <= precio) if arriba else (v >= precio)):
            continue
        pendiente = d.get("pendiente_pct") or 0
        sentido = "alcista" if pendiente > 0 else "bajista"
        c.append(
            {
                "precio": v,
                "peso": DIAGONAL_PESO * (1 + PIVOTE_TOQUES_MULT * math.log(max(1, d.get("toques", 1)))),
                "motivo": f"Directriz {sentido} ({d.get('toques', 0)} toques)",
            }
        )
    return c


def _candidatos_redondos(tec: dict, precio: float, arriba: bool) -> list[dict]:
    """Números psicológicos: peso bajo, sirven de desempate, no de argumento."""
    return [
        {"precio": v, "peso": NIVEL_REDONDO_PESO, "motivo": "Nivel psicológico redondo"}
        for v in (tec.get("niveles_redondos") or [])
        if es_valido(v) and ((v > precio) if arriba else (v < precio))
    ]


def _candidatos_soporte(precio: float, tec: dict) -> list[dict]:
    c: list[dict] = []
    for clave, etiqueta, peso in (("mm50", "Media móvil 50", 2.0), ("mm200", "Media móvil 200", 2.5)):
        v = _num(tec.get(clave))
        if v is not None and v < precio:
            c.append({"precio": v, "peso": peso, "motivo": etiqueta})

    for nivel, valor in (tec.get("fibonacci") or {}).items():
        v = _num(valor)
        if v is not None and v < precio:
            c.append({"precio": v, "peso": 1.5, "motivo": f"Fibonacci {nivel}"})

    # Los gaps se anclan por su RANGO COMPLETO, no por un extremo: dos gaps que
    # se solapan en la realidad se anclaban en puntos distintos y se contaban
    # como candidatos independientes, perdiendo una confluencia genuina. El gap
    # entra ahora en su punto medio con `sigma` igual a su semiamplitud, así que
    # la fusión por densidad detecta el solape sin necesidad de umbral alguno.
    for gap in tec.get("gaps", []):
        desde, hasta = _num(gap.get("desde")), _num(gap.get("hasta"))
        if gap.get("tipo") == "alcista" and desde is not None and hasta is not None and desde < precio:
            c.append(
                {
                    "precio": (desde + hasta) / 2,
                    "peso": 1.5,
                    "motivo": "Gap alcista sin rellenar",
                    "sigma": abs(hasta - desde) / 2,
                }
            )

    c += _candidatos_pivotes(tec, precio, "soportes")
    c += _candidatos_volumen(tec, precio, arriba=False)
    c += _candidatos_diagonales(tec, precio, arriba=False)
    c += _candidatos_redondos(tec, precio, arriba=False)

    v = _num(tec.get("min_52s"))
    if v is not None and v < precio:
        c.append({"precio": v, "peso": 1.5, "motivo": "Mínimo de 52 semanas"})
    return c


def _candidatos_resistencia(precio: float, tec: dict, fair_value: float | None) -> list[dict]:
    c: list[dict] = []
    for clave, etiqueta, peso in (("mm50", "Media móvil 50", 1.5), ("mm200", "Media móvil 200", 2.0)):
        v = _num(tec.get(clave))
        if v is not None and v > precio:
            c.append({"precio": v, "peso": peso, "motivo": f"Recuperación de {etiqueta}"})

    c += _candidatos_pivotes(tec, precio, "resistencias")

    for clave, etiqueta, peso in (
        ("max_52s", "Máximo de 52 semanas", 2.0),
        ("ath", "Máximo histórico", 2.2),
    ):
        v = _num(tec.get(clave))
        if v is not None and v > precio:
            c.append({"precio": v, "peso": peso, "motivo": etiqueta})

    for gap in tec.get("gaps", []):
        desde, hasta = _num(gap.get("desde")), _num(gap.get("hasta"))
        if gap.get("tipo") == "bajista" and desde is not None and hasta is not None and hasta > precio:
            c.append(
                {
                    "precio": (desde + hasta) / 2,
                    "peso": 1.3,
                    "motivo": "Gap bajista sin rellenar",
                    "sigma": abs(hasta - desde) / 2,
                }
            )

    c += _candidatos_volumen(tec, precio, arriba=True)
    c += _candidatos_diagonales(tec, precio, arriba=True)
    c += _candidatos_redondos(tec, precio, arriba=True)

    # El valor objetivo apoya, pero no limita: peso moderado.
    v = _num(fair_value)
    if v is not None and v > precio:
        c.append({"precio": v, "peso": 1.8, "motivo": "Valor objetivo justo"})
    return c


# ==================================================== API pública ============
def zonas_confluencia_soporte(precio: float, tecnico: dict) -> list[dict]:
    """Zonas de soporte agrupadas por confluencia, de la más alta a la más baja.

    PUNTO DE ENTRADA ÚNICO al motor de confluencia para cualquier otro módulo
    (hoy lo consume `core/timing.py` para puntuar la proximidad del precio a
    una zona fuerte). Deliberadamente devuelve las zonas EN BRUTO, antes de
    `_seleccionar()`: la selección de los 3 niveles del plan aplica filtros de
    separación mínima que descartan zonas perfectamente válidas para el
    timing —una zona a un 3% del precio no sirve como "entrada 2" pero es
    justo lo que el timing quiere detectar—.

    El rediseño del motor (densidad gaussiana, ATR adaptativo, orden por peso,
    Volume Profile, multi-temporalidad, diagonales) se ha hecho dentro de
    `_agrupar()` y `_candidatos_soporte()`, de modo que `core/timing.py` hereda
    todos los cambios sin que haya habido que tocar una sola línea suya. Si en
    el futuro se introduce una función de agrupación distinta, hay que redirigir
    ESTA función a la nueva, y solo esta.
    """
    if not es_valido(precio) or precio <= 0:
        return []
    precio = float(precio)
    return sorted(
        _agrupar(
            _en_rango(
                _candidatos_soporte(precio, tecnico),
                precio,
                _num(tecnico.get("atr")),
                DCA_DISTANCIA_MAX_ENTRADAS,
                DCA_DISTANCIA_MIN_ENTRADAS,
            ),
            precio,
            _num(tecnico.get("atr")),
            _factor_confianza(tecnico),
        ),
        key=lambda z: z["precio"],
        reverse=True,
    )


# ====================================================== selección ============
def _cumple_separacion(
    zona: dict, referencias: list[dict], separacion: float
) -> tuple[bool, str | None]:
    """¿Puede esta zona convivir con las ya elegidas (y con el precio actual)?

    La separación se comprueba contra todas las referencias, incluido el precio
    de mercado, que entra como ZONA VIRTUAL DE PESO 0: así una confluencia
    fuerte muy cercana al precio puede colarse como Entrada 1 sin tener que
    superar en peso a nada (0 x 1,4 = 0), pero sigue sujeta al suelo absoluto
    de distancia.

    Cuando una referencia falla, se aplica la REGLA DE EXCEPCIÓN, que exige las
    dos condiciones a la vez (nunca una sola):
      · el peso de la zona supera al de la referencia en >= RATIO_PESO, y
      · la distancia ya cubre >= COBERTURA_MIN de la separación exigida.
    Sin la segunda condición, una zona de peso enorme pegada al precio se
    colocaría como Entrada 1 casi a precio de mercado y el plan dejaría de
    escalonar nada.
    """
    excepciones: list[str] = []
    for ref in referencias:
        if ref["precio"] <= 0:
            continue
        distancia = abs(zona["precio"] - ref["precio"]) / ref["precio"]
        if distancia >= separacion:
            continue
        cobertura = distancia / separacion if separacion > 0 else 0.0
        peso_ok = zona["peso"] >= ref["peso"] * DCA_EXCEPCION_RATIO_PESO
        if cobertura >= DCA_EXCEPCION_COBERTURA_MIN and peso_ok:
            excepciones.append(
                f"separación {distancia * 100:.1f}% sobre {separacion * 100:.1f}% exigido"
            )
            continue
        return False, None
    return True, (excepciones[0] if excepciones else None)


def _seleccionar(
    zonas: list[dict], precio_ref: float, n: int, separacion: float, ascendente: bool
) -> list[dict]:
    """Elige n zonas ORDENANDO POR PESO, no por precio.

    Este es el cambio de criterio de fondo. Antes el recorrido iba por precio y
    el peso solo intervenía al formar las zonas, de modo que la zona más fiable
    de la tabla podía quedar fuera del plan por no tocarle turno. Ahora la zona
    de mayor peso se acepta siempre primero y actúa de ancla, y cada siguiente
    candidata se admite si respeta la separación adaptativa frente a las ya
    elegidas y frente al precio actual (o si activa la regla de excepción).

    La separación se conserva —no es un capricho técnico: es lo que hace que
    cada nivel represente un escenario de caída distinto—, pero deja de ser un
    porcentaje fijo del precio para pasar a medirse en múltiplos de ATR.

    Al final, las zonas elegidas se REORDENAN POR PROXIMIDAD al precio actual,
    de forma que "Nivel 1" siga significando "el primero que tocaría el precio",
    que es como se lee un plan DCA.
    """
    lado = (
        (lambda p: p > precio_ref) if ascendente else (lambda p: p < precio_ref)
    )
    candidatas = [z for z in zonas if lado(z["precio"])]
    # El precio de mercado entra como zona virtual de peso 0.
    referencias = [{"precio": precio_ref, "peso": 0.0}]
    elegidas: list[dict] = []

    for zona in sorted(candidatas, key=lambda z: -z["peso"]):
        if len(elegidas) >= n:
            break
        distancia_precio = abs(zona["precio"] - precio_ref) / precio_ref if precio_ref else 0
        if distancia_precio < DCA_EXCEPCION_DISTANCIA_MIN:
            continue  # suelo absoluto: ninguna excepción pega un nivel al precio
        ok, excepcion = _cumple_separacion(zona, referencias, separacion)
        if not ok:
            continue
        if excepcion:
            zona = {**zona, "excepcion": excepcion}
        elegidas.append(zona)
        referencias.append(zona)

    return sorted(elegidas, key=lambda z: z["precio"], reverse=not ascendente)


def construir_plan(paquete: dict, tecnico: dict, valoracion: dict) -> dict:
    """Genera 3 niveles de entrada, 3 de salida y 1 stop loss."""
    precio = tecnico.get("precio") or paquete.get("precio")
    if not es_valido(precio) or not tecnico.get("disponible"):
        return {"disponible": False, "motivo": "Sin precio o histórico suficiente"}

    fair_value = valoracion.get("fair_value")
    precio = float(precio)
    atr = _num(tecnico.get("atr"))
    confianza = _factor_confianza(tecnico)
    sep_entradas = _separacion_minima(precio, atr, DCA_SEPARACION_ATR_ENTRADAS)
    sep_salidas = _separacion_minima(precio, atr, DCA_SEPARACION_ATR_SALIDAS)

    # ------------------------------------------------------------ entradas --
    zonas_entrada = zonas_confluencia_soporte(precio, tecnico)
    entradas = _seleccionar(zonas_entrada, precio, 3, sep_entradas, ascendente=False)

    # Si la confluencia no da los 3 niveles, se completan por escalones —ahora
    # también proporcionales al ATR, no a un porcentaje fijo—.
    referencia = entradas[-1]["precio"] if entradas else precio
    while len(entradas) < 3:
        siguiente = referencia * (1 - sep_entradas * 1.2)
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
            "excepcion": z.get("excepcion"),
        }
        for i, z in enumerate(entradas[:3])
    ]

    # -------------------------------------------------------------- salidas --
    zonas_salida = _agrupar(
        _en_rango(
            _candidatos_resistencia(precio, tecnico, fair_value),
            precio,
            atr,
            DCA_DISTANCIA_MAX_SALIDAS,
            DCA_DISTANCIA_MIN_SALIDAS,
        ),
        precio,
        atr,
        confianza,
    )
    salidas = _seleccionar(zonas_salida, precio, 3, sep_salidas, ascendente=True)
    referencia = salidas[-1]["precio"] if salidas else precio
    while len(salidas) < 3:
        siguiente = referencia * (1 + sep_salidas * 1.2)
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
            "excepcion": z.get("excepcion"),
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
    # Coherencia del plan: un stop por encima de la última entrada significaría
    # que el plan se detiene antes de haberse llegado a ejecutar del todo.
    stop = min(stop, entrada_baja * (1 - DCA_STOP_MARGEN_MIN))

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
        # Diagnóstico del motor: permite entender por qué salió este plan y no
        # otro sin tener que reproducir el cálculo a mano.
        "motor": {
            "separacion_entradas_pct": sep_entradas * 100,
            "separacion_salidas_pct": sep_salidas * 100,
            "atr_percentil": tecnico.get("atr_percentil"),
            "factor_confianza": confianza,
            "zonas_soporte_detectadas": len(zonas_entrada),
            "zonas_resistencia_detectadas": len(zonas_salida),
        },
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
        if plan.get("ejecutable"):
            motivos.append("Precio en nivel 1")
        else:
            precio_ref = plan.get("precio_referencia")
            entradas = plan.get("entradas") or []
            nivel_1 = entradas[0]["precio"] if entradas else None
            if es_valido(precio_ref) and es_valido(nivel_1) and precio_ref > 0:
                falta_pct = (precio_ref - nivel_1) / precio_ref * 100
                motivos.append(f"A {falta_pct:.1f}".replace(".", ",") + "% del Nivel de Entrada 1")
            else:
                motivos.append("Aún sobre el nivel 1")

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
