"""Hoja de estilos de la app. Fondo claro, tarjetas de borde redondeado y la
paleta corporativa expuesta como variables CSS."""

import streamlit as st

from config.settings import (
    C_AMBAR,
    C_AZUL,
    C_BORDE,
    C_FONDO,
    C_PRIMARIO,
    C_SUPERFICIE,
    C_TEAL,
    C_TEXTO,
    C_TEXTO_TENUE,
    C_VERDE,
)

CSS = f"""
<style>
:root {{
  --ss-primario: {C_PRIMARIO};
  --ss-azul: {C_AZUL};
  --ss-verde: {C_VERDE};
  --ss-teal: {C_TEAL};
  --ss-ambar: {C_AMBAR};
  --ss-fondo: {C_FONDO};
  --ss-superficie: {C_SUPERFICIE};
  --ss-texto: {C_TEXTO};
  --ss-tenue: {C_TEXTO_TENUE};
  --ss-borde: {C_BORDE};
}}

.stApp {{ background: var(--ss-fondo); }}
html, body, [class*="css"] {{
  font-family: "Inter", "Segoe UI", system-ui, -apple-system, sans-serif;
  color: var(--ss-texto);
}}
.block-container {{ padding-top: 1.2rem; max-width: 1500px; }}

/* --- cabecera --- */
.ss-home {{ font-size: .95rem; color: var(--ss-tenue); font-weight: 600; }}
.ss-logo {{ display: block; margin: 0 auto; }}

/* --- navbar --- */
div[data-testid="stTabs"] button[data-baseweb="tab"] {{
  font-weight: 700; letter-spacing: .04em; text-transform: uppercase;
  font-size: .82rem; color: var(--ss-tenue);
}}
div[data-testid="stTabs"] button[aria-selected="true"] {{ color: var(--ss-primario); }}
div[data-testid="stTabs"] div[data-baseweb="tab-highlight"] {{ background: var(--ss-azul); }}

/* --- tarjetas de bloque --- */
.ss-card {{
  background: var(--ss-superficie);
  border: 1.5px solid var(--ss-borde);
  border-radius: 18px;
  padding: 1.1rem 1.25rem;
  height: 100%;
}}
.ss-card h4 {{
  margin: 0 0 .8rem 0; font-size: .95rem; font-weight: 700;
  color: var(--ss-primario); letter-spacing: .01em;
}}
div[data-testid="stVerticalBlockBorderWrapper"] {{ border-radius: 18px; }}

/* --- etiquetas de cabecera de análisis --- */
.ss-etiqueta {{
  font-size: .72rem; text-transform: uppercase; letter-spacing: .12em;
  color: var(--ss-tenue); font-weight: 700; margin-bottom: .15rem;
}}
.ss-ticker {{ font-size: 1.9rem; font-weight: 800; color: var(--ss-primario); line-height: 1.1; }}
.ss-empresa {{ font-size: 1rem; color: var(--ss-texto); }}
.ss-sector {{ font-size: .88rem; color: var(--ss-tenue); }}
.ss-precio {{ font-size: 1.7rem; font-weight: 800; color: var(--ss-azul); line-height: 1.1; }}
.ss-precio-eur {{ font-size: .95rem; color: var(--ss-tenue); }}

/* --- alertas y badges --- */
.ss-alerta {{
  border-radius: 12px; padding: .65rem .85rem; color: #fff;
  font-weight: 700; font-size: .88rem; text-align: center;
}}
.ss-badge {{
  display: inline-block; border-radius: 999px; padding: .18rem .6rem;
  font-size: .72rem; font-weight: 700; color: #fff;
}}
.ss-nd {{ color: var(--ss-tenue); font-style: italic; }}

/* --- métricas en rejilla --- */
.ss-metrica {{
  display: flex; justify-content: space-between; gap: .5rem;
  padding: .3rem 0; border-bottom: 1px dashed var(--ss-borde); font-size: .86rem;
}}
.ss-metrica span:first-child {{ color: var(--ss-tenue); }}
.ss-metrica span:last-child {{ font-weight: 600; font-variant-numeric: tabular-nums; }}

/* --- noticias --- */
.ss-noticia {{ padding: .35rem 0; border-bottom: 1px solid var(--ss-borde); font-size: .85rem; }}
.ss-noticia a {{ color: var(--ss-azul); text-decoration: none; font-weight: 600; }}
.ss-noticia a:hover {{ text-decoration: underline; }}
.ss-noticia small {{ color: var(--ss-tenue); }}

/* --- barra de puntuación --- */
.ss-barra {{ background: var(--ss-borde); border-radius: 999px; height: 10px; overflow: hidden; }}
.ss-barra > div {{ height: 100%; border-radius: 999px; }}
.ss-nota {{ font-size: 2.1rem; font-weight: 800; line-height: 1; }}

/* --- niveles del plan DCA --- */
.ss-nivel {{
  display: flex; justify-content: space-between; align-items: baseline;
  padding: .32rem .55rem; border-radius: 9px; margin-bottom: .28rem;
  background: #f1f5f9; font-size: .84rem;
}}
.ss-nivel b {{ font-variant-numeric: tabular-nums; }}
.ss-motivos {{ font-size: .72rem; color: var(--ss-tenue); margin: -.15rem 0 .45rem .55rem; }}

/* --- botones --- */
.stButton > button {{ border-radius: 10px; font-weight: 600; }}
.stButton > button[kind="primary"] {{ background: var(--ss-azul); border-color: var(--ss-azul); }}
</style>
"""


def aplicar() -> None:
    st.markdown(CSS, unsafe_allow_html=True)
