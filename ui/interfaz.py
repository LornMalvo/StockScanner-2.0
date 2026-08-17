"""Estructura general: cabecera, navbar de 5 secciones y despacho de vistas.

El orden y los elementos siguen el wireframe: enlace "Home" a la izquierda,
logo centrado, navbar horizontal debajo y el contenido de la sección activa.
"""

from __future__ import annotations

import base64
from functools import lru_cache
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


@lru_cache(maxsize=1)
def _logo_base64() -> str | None:
    """Logo incrustado en la propia página.

    Se incrusta en lugar de usar `st.image` porque este alinea la imagen a la
    izquierda de su columna y no permite centrarla con precisión; con una
    etiqueta <img> propia se controla ancho y centrado desde CSS.
    """
    if not RUTA_LOGO.exists():
        return None
    return base64.b64encode(RUTA_LOGO.read_bytes()).decode("ascii")


def cabecera() -> None:
    logo = _logo_base64()
    if logo:
        st.markdown(
            f'<img class="ss-logo" src="data:image/png;base64,{logo}" alt="{APP_NOMBRE}">',
            unsafe_allow_html=True,
        )
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
