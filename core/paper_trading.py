"""Cálculo del seguimiento de Paper Trading a partir del plan + libro de eventos.

MISMA IDEA QUE `core/cartera.py`, aplicada al mismo problema: un plan DCA se
ejecuta por partes (entrada 1, entrada 2...) igual que una cartera real se
construye a base de compras sucesivas. En vez de reescribir el cálculo de
precio medio / P&L, este módulo TRADUCE las ejecuciones del plan a
operaciones de compra/venta y delega en `core/cartera.py`, ya validado.

DOS FUENTES DE VERDAD QUE NO SE MEZCLAN:
- `paper_trading_niveles` es el PLAN: precios objetivo, estático, congelado
  al guardar. De ahí sale el "precio medio proyectado" (si se llenaran los 3
  niveles) — ya calculado por `plan_dca.construir_plan()` y guardado en la
  cabecera como `precio_medio_estimado` / `objetivo_medio_estimado`.
- `paper_trading_ejecuciones` es el LIBRO DE EVENTOS: lo que de verdad se ha
  "ejecutado" en la simulación. De ahí sale el "precio medio real", que es lo
  único que debería gobernar el P&L. Mostrar solo el proyectado como si fuera
  el real es el error que se pidió evitar explícitamente.

DIVISA. `capital_asignado` está en EUR (la moneda de referencia del usuario).
Los precios de los niveles y de las ejecuciones llegan en la divisa nativa
del ticker. Cada fila de `paper_trading_ejecuciones` lleva su propio
`fx_usd_eur` guardado en el momento de la ejecución (no el de hoy): el coste
en euros de una compra de hace tres meses depende del cambio de entonces, no
del actual. `core/bd_supabase.py::registrar_ejecucion()` exige que esa
conversión sea posible ANTES de guardar la fila — así este módulo nunca tiene
que lidiar con una ejecución sin precio en euros.

Módulo puro: sin Streamlit, sin Supabase, sin llamadas a red.
"""

from __future__ import annotations

from config.settings import CARTERA_TOLERANCIA_ACCIONES
from core import cartera
from utils.formato import es_valido


# ------------------------------------------------------------- máquina de estados --
def derivar_estado(
    n_entradas_totales: int,
    n_entradas_ejecutadas: int,
    hubo_venta: bool,
    acciones_vivas,
    hubo_ejecucion: bool,
) -> str:
    """Estado derivado a partir de lo ejecutado. `descartada` NO se deriva
    aquí: es una acción manual explícita sobre un plan en `vigilancia` que
    nunca llegó a ejecutar nada (ver `bd_supabase.descartar_plan()`).

    `hubo_venta` es "¿ha salido ya alguna acción de la posición?", sin
    importar si esa venta estaba ligada a un nivel de salida planificado o
    fue un cierre manual (stop loss, por ejemplo). Un cierre manual antes de
    completar las tres entradas cuenta igual: si estás vendiendo, ya no
    estás "todavía construyendo la posición".

    Prioridad: una vez empieza a salir dinero, el plan pasa a considerarse
    "en cierre" aunque no se hubieran completado las tres entradas.
    """
    if hubo_ejecucion and (not es_valido(acciones_vivas) or acciones_vivas <= CARTERA_TOLERANCIA_ACCIONES):
        return "cerrada"
    if hubo_venta:
        return "parcial_salida"
    if n_entradas_totales > 0 and n_entradas_ejecutadas >= n_entradas_totales:
        return "abierta"
    if n_entradas_ejecutadas > 0:
        return "parcial_entrada"
    return "vigilancia"


# ------------------------------------------------------------------- adaptador --
def _a_operacion_eur(ejecucion: dict, moneda: str | None) -> dict | None:
    """Traduce una fila de `paper_trading_ejecuciones` a la forma que espera
    `cartera.resumen_posicion()`, con el precio ya convertido a EUR usando el
    tipo de cambio GUARDADO en la propia fila (histórico, no el de hoy).

    None si la conversión no es posible (no debería ocurrir si
    `registrar_ejecucion()` hizo su trabajo; es una red de seguridad, no el
    camino esperado).
    """
    precio_eur = cartera.precio_en_eur(ejecucion.get("precio"), moneda, ejecucion.get("fx_usd_eur"))
    if precio_eur is None:
        return None
    return {
        "id": ejecucion.get("id"),
        "tipo": "compra" if ejecucion.get("tipo") == "entrada" else "venta",
        "acciones": ejecucion.get("acciones"),
        "precio": precio_eur,
        "comisiones": 0.0,  # simulado: sin comisiones de bróker
        "fecha": ejecucion.get("fecha"),
    }


def validar_venta_salida(ejecuciones: list[dict], moneda: str | None, acciones) -> str | None:
    """Bloquea vender más acciones de las que la simulación tiene vivas.
    Reutiliza literalmente la validación de Cartera."""
    operaciones = [o for o in (_a_operacion_eur(e, moneda) for e in ejecuciones) if o]
    return cartera.validar_venta(operaciones, acciones)


def sugerir_acciones(capital_asignado, peso, precio_nivel_nativo, moneda: str | None, fx_actual) -> float | None:
    """Acciones que agotarían la parte de capital asignada a un nivel, al
    precio de ejecución dado. Solo una SUGERENCIA de partida para el
    formulario: el usuario puede corregirla a mano antes de confirmar."""
    if not es_valido(capital_asignado) or not es_valido(peso) or not es_valido(precio_nivel_nativo):
        return None
    precio_eur = cartera.precio_en_eur(precio_nivel_nativo, moneda, fx_actual)
    if not es_valido(precio_eur) or float(precio_eur) <= 0:
        return None
    return (float(capital_asignado) * float(peso)) / float(precio_eur)


# ------------------------------------------------------------- resumen completo --
def resumen_posicion(
    niveles: list[dict],
    ejecuciones: list[dict],
    moneda: str | None,
    precio_actual_nativo,
    fx_actual,
    capital_asignado,
    precio_medio_proyectado=None,
    objetivo_medio_proyectado=None,
) -> dict:
    """Combina plan (niveles) + ejecuciones reales en un único diagnóstico.

    Todas las cifras monetarias del resultado están en EUR. `acciones`,
    `precio_medio` (real, no proyectado), `latente`, `realizado`, etc. vienen
    directamente de `cartera.resumen_posicion()` sobre las ejecuciones
    convertidas — el mismo motor validado para la cartera real.
    """
    ejecuciones = cartera.ordenar(ejecuciones)
    operaciones, sin_convertir = [], []
    for e in ejecuciones:
        o = _a_operacion_eur(e, moneda)
        if o is None:
            sin_convertir.append(e)
        else:
            operaciones.append(o)

    precio_actual_eur = cartera.precio_en_eur(precio_actual_nativo, moneda, fx_actual)
    real = cartera.resumen_posicion(operaciones, precio_actual_eur)

    entradas = [n for n in niveles if n.get("tipo") == "entrada"]
    salidas = [n for n in niveles if n.get("tipo") == "salida"]
    n_entradas_ejecutadas = sum(1 for n in entradas if n.get("ejecutado"))
    n_salidas_ejecutadas = sum(1 for n in salidas if n.get("ejecutado"))
    hubo_ejecucion = bool(operaciones)
    hubo_venta = any(e.get("tipo") == "salida" for e in ejecuciones)

    estado = derivar_estado(
        len(entradas), n_entradas_ejecutadas, hubo_venta, real["acciones"], hubo_ejecucion
    )

    capital_ejecutado = real["invertido_bruto"]  # EUR ya desembolsados en entradas
    capital_pendiente = (
        max(float(capital_asignado) - capital_ejecutado, 0.0) if es_valido(capital_asignado) else None
    )

    avisos = list(real["avisos"])
    if sin_convertir:
        avisos.append(
            f"{len(sin_convertir)} ejecución(es) sin tipo de cambio guardado: excluidas del cálculo en euros."
        )

    # --- salidas cuyo precio queda por debajo del precio medio REAL --------
    # El mismo aviso que hace la app de referencia: un objetivo de venta por
    # debajo de lo que de verdad has pagado de media no es beneficio, es
    # pérdida contenida. Se compara con la divisa/tipo de cambio de HOY
    # porque es una foto del plan visto desde el presente, no un hecho
    # histórico como sí lo son las ejecuciones ya registradas.
    salidas_bajo_medio: dict[int, bool] = {}
    if es_valido(real["precio_medio"]):
        for n in salidas:
            precio_eur = cartera.precio_en_eur(n.get("precio"), moneda, fx_actual)
            salidas_bajo_medio[n.get("nivel")] = (
                es_valido(precio_eur) and float(precio_eur) < real["precio_medio"]
            )

    return {
        **real,
        # ATENCIÓN: NO es el estado autoritativo — nunca puede valer
        # 'descartada' (ver docstring de derivar_estado). El estado que
        # manda para agrupar/mostrar es siempre el de la cabecera
        # (`paper_trading_posiciones.estado`), no esta clave. Solo sirve
        # para que `bd_supabase.sincronizar_estado_paper()` sepa a qué
        # sincronizar la cabecera tras cada ejecución.
        "estado_derivado": estado,
        "progreso": {
            "entradas_ejecutadas": n_entradas_ejecutadas,
            "entradas_totales": len(entradas),
            "salidas_ejecutadas": n_salidas_ejecutadas,
            "salidas_totales": len(salidas),
        },
        "precio_actual_eur": precio_actual_eur,
        "capital_asignado": capital_asignado,
        "capital_ejecutado": capital_ejecutado,
        "capital_pendiente": capital_pendiente,
        "precio_medio_proyectado": precio_medio_proyectado,
        "objetivo_medio_proyectado": objetivo_medio_proyectado,
        "salidas_bajo_medio": salidas_bajo_medio,
        "avisos": avisos,
        "ejecuciones": ejecuciones,
    }
