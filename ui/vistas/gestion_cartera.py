"""Apartado "Gestión de Cartera": posiciones reales abiertas."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from core import bd_supabase, datos_api
from utils.formato import es_valido


def render() -> None:
    st.markdown("#### Gestión de cartera")

    if not bd_supabase.hay_conexion():
        st.warning("Sin conexión con Supabase: configura los secrets para registrar posiciones.")
        return

    with st.expander("Registrar nueva posición"):
        c1, c2, c3, c4 = st.columns(4)
        ticker = c1.text_input("Ticker").strip().upper()
        acciones = c2.number_input("Nº de acciones", min_value=0.0, step=1.0)
        precio = c3.number_input("Precio de compra", min_value=0.0, step=0.01, format="%.2f")
        fecha = c4.date_input("Fecha de compra")
        if st.button("Guardar posición", type="primary"):
            if ticker and acciones > 0 and precio > 0:
                ok = bd_supabase.registrar_posicion_real(
                    {
                        "ticker": ticker,
                        "acciones": acciones,
                        "precio_compra": precio,
                        "fecha_compra": str(fecha),
                        "estado": "abierta",
                    }
                )
                st.success("Posición registrada.") if ok else st.error("No se pudo guardar.")
            else:
                st.warning("Completa ticker, número de acciones y precio de compra.")

    posiciones = bd_supabase.listar_cartera()
    if not posiciones:
        st.info("No hay posiciones registradas.")
        return

    filas, invertido_total, valor_total = [], 0.0, 0.0
    # Una sola petición para el precio de todas las posiciones, en vez de
    # una por posición.
    precios = datos_api.obtener_precios_lote([p["ticker"] for p in posiciones])
    for pos in posiciones:
        precio_actual = precios.get(pos["ticker"])
        invertido = (pos.get("acciones") or 0) * (pos.get("precio_compra") or 0)
        valor = (pos.get("acciones") or 0) * precio_actual if es_valido(precio_actual) else None
        if es_valido(valor):
            invertido_total += invertido
            valor_total += valor
        filas.append(
            {
                "Ticker": pos["ticker"],
                "Acciones": pos.get("acciones"),
                "Precio compra": pos.get("precio_compra"),
                "Precio actual": precio_actual,
                "Invertido": invertido,
                "Valor actual": valor,
                "P/L %": ((valor / invertido - 1) * 100) if es_valido(valor) and invertido else None,
            }
        )

    m1, m2, m3 = st.columns(3)
    m1.metric("Invertido", f"{invertido_total:,.2f}")
    m2.metric("Valor actual", f"{valor_total:,.2f}")
    if invertido_total:
        m3.metric("Rentabilidad", f"{(valor_total / invertido_total - 1) * 100:+.2f} %")

    st.dataframe(pd.DataFrame(filas), use_container_width=True, hide_index=True)
