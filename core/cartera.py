"""Cálculo de la cartera real a partir del libro de operaciones.

MODELO DE DATOS. Una posición NO guarda cifras: guarda quién es (ticker,
divisas, ciclo de vida). Todo lo numérico —acciones vivas, precio medio,
plusvalía latente y realizada— se DERIVA aquí recorriendo `cartera_operaciones`
en orden cronológico. Ese es el motivo del refactor: el modelo plano anterior
(`acciones` / `precio_compra` / `precio_venta` en una sola fila) no soportaba
compras adicionales ni ventas parciales sin destruir el historial.

CONVENCIÓN CONTABLE. Se calculan DOS resultados realizados en paralelo, porque
responden a preguntas distintas y son incompatibles entre sí:

- **Coste medio ponderado** (`realizado`, `precio_medio`): al vender se libera
  coste al precio medio, así que **el precio medio de lo que queda no se
  mueve**. Es la convención elegida para la interfaz.
- **FIFO** (`realizado_fifo`, `fifo_por_ano`): al vender desaparecen los lotes
  más antiguos, así que el coste de lo que queda —y por tanto su precio
  medio— sí cambia. Es la convención fiscalmente exigible en España para
  calcular la ganancia patrimonial del ejercicio.

Los dos métodos dan el mismo resultado total cuando la posición se cierra por
completo; difieren únicamente en el ejercicio en que se reconoce la ganancia.
Como el libro guarda los hechos crudos, ambos se derivan sin almacenar nada y
sin tener que elegir. `realizado_fifo` se calcula pero de momento no se
muestra en la interfaz.

COMISIONES. La comisión de compra suma al coste (sube el precio medio); la de
venta resta del importe recibido. Es el tratamiento estándar y el fiscalmente
correcto.

DIVISA. El coste está en la divisa base de la cartera (EUR: el bróker liquida
ya convertido). La cotización puede venir en otra divisa; `precio_en_eur()`
hace la conversión y devuelve None —nunca un cero ni una estimación— si no hay
tipo de cambio para esa divisa.

Módulo puro: no importa Streamlit ni Supabase, así que es ejecutable y
verificable fuera de la app.
"""

from __future__ import annotations

from collections import deque
from datetime import date, datetime

from config.settings import CARTERA_TOLERANCIA_ACCIONES
from utils.formato import es_valido, num


# ------------------------------------------------------------- utilidades ----
def _fecha(valor) -> date | None:
    """Normaliza a `date` lo que devuelva Supabase (str ISO) o un formulario."""
    if valor is None:
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    try:
        return datetime.fromisoformat(str(valor)[:10]).date()
    except ValueError:
        return None


def _clave_orden(op: dict) -> tuple:
    """Cronológico y, a igualdad de fecha, por orden de inserción (`id`).

    El orden importa de verdad para FIFO: dos operaciones del mismo día
    consumen lotes en el orden en que se registraron.
    """
    f = _fecha(op.get("fecha")) or date.min
    try:
        ident = int(op.get("id") or 0)
    except (TypeError, ValueError):
        ident = 0
    return (f, ident)


def ordenar(operaciones: list[dict]) -> list[dict]:
    return sorted(operaciones or [], key=_clave_orden)


def precio_en_eur(precio, divisa: str | None, fx_usd_eur) -> float | None:
    """Convierte un precio de cotización a EUR.

    Devuelve None si la divisa es desconocida o no hay tipo de cambio para
    ella: un valor sin convertir mezclado con importes en euros es peor que
    un "dato no disponible" honesto.
    """
    if not es_valido(precio):
        return None
    codigo = (divisa or "").strip().upper()
    if codigo == "EUR":
        return float(precio)
    if codigo == "USD" and es_valido(fx_usd_eur):
        return float(precio) * float(fx_usd_eur)
    return None


# --------------------------------------------------------------- validación --
def validar_venta(operaciones: list[dict], acciones) -> str | None:
    """Mensaje de error si la venta no es registrable; None si todo correcto."""
    n = num(acciones)
    if n is None or n <= 0:
        return "El número de acciones a vender debe ser mayor que cero."
    vivas = resumen_posicion(operaciones)["acciones"]
    if n > vivas + CARTERA_TOLERANCIA_ACCIONES:
        return (
            f"No puedes vender {n:g} acciones: la posición solo tiene "
            f"{vivas:g} en cartera."
        )
    return None


# ------------------------------------------------------ resumen de posición --
def resumen_posicion(operaciones: list[dict], precio_actual=None) -> dict:
    """Deriva el estado completo de una posición desde su libro de operaciones.

    `precio_actual` debe llegar YA convertido a la divisa base (EUR); este
    módulo no sabe de tipos de cambio más allá de `precio_en_eur()`.
    """
    ops = ordenar(operaciones)

    acciones = 0.0          # acciones vivas
    coste = 0.0             # coste (comisiones incluidas) de las acciones vivas
    realizado = 0.0         # plusvalía realizada por coste medio
    comisiones = 0.0
    invertido_bruto = 0.0   # todo lo desembolsado en compras a lo largo de la vida
    recuperado = 0.0        # todo lo ingresado en ventas, neto de comisiones
    n_compras = n_ventas = 0
    avisos: list[str] = []

    lotes: deque[list[float]] = deque()   # FIFO: [acciones, coste_unitario]
    realizado_fifo = 0.0
    fifo_por_ano: dict[int, float] = {}

    for op in ops:
        n = num(op.get("acciones"))
        p = num(op.get("precio"))
        c = num(op.get("comisiones")) or 0.0
        if n is None or n <= 0 or p is None or p <= 0:
            avisos.append("Hay una operación con datos incompletos; se ha ignorado.")
            continue

        comisiones += c

        if str(op.get("tipo")) == "compra":
            n_compras += 1
            desembolso = n * p + c
            invertido_bruto += desembolso
            acciones += n
            coste += desembolso
            lotes.append([n, desembolso / n])
            continue

        # ------------------------------------------------------------ venta --
        n_ventas += 1
        if n > acciones + CARTERA_TOLERANCIA_ACCIONES:
            # La interfaz bloquea la sobreventa; esto es un cinturón de
            # seguridad por si el libro se edita por otra vía.
            avisos.append(
                f"Venta de {n:g} acciones con solo {acciones:g} en cartera: "
                "se ha computado únicamente lo disponible."
            )
            n = acciones
        if n <= CARTERA_TOLERANCIA_ACCIONES:
            continue

        ingreso = n * p - c
        recuperado += ingreso

        # --- coste medio: el precio medio de lo que queda NO se mueve --------
        medio = coste / acciones if acciones > CARTERA_TOLERANCIA_ACCIONES else 0.0
        coste_liberado = medio * n
        realizado += ingreso - coste_liberado
        coste -= coste_liberado
        acciones -= n
        if acciones <= CARTERA_TOLERANCIA_ACCIONES:
            # Cierre total: se anula el residuo de coma flotante en vez de
            # arrastrar un coste de 0,0000001 sobre 0 acciones.
            acciones = 0.0
            coste = 0.0

        # --- FIFO en paralelo (solo para el cálculo fiscal) -----------------
        pendiente, coste_fifo = n, 0.0
        while pendiente > CARTERA_TOLERANCIA_ACCIONES and lotes:
            lote = lotes[0]
            usadas = min(lote[0], pendiente)
            coste_fifo += usadas * lote[1]
            lote[0] -= usadas
            pendiente -= usadas
            if lote[0] <= CARTERA_TOLERANCIA_ACCIONES:
                lotes.popleft()
        ganancia_fifo = ingreso - coste_fifo
        realizado_fifo += ganancia_fifo
        anio = (_fecha(op.get("fecha")) or date.min).year
        fifo_por_ano[anio] = fifo_por_ano.get(anio, 0.0) + ganancia_fifo

    # ------------------------------------------------------------- derivados --
    viva = acciones > CARTERA_TOLERANCIA_ACCIONES
    precio_medio = coste / acciones if viva else None

    if not viva:
        # Posición cerrada: el valor de mercado es cero por definición, no un
        # dato ausente.
        valor_actual, latente, latente_pct = 0.0, 0.0, None
    elif es_valido(precio_actual):
        valor_actual = acciones * float(precio_actual)
        latente = valor_actual - coste
        latente_pct = (latente / coste * 100) if coste > 0 else None
    else:
        valor_actual = latente = latente_pct = None

    coste_vendido = invertido_bruto - coste
    realizado_pct = (realizado / coste_vendido * 100) if coste_vendido > 0 else None

    fechas = [f for f in (_fecha(o.get("fecha")) for o in ops) if f]

    return {
        "acciones": acciones,
        "precio_medio": precio_medio,
        "coste_vivo": coste,
        "invertido_bruto": invertido_bruto,
        "recuperado": recuperado,
        "comisiones": comisiones,
        "realizado": realizado,
        "realizado_pct": realizado_pct,
        "realizado_fifo": realizado_fifo,
        "fifo_por_ano": fifo_por_ano,
        "valor_actual": valor_actual,
        "latente": latente,
        "latente_pct": latente_pct,
        "resultado_total": (realizado + latente) if latente is not None else None,
        "n_compras": n_compras,
        "n_ventas": n_ventas,
        "primera_fecha": fechas[0] if fechas else None,
        "ultima_fecha": fechas[-1] if fechas else None,
        "cerrada": not viva and bool(ops),
        "avisos": avisos,
        "operaciones": ops,
    }


# ------------------------------------------------------- resumen de cartera --
def resumen_cartera(resumenes: list[dict]) -> dict:
    """Agrega varias posiciones.

    Regla de oro del proyecto: una posición sin precio actual NO cuenta como
    valor cero. Se excluye del valor de mercado y se reporta la cobertura real
    para que la interfaz pueda advertirlo.
    """
    invertido = valorado = valor_actual = 0.0
    realizado = 0.0
    sin_precio: list[str] = []

    for r in resumenes:
        realizado += r.get("realizado") or 0.0
        if not r.get("acciones"):
            continue
        coste = r.get("coste_vivo") or 0.0
        invertido += coste
        if es_valido(r.get("valor_actual")):
            valorado += coste
            valor_actual += float(r["valor_actual"])
        else:
            sin_precio.append(r.get("ticker") or "?")

    completo = not sin_precio and invertido > 0
    latente = (valor_actual - valorado) if valorado > 0 else None
    return {
        "invertido": invertido,
        "valor_actual": valor_actual if valorado > 0 else None,
        "coste_valorado": valorado,
        "latente": latente,
        "latente_pct": (latente / valorado * 100) if latente is not None and valorado > 0 else None,
        "realizado": realizado,
        "cobertura": (valorado / invertido) if invertido > 0 else 0.0,
        "sin_precio": sin_precio,
        "completo": completo,
    }
