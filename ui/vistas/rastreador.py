"""Apartado "Rastreador": ejecuta el motor de análisis sobre una lista de
tickers y ordena los resultados por calidad, upside o timing.

Reutiliza `ejecutar_analisis` para que rastreador y análisis individual no
puedan divergir nunca en los criterios de puntuación.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from core import bd_supabase
from ui.vistas.analisis_individual import ejecutar_analisis


def render() -> None:
    st.markdown("#### Rastreador")

    origen = st.radio(
        "Origen de la lista",
        ["Lista manual", "Mis favoritos"],
        horizontal=True,
        label_visibility="collapsed",
    )

    if origen == "Mis favoritos":
        tickers = [f["ticker"] for f in bd_supabase.listar_favoritos()]
        if not tickers:
            st.info("No hay favoritos guardados.")
            return
        st.caption("Tickers: " + ", ".join(tickers))
    else:
        texto = st.text_input(
            "Tickers separados por comas",
            placeholder="AAPL, MSFT, NVDA, KO",
            label_visibility="collapsed",
        )
        tickers = [t.strip().upper() for t in texto.split(",") if t.strip()]

    col_boton, col_orden = st.columns([1, 2])
    with col_orden:
        criterio = st.selectbox(
            "Ordenar por", ["Calidad", "Upside %", "Timing"], label_visibility="collapsed"
        )
    with col_boton:
        lanzar = st.button("Rastrear", type="primary", use_container_width=True)

    if not lanzar:
        return
    if not tickers:
        st.warning("Introduce al menos un ticker.")
        return
    if len(tickers) > 20:
        st.warning("Máximo 20 tickers por lote para no agotar las cuotas de las APIs.")
        tickers = tickers[:20]

    filas = []
    barra = st.progress(0.0, text="Analizando…")
    for i, ticker in enumerate(tickers, start=1):
        barra.progress(i / len(tickers), text=f"Analizando {ticker} ({i}/{len(tickers)})")
        a = ejecutar_analisis(ticker)
        if "error" in a:
            filas.append({"Ticker": ticker, "Empresa": "No encontrado"})
            continue
        filas.append(
            {
                "Ticker": ticker,
                "Empresa": a["paquete"].get("nombre"),
                "Sector": a["paquete"].get("sector"),
                "Precio": a["paquete"].get("precio"),
                "Valor objetivo": a["valoracion"].get("fair_value"),
                "Upside %": a["valoracion"].get("upside_pct"),
                "Calidad": a["calidad"].get("puntuacion"),
                "Timing": a["timing"].get("puntuacion"),
                "Señal": a["timing"].get("senal"),
                "Veredicto": a["veredicto"].get("etiqueta"),
            }
        )
    barra.empty()

    df = pd.DataFrame(filas)
    if criterio in df.columns:
        df = df.sort_values(criterio, ascending=False, na_position="last")
    st.dataframe(df, use_container_width=True, hide_index=True)
    st.caption("Las celdas vacías corresponden a datos no disponibles; no se computan como cero.")
