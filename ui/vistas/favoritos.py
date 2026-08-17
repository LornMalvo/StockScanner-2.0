"""Apartado "Favoritos": tickers guardados en Supabase."""

from __future__ import annotations

import streamlit as st

from config.settings import TEXTO_ND
from core import bd_supabase, datos_api
from ui import componentes as C
from utils.formato import es_valido, fmt_num, fmt_pct


def render() -> None:
    st.markdown("#### Favoritos")

    if not bd_supabase.hay_conexion():
        st.warning(
            "Sin conexión con Supabase. Añade `SUPABASE_URL` y `SUPABASE_KEY` a los secrets "
            "para guardar y consultar favoritos."
        )
        return

    favoritos = bd_supabase.listar_favoritos()
    if not favoritos:
        st.info("Todavía no has marcado ninguna empresa. Usa la estrella del Análisis Individual.")
        return

    for fav in favoritos:
        with st.container(border=True):
            col_id, col_precio, col_var, col_acc = st.columns([3, 1.4, 1.4, 1.4])
            precio = datos_api.obtener_precio_actual(fav["ticker"])
            hist = datos_api.obtener_historico(fav["ticker"], periodo="1mo")
            variacion = None
            if not hist.empty and len(hist) > 1 and es_valido(precio):
                variacion = (precio / float(hist["Close"].iloc[0]) - 1) * 100

            with col_id:
                st.markdown(
                    f"**{fav['ticker']}** — {fav.get('nombre') or TEXTO_ND}  \n"
                    f"<span class='ss-sector'>{fav.get('sector') or TEXTO_ND}</span>",
                    unsafe_allow_html=True,
                )
            with col_precio:
                C.metrica("Precio", fmt_num(precio))
            with col_var:
                C.metrica("1 mes", fmt_pct(variacion))
            with col_acc:
                if st.button("Analizar", key=f"an_{fav['ticker']}", use_container_width=True):
                    st.session_state["entrada_ticker"] = fav["ticker"]
                    st.session_state["seccion"] = "Análisis Individual"
                    st.rerun()
                if st.button("Quitar", key=f"rm_{fav['ticker']}", use_container_width=True):
                    bd_supabase.alternar_favorito(fav["ticker"])
                    st.rerun()
