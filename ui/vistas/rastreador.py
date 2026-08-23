"""Apartado "Rastreador": ejecuta el motor de análisis sobre una lista de
tickers y ordena los resultados por calidad, upside o timing.

Reutiliza `ejecutar_analisis` para que rastreador y análisis individual no
puedan divergir nunca en los criterios de puntuación.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from core import bd_supabase, datos_api
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
    if len(tickers) > 10:
        st.warning(
            "Máximo 10 tickers por lote. Cada análisis implica varias peticiones a Yahoo "
            "Finance y lotes mayores disparan el límite por IP."
        )
        tickers = tickers[:10]

    filas = []
    barra = st.progress(0.0, text="Analizando…")

    # Instrumentación: mide solo este rastreo, no lo acumulado de la sesión.
    datos_api.reset_metricas()

    # Precalienta en una sola petición HTTP el histórico de todos los
    # tickers del lote (yf.download en vez de N llamadas history()). El
    # bucle de abajo, al llamar a ejecutar_analisis -> obtener_paquete ->
    # obtener_historico(ticker), encuentra la caché ya caliente y no vuelve
    # a tocar la red para esa pieza.
    barra.progress(0.0, text="Descargando histórico en lote…")
    datos_api.obtener_historicos_lote(tickers)

    for i, ticker in enumerate(tickers, start=1):
        barra.progress(i / len(tickers), text=f"Analizando {ticker} ({i}/{len(tickers)})")
        # incluir_noticias=False: no alimentan ningún cálculo del rastreo,
        # solo se muestran en el Análisis Individual.
        a = ejecutar_analisis(ticker, incluir_noticias=False)
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
    datos_api.log_resumen_metricas(f"Rastreador ({len(tickers)} tickers)")

    df = pd.DataFrame(filas)
    if criterio in df.columns:
        df = df.sort_values(criterio, ascending=False, na_position="last")
    st.dataframe(df, use_container_width=True, hide_index=True)
    st.caption("Las celdas vacías corresponden a datos no disponibles; no se computan como cero.")
