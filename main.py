"""StockScanner — punto de entrada.

Este archivo se limita a configurar la página y delegar en `ui.interfaz`.
Toda la lógica vive en los módulos de `core/`, `ui/` y `utils/`.

Ejecución local:   streamlit run main.py
"""

import logging
from pathlib import Path

import streamlit as st

from config.settings import APP_CLAIM, APP_NOMBRE
from ui import interfaz

RUTA_LOGO = Path(__file__).resolve().parent / "assets" / "logo.png"

# Sin esto, el logger raíz de Python queda en su nivel por defecto (WARNING)
# y los `logger.info(...)` de core/datos_api.py (métricas de peticiones a
# la API) se descartan en silencio: no aparecen ni en consola local ni en
# los logs de "Manage app" de Streamlit Community Cloud. `basicConfig` es
# idempotente (solo configura el root logger si no tiene handlers todavía),
# así que no pasa nada porque Streamlit re-ejecute este módulo en cada
# interacción del usuario.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


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
