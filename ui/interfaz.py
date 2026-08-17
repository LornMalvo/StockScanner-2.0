"""Estructura general: cabecera, navbar de 5 secciones y despacho de vistas.

El orden y los elementos siguen el wireframe: enlace "Home" a la izquierda,
logo centrado, navbar horizontal debajo y el contenido de la sección activa.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from config.settings import APP_CLAIM, APP_NOMBRE, ICONOS_SECCION, SECCIONES
from ui import estilos
from ui.vistas import (
    analisis_individual,
    favoritos,
    gestion_cartera,
    paper_trading,
    rastreador,
)

RUTA_LOGO = Path(__file__).resolve().parent.parent / "assets" / "logo.png"

VISTAS = {
    "Análisis Individual": analisis_individual.render,
    "Rastreador": rastreador.render,
    "Gestión de Cartera": gestion_cartera.render,
    "Paper Trading": paper_trading.render,
    "Favoritos": favoritos.render,
}


def cabecera() -> None:
    izq, centro, der = st.columns([1, 2, 1])
    with izq:
        st.markdown('<div class="ss-home">Home</div>', unsafe_allow_html=True)
    with centro:
        if RUTA_LOGO.exists():
            st.image(str(RUTA_LOGO), use_container_width=True)
        else:
            st.markdown(
                f'<div style="text-align:center"><h2>{APP_NOMBRE}</h2>'
                f"<small>{APP_CLAIM}</small></div>",
                unsafe_allow_html=True,
            )


def navbar() -> str:
    """Navbar de píldoras segmentadas con icono. Devuelve la sección activa.

    Sigue siendo un st.button real por sección (mismo ciclo de eventos que
    cualquier widget de Streamlit): el aspecto de píldora lo da la clase
    `.st-key-navbar_pildoras` que Streamlit asigna automáticamente al
    contenedor (ver ui/estilos.py).
    """
    if "seccion" not in st.session_state:
        st.session_state["seccion"] = SECCIONES[0]

    with st.container(key="navbar_pildoras"):
        columnas = st.columns(len(SECCIONES))
        for columna, seccion in zip(columnas, SECCIONES):
            activa = st.session_state["seccion"] == seccion
            with columna:
                if st.button(
                    seccion,
                    key=f"nav_{seccion}",
                    icon=f":material/{ICONOS_SECCION[seccion]}:",
                    use_container_width=True,
                    type="primary" if activa else "secondary",
                ):
                    st.session_state["seccion"] = seccion
                    st.rerun()
    st.write("")
    return st.session_state["seccion"]


def render() -> None:
    estilos.aplicar()
    cabecera()
    seccion = navbar()
    VISTAS[seccion]()
