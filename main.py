"""StockScanner — punto de entrada.

Este archivo se limita a configurar la página y delegar en `ui.interfaz`.
Toda la lógica vive en los módulos de `core/`, `ui/` y `utils/`.

Ejecución local:   streamlit run main.py
"""

from pathlib import Path

import streamlit as st

from config.settings import APP_CLAIM, APP_NOMBRE
from ui import interfaz

RUTA_LOGO = Path(__file__).resolve().parent / "assets" / "logo.png"


def configurar_pagina() -> None:
    st.set_page_config(
        page_title=f"{APP_NOMBRE} · {APP_CLAIM}",
        page_icon=str(RUTA_LOGO) if RUTA_LOGO.exists() else "📈",
        layout="wide",
        initial_sidebar_state="collapsed",
    )


def main() -> None:
    configurar_pagina()
    interfaz.render()


if __name__ == "__main__":
    main()
