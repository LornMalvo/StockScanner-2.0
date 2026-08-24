"""Apartado "Gestión de Cartera": posiciones reales sobre libro de operaciones.

La vista no calcula nada por su cuenta: pide el libro a `bd_supabase` y se lo
pasa a `core/cartera.py`, que deriva acciones vivas, precio medio y P&L. Aquí
solo queda el formateo y la interacción.

DIVISA. El coste vive en euros (el bróker liquida convertido), pero la
cotización de yfinance viene en la divisa nativa del valor. Cada cabecera
guarda `divisa_cotizacion` para poder convertir; si falta, se detecta una vez
y se persiste. Si la divisa no es convertible (ni EUR ni USD), el valor de
mercado se muestra como "dato no disponible" en vez de mezclar monedas.
"""

from __future__ import annotations

from datetime import date

import streamlit as st

from config.settings import (
    CARTERA_DIVISAS_CONVERTIBLES,
    C_ROJO,
    C_TEXTO_TENUE,
    C_VERDE,
    TEXTO_ND,
)
from core import bd_supabase, cartera, datos_api
from ui import componentes as C
from utils.formato import es_valido, fmt_eur, fmt_fecha, fmt_num, fmt_pct


# ------------------------------------------------------------- utilidades ----
def _color(valor) -> str:
    if not es_valido(valor):
        return C_TEXTO_TENUE
    return C_VERDE if float(valor) >= 0 else C_ROJO


def _detectar_divisa(ticker: str) -> str | None:
    """Divisa de cotización del ticker según yfinance. None si no se resuelve.

    Una sola petición (además cacheada) por posición y para siempre: el
    resultado se persiste en la cabecera.
    """
    try:
        info = datos_api.obtener_info(ticker) or {}
        divisa = info.get("currency")
        return str(divisa).upper() if divisa else None
    except Exception:
        return None


def _fmt_acciones(valor) -> str:
    """Acciones sin decimales cuando son enteras (Trade Republic permite
    fracciones, así que no se puede formatear siempre como entero)."""
    if not es_valido(valor):
        return TEXTO_ND
    v = float(valor)
    return fmt_num(v, 0) if abs(v - round(v)) < 1e-9 else fmt_num(v, 4)


# ------------------------------------------------------------ carga de datos --
def _cargar() -> tuple[list[dict], dict]:
    """Devuelve (cabeceras, resúmenes por posicion_id).

    Dos peticiones a Supabase (cabeceras + libro completo) y una sola de
    precios en lote para todas las posiciones abiertas.
    """
    posiciones = bd_supabase.listar_cartera()
    libro = bd_supabase.operaciones_por_posicion()
    abiertas = [p for p in posiciones if p.get("estado") == "abierta"]
    precios = (
        datos_api.obtener_precios_lote([p["ticker"] for p in abiertas]) if abiertas else {}
    )
    fx = datos_api.obtener_fx_usd_eur()

    resumenes: dict = {}
    for p in posiciones:
        divisa = p.get("divisa_cotizacion")
        if not divisa and p.get("estado") == "abierta":
            divisa = _detectar_divisa(p["ticker"])
            if divisa:
                bd_supabase.actualizar_divisa_cotizacion(p["id"], divisa)
                p["divisa_cotizacion"] = divisa
        precio_eur = cartera.precio_en_eur(precios.get(p["ticker"]), divisa, fx)
        resumen = cartera.resumen_posicion(libro.get(p["id"], []), precio_eur)
        resumen["ticker"] = p["ticker"]
        resumen["precio_actual_eur"] = precio_eur
        resumen["divisa_cotizacion"] = divisa
        resumenes[p["id"]] = resumen
    return posiciones, resumenes


# ------------------------------------------------------------- agregados -----
def _cabecera(resumenes: dict) -> None:
    total = cartera.resumen_cartera(list(resumenes.values()))

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Invertido", fmt_eur(total["invertido"]))
    c2.metric("Valor actual", fmt_eur(total["valor_actual"]))
    c3.metric(
        "P/L latente",
        fmt_eur(total["latente"], signo=True),
        delta=fmt_pct(total["latente_pct"]) if es_valido(total["latente_pct"]) else None,
    )
    c4.metric("P/L realizado", fmt_eur(total["realizado"], signo=True))

    if total["sin_precio"]:
        st.caption(
            "⚠ Sin cotización convertible para "
            + ", ".join(total["sin_precio"])
            + f" — quedan fuera del valor de mercado (cobertura {total['cobertura'] * 100:.0f} %). "
            "Se admiten cotizaciones en "
            + " y ".join(CARTERA_DIVISAS_CONVERTIBLES)
            + "."
        )


# -------------------------------------------------------- alta de posición ---
def _formulario_compra() -> None:
    with st.expander("Registrar compra"):
        st.caption(
            "Importes en euros, tal como los liquida el bróker. Si ya tienes una "
            "posición abierta de ese ticker, la compra se añade a su libro y "
            "recalcula el precio medio; si no, abre una posición nueva."
        )
        with st.form("form_compra_nueva", clear_on_submit=True):
            c1, c2, c3, c4, c5 = st.columns([1.2, 1, 1, 1, 1.1])
            ticker = c1.text_input("Ticker").strip().upper()
            acciones = c2.number_input(
                "Acciones", min_value=0.0, step=1.0, format="%.4f", key="alta_acciones"
            )
            precio = c3.number_input(
                "Precio (€)", min_value=0.0, step=0.01, format="%.4f", key="alta_precio"
            )
            comisiones = c4.number_input(
                "Comisiones (€)", min_value=0.0, step=0.5, format="%.2f", key="alta_comis"
            )
            fecha = c5.date_input("Fecha", value=date.today(), key="alta_fecha")
            enviado = st.form_submit_button("Registrar compra", type="primary")

        if enviado:
            if not ticker or acciones <= 0 or precio <= 0:
                st.warning("Completa ticker, acciones y precio (mayores que cero).")
                return
            divisa = _detectar_divisa(ticker)
            if bd_supabase.registrar_compra(
                ticker,
                acciones,
                precio,
                fecha,
                comisiones=comisiones,
                divisa_cotizacion=divisa,
            ):
                st.rerun()
            else:
                st.error(
                    "No se ha podido registrar la compra. Revisa la conexión con Supabase."
                )


# ------------------------------------------------------- tarjeta de posición --
def _operar(pos: dict, resumen: dict) -> None:
    """Compra adicional y venta (total o parcial) sobre una posición viva.

    Todos los widgets llevan `key` explícita: sin ella, Streamlit deriva el
    identificador de los parámetros del widget y dos campos idénticos
    ("Precio (€)", mismo mínimo, mismo paso, mismo formato) en las pestañas
    de compra y de venta pueden colisionar. El manejo del envío va FUERA del
    bloque `with st.form`, para que los mensajes de error no se dibujen
    dentro del propio formulario.
    """
    ident = pos["id"]
    with st.expander("Operar"):
        t_compra, t_venta = st.tabs(["Comprar más", "Vender"])

        with t_compra:
            with st.form(f"form_compra_{ident}", clear_on_submit=True):
                c1, c2, c3, c4 = st.columns(4)
                n_c = c1.number_input(
                    "Acciones", min_value=0.0, step=1.0, format="%.4f", key=f"c_acc_{ident}"
                )
                p_c = c2.number_input(
                    "Precio (€)", min_value=0.0, step=0.01, format="%.4f", key=f"c_pre_{ident}"
                )
                com_c = c3.number_input(
                    "Comisiones (€)", min_value=0.0, step=0.5, format="%.2f", key=f"c_com_{ident}"
                )
                f_c = c4.date_input("Fecha", value=date.today(), key=f"c_fec_{ident}")
                enviar_compra = st.form_submit_button("Añadir compra", type="primary")

            if enviar_compra:
                if n_c <= 0 or p_c <= 0:
                    st.warning("Acciones y precio deben ser mayores que cero.")
                elif bd_supabase.registrar_compra(
                    pos["ticker"],
                    n_c,
                    p_c,
                    f_c,
                    comisiones=com_c,
                    divisa_cotizacion=pos.get("divisa_cotizacion"),
                ):
                    st.rerun()
                else:
                    st.error("No se ha podido registrar la compra.")

        with t_venta:
            with st.form(f"form_venta_{ident}", clear_on_submit=True):
                c1, c2, c3, c4 = st.columns(4)
                n_v = c1.number_input(
                    "Acciones",
                    min_value=0.0,
                    max_value=float(resumen["acciones"]),
                    value=float(resumen["acciones"]),
                    step=1.0,
                    format="%.4f",
                    key=f"v_acc_{ident}",
                )
                p_v = c2.number_input(
                    "Precio (€)", min_value=0.0, step=0.01, format="%.4f", key=f"v_pre_{ident}"
                )
                com_v = c3.number_input(
                    "Comisiones (€)", min_value=0.0, step=0.5, format="%.2f", key=f"v_com_{ident}"
                )
                f_v = c4.date_input("Fecha", value=date.today(), key=f"v_fec_{ident}")
                st.caption(
                    "Venta parcial: el precio medio de las acciones que quedan no varía "
                    "(coste medio ponderado)."
                )
                enviar_venta = st.form_submit_button("Registrar venta", type="primary")

            if enviar_venta:
                error = cartera.validar_venta(resumen["operaciones"], n_v)
                if error:
                    st.warning(error)
                elif p_v <= 0:
                    st.warning("El precio de venta debe ser mayor que cero.")
                elif bd_supabase.registrar_venta(
                    ident, pos["ticker"], n_v, p_v, f_v, comisiones=com_v
                ):
                    st.rerun()
                else:
                    st.error("No se ha podido registrar la venta.")


def _libro(pos: dict, resumen: dict) -> None:
    with st.expander(f"Libro de operaciones ({len(resumen['operaciones'])})"):
        anchos = [1.1, 1.4, 1.2, 1.4, 1.2, 1.4, 0.6]
        cab = st.columns(anchos)
        for col, texto in zip(
            cab, ("Tipo", "Fecha", "Acciones", "Precio", "Comisión", "Importe", "")
        ):
            col.caption(f"**{texto}**")

        for op in resumen["operaciones"]:
            fila = st.columns(anchos)
            es_compra = op.get("tipo") == "compra"
            # El importe refleja el flujo de caja real: la comisión se suma al
            # desembolso de la compra y se resta del ingreso de la venta.
            importe = (op.get("acciones") or 0) * (op.get("precio") or 0) + (
                1 if es_compra else -1
            ) * (op.get("comisiones") or 0)
            fila[0].markdown(f"**{'Compra' if es_compra else 'Venta'}**")
            fila[1].write(fmt_fecha(op.get("fecha")))
            fila[2].write(_fmt_acciones(op.get("acciones")))
            fila[3].write(fmt_eur(op.get("precio")))
            fila[4].write(fmt_eur(op.get("comisiones")))
            fila[5].write(fmt_eur(importe))
            if fila[6].button(
                "🗑", key=f"del_{op['id']}", help="Eliminar esta operación del libro"
            ):
                if bd_supabase.eliminar_operacion(op["id"], pos["id"]):
                    st.rerun()
                else:
                    st.error("No se ha podido eliminar la operación.")

        st.caption(
            f"Comisiones acumuladas: {fmt_eur(resumen['comisiones'])} · "
            f"Desembolsado: {fmt_eur(resumen['invertido_bruto'])} · "
            f"Recuperado en ventas: {fmt_eur(resumen['recuperado'])}"
        )


def _tarjeta(pos: dict, resumen: dict) -> None:
    abierta = pos.get("estado") == "abierta"

    with st.container(border=True):
        cab, met = st.columns([1.6, 2.6])

        with cab:
            st.markdown(f"### {pos['ticker']}")
            if pos.get("nombre"):
                st.caption(pos["nombre"])
            if abierta:
                st.caption(
                    f"{_fmt_acciones(resumen['acciones'])} acciones · "
                    f"desde el {fmt_fecha(resumen['primera_fecha'])}"
                )
            else:
                st.caption(
                    f"Cerrada el {fmt_fecha(pos.get('cerrada_en') or resumen['ultima_fecha'])} · "
                    f"{resumen['n_compras']} compras / {resumen['n_ventas']} ventas"
                )

        with met:
            if abierta:
                C.metrica("Precio medio", fmt_eur(resumen["precio_medio"]))
                C.metrica("Precio actual", fmt_eur(resumen["precio_actual_eur"]))
                C.metrica("Coste", fmt_eur(resumen["coste_vivo"]))
                C.metrica("Valor actual", fmt_eur(resumen["valor_actual"]))
                C.metrica_distancia(
                    "P/L latente",
                    fmt_eur(resumen["latente"], signo=True),
                    fmt_pct(resumen["latente_pct"]),
                    _color(resumen["latente"]),
                )
                if abs(resumen["realizado"]) > 0.005:
                    C.metrica_color(
                        "P/L realizado (ventas previas)",
                        fmt_eur(resumen["realizado"], signo=True),
                        _color(resumen["realizado"]),
                    )
            else:
                C.metrica("Desembolsado", fmt_eur(resumen["invertido_bruto"]))
                C.metrica("Recuperado", fmt_eur(resumen["recuperado"]))
                C.metrica_distancia(
                    "Resultado de la operación",
                    fmt_eur(resumen["realizado"], signo=True),
                    fmt_pct(resumen["realizado_pct"]),
                    _color(resumen["realizado"]),
                )

        for aviso in resumen["avisos"]:
            st.warning(aviso)

        if abierta and not es_valido(resumen["precio_actual_eur"]):
            cotiza = (
                f" (cotiza en {resumen['divisa_cotizacion']})"
                if resumen.get("divisa_cotizacion")
                else ""
            )
            st.caption(
                f"Sin cotización convertible a euros{cotiza}: el valor de mercado y "
                "el P/L latente no se pueden calcular."
            )

        if abierta:
            _operar(pos, resumen)
        _libro(pos, resumen)


# ------------------------------------------------------------------ render ---
def render() -> None:
    st.markdown("#### Gestión de cartera")

    if not bd_supabase.hay_conexion():
        st.warning("Sin conexión con Supabase: configura los secrets para registrar posiciones.")
        return

    posiciones, resumenes = _cargar()

    _cabecera(resumenes)
    st.divider()
    _formulario_compra()

    # NOTA: `resumen["realizado_fifo"]` y `resumen["fifo_por_ano"]` ya se
    # calculan en core/cartera.py (ganancia patrimonial por ejercicio según
    # FIFO, la convención fiscal española). No se muestran todavía: quedan
    # listos para cuando se aborde el apartado de fiscalidad.

    if not posiciones:
        st.info("No hay posiciones registradas. Empieza registrando una compra.")
        return

    abiertas = [p for p in posiciones if p.get("estado") == "abierta"]
    cerradas = [p for p in posiciones if p.get("estado") != "abierta"]

    t_abiertas, t_cerradas = st.tabs(
        [f"Abiertas ({len(abiertas)})", f"Cerradas ({len(cerradas)})"]
    )
    with t_abiertas:
        if not abiertas:
            st.info("No hay posiciones abiertas.")
        for pos in abiertas:
            _tarjeta(pos, resumenes[pos["id"]])
    with t_cerradas:
        if not cerradas:
            st.info("Todavía no has cerrado ninguna posición.")
        for pos in cerradas:
            _tarjeta(pos, resumenes[pos["id"]])
