"""Apartado "Paper Trading": seguimiento de los planes DCA ejecutados."""

from __future__ import annotations

import streamlit as st

from config.settings import TEXTO_ND
from core import bd_supabase, datos_api
from ui import componentes as C
from utils.formato import es_valido, fmt_fecha, fmt_num, fmt_pct


def render() -> None:
    st.markdown("#### Paper Trading")

    if not bd_supabase.hay_conexion():
        st.warning("Sin conexión con Supabase: las operaciones simuladas no se pueden recuperar.")
        return

    estado = st.radio(
        "Estado", ["abierta", "cerrada"], horizontal=True, label_visibility="collapsed"
    )
    posiciones = bd_supabase.listar_paper_trades(estado)
    if not posiciones:
        st.info(
            "No hay posiciones simuladas. Ejecuta un plan DCA desde el Análisis Individual."
            if estado == "abierta"
            else "Todavía no has cerrado ninguna posición simulada."
        )
        return

    for pos in posiciones:
        precio_actual = datos_api.obtener_precio_actual(pos["ticker"])
        entrada = pos.get("precio_apertura")
        rendimiento = (
            (precio_actual / entrada - 1) * 100
            if es_valido(precio_actual) and es_valido(entrada) and entrada
            else None
        )

        with st.container(border=True):
            cab, met, acc = st.columns([2.2, 2.4, 1.2])
            with cab:
                st.markdown(f"**{pos['ticker']}** · {pos.get('veredicto') or TEXTO_ND}")
                st.caption(f"Abierta el {fmt_fecha(pos.get('abierta_en'))}")
            with met:
                C.metrica("Precio de apertura", fmt_num(entrada))
                C.metrica("Precio actual", fmt_num(precio_actual))
                C.metrica("Rendimiento", fmt_pct(rendimiento))
                C.metrica("Stop loss", fmt_num(pos.get("stop_loss")))
            with acc:
                if estado == "abierta" and st.button(
                    "Cerrar", key=f"cerrar_{pos['id']}", use_container_width=True
                ):
                    if es_valido(precio_actual):
                        bd_supabase.cerrar_paper_trade(pos["id"], float(precio_actual))
                        st.rerun()
                    else:
                        st.error(f"Precio actual: {TEXTO_ND}. No se puede cerrar.")

            niveles = bd_supabase.listar_niveles(pos["id"])
            if niveles:
                with st.expander("Niveles del plan"):
                    for n in niveles:
                        alcanzado = (
                            es_valido(precio_actual)
                            and (
                                (n["tipo"] == "entrada" and precio_actual <= n["precio"])
                                or (n["tipo"] == "salida" and precio_actual >= n["precio"])
                            )
                        )
                        marca = "✔ alcanzado" if alcanzado else "pendiente"
                        C.metrica(
                            f"{n['tipo'].capitalize()} {n['nivel']} — {n.get('motivos') or ''}",
                            f"{fmt_num(n['precio'])}  ·  {marca}",
                        )
