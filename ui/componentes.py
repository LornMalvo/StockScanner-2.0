"""Componentes visuales reutilizables."""

from __future__ import annotations

import html

import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from config.settings import C_AZUL, C_PRIMARIO, C_TEAL, C_VERDE, TEXTO_ND
from utils.formato import es_valido


def titulo_bloque(texto: str) -> None:
    st.markdown(f"#### {texto}")


def boton_favorito(favorito: bool, key: str, ayuda: str | None = None) -> bool:
    """Icono de estrella clicable: rellena y dorada si es favorito, vacía si no.

    Usa un st.button real (mismo ciclo de eventos que cualquier otro botón,
    sin recargas de página) coloreado vía la clase `.st-key-<key>` que
    Streamlit asigna automáticamente al contenedor del widget con esa key
    (ver reglas `.st-key-btn_favorito_on/off` en ui/estilos.py).
    """
    glifo = "★" if favorito else "☆"
    return st.button(
        glifo,
        key=key,
        help=ayuda or ("Quitar de Favoritos" if favorito else "Añadir a Favoritos"),
    )


def metrica(etiqueta: str, valor: str) -> None:
    """Fila etiqueta/valor. Los valores ausentes se marcan explícitamente."""
    clase = "ss-nd" if valor == TEXTO_ND else ""
    st.markdown(
        f'<div class="ss-metrica"><span>{html.escape(etiqueta)}</span>'
        f'<span class="{clase}">{html.escape(str(valor))}</span></div>',
        unsafe_allow_html=True,
    )


def metrica_color(etiqueta: str, valor: str, color: str) -> None:
    """Fila etiqueta/valor con el valor coloreado (p. ej. verde/rojo)."""
    st.markdown(
        f'<div class="ss-metrica"><span>{html.escape(etiqueta)}</span>'
        f'<span style="color:{color};font-weight:700">{html.escape(str(valor))}</span></div>',
        unsafe_allow_html=True,
    )


def metrica_distancia(etiqueta: str, base: str, extra: str, color: str) -> None:
    """Fila etiqueta/valor donde el valor base se muestra en estilo normal y
    solo la distancia % (entre paréntesis) lleva el color verde/rojo."""
    if base == TEXTO_ND:
        metrica(etiqueta, base)
        return
    st.markdown(
        f'<div class="ss-metrica"><span>{html.escape(etiqueta)}</span>'
        f'<span>{html.escape(base)} <span style="color:{color}">({html.escape(extra)})</span></span></div>',
        unsafe_allow_html=True,
    )


def metrica_nota(etiqueta: str, valor: str, nota: str | None = None) -> None:
    """Fila etiqueta/valor con una nota gris opcional a la derecha (sin
    prefijo fijo, p. ej. el nivel de RSI junto a su cifra)."""
    if valor == TEXTO_ND or not nota:
        metrica(etiqueta, valor)
        return
    st.markdown(
        f'<div class="ss-metrica"><span>{html.escape(etiqueta)}</span>'
        f'<span>{html.escape(valor)} <span class="ss-media-sector">{html.escape(nota)}</span></span></div>',
        unsafe_allow_html=True,
    )


def metrica_fundamental(
    etiqueta: str, valor: str, destaca: bool = False, media_sector: str | None = None
) -> None:
    """Fila de fundamentales: el valor se resalta en verde si destaca sobre
    la media de su sector, con la media (opcional) en gris a la derecha."""
    clase = "ss-nd" if valor == TEXTO_ND else ""
    estilo = f"color:{C_VERDE};font-weight:700" if destaca and valor != TEXTO_ND else ""
    media_html = (
        f'<span class="ss-media-sector">media sector: {html.escape(media_sector)}</span>'
        if media_sector
        else ""
    )
    st.markdown(
        f'<div class="ss-metrica"><span>{html.escape(etiqueta)}</span>'
        f'<span><span class="{clase}" style="{estilo}">{html.escape(str(valor))}</span>'
        f"{media_html}</span></div>",
        unsafe_allow_html=True,
    )


def alerta(texto: str, color: str) -> None:
    st.markdown(
        f'<div class="ss-alerta" style="background:{color}">{html.escape(texto)}</div>',
        unsafe_allow_html=True,
    )


def badge(texto: str, color: str) -> None:
    st.markdown(
        f'<span class="ss-badge" style="background:{color}">{html.escape(texto)}</span>',
        unsafe_allow_html=True,
    )


def nota(puntuacion: float | None, color: str, sufijo: str = "/100") -> None:
    """Nota numérica grande + barra de progreso."""
    if not es_valido(puntuacion):
        st.markdown(f'<div class="ss-nd">{TEXTO_ND}</div>', unsafe_allow_html=True)
        return
    ancho = max(0, min(100, float(puntuacion)))
    st.markdown(
        f'<div class="ss-nota" style="color:{color}">{puntuacion:.0f}'
        f'<span style="font-size:.9rem;color:#64748b">{sufijo}</span></div>'
        f'<div class="ss-barra" style="margin-top:.35rem">'
        f'<div style="width:{ancho}%;background:{color}"></div></div>',
        unsafe_allow_html=True,
    )


def lista_noticias(noticias: list[dict]) -> None:
    if not noticias:
        st.markdown(f'<div class="ss-nd">{TEXTO_ND}</div>', unsafe_allow_html=True)
        return
    for n in noticias:
        fecha = n["fecha"].strftime("%d/%m/%Y") if n.get("fecha") else TEXTO_ND
        fuente = html.escape(n.get("fuente") or "")
        st.markdown(
            f'<div class="ss-noticia"><a href="{html.escape(n["url"])}" target="_blank">'
            f'{html.escape(n["titular"])}</a><br><small>{fecha} · {fuente}</small></div>',
            unsafe_allow_html=True,
        )


def nivel_plan(etiqueta: str, precio_txt: str, distancia: str, motivos: list[str]) -> None:
    st.markdown(
        f'<div class="ss-nivel"><span>{html.escape(etiqueta)}</span>'
        f'<b>{html.escape(precio_txt)} <span style="color:#64748b">({distancia})</span></b></div>'
        f'<div class="ss-motivos">{html.escape(" · ".join(motivos))}</div>',
        unsafe_allow_html=True,
    )


def grafico_precio_macd(historico, tecnico: dict, ticker: str) -> None:
    """Velas + MM50/MM200 arriba, MACD abajo, con eje X compartido."""
    if historico is None or historico.empty:
        st.markdown(f'<div class="ss-nd">{TEXTO_ND}</div>', unsafe_allow_html=True)
        return

    df = historico.tail(400)
    series = tecnico.get("series", {})
    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.04,
        row_heights=[0.68, 0.32],
    )

    fig.add_trace(
        go.Candlestick(
            x=df.index,
            open=df["Open"],
            high=df["High"],
            low=df["Low"],
            close=df["Close"],
            name=ticker,
            increasing_line_color=C_VERDE,
            decreasing_line_color="#dc2626",
            showlegend=False,
        ),
        row=1,
        col=1,
    )

    for clave, nombre, color in (("mm50", "MM50", C_AZUL), ("mm200", "MM200", C_PRIMARIO)):
        serie = series.get(clave)
        if serie is not None:
            fig.add_trace(
                go.Scatter(
                    x=df.index,
                    y=serie.reindex(df.index),
                    name=nombre,
                    line=dict(color=color, width=1.4),
                ),
                row=1,
                col=1,
            )

    macd_df = series.get("macd")
    if macd_df is not None:
        macd_df = macd_df.reindex(df.index)
        colores = [C_TEAL if v >= 0 else "#f97316" for v in macd_df["histograma"].fillna(0)]
        fig.add_trace(
            go.Bar(
                x=df.index,
                y=macd_df["histograma"],
                marker_color=colores,
                name="Histograma",
                showlegend=False,
            ),
            row=2,
            col=1,
        )
        fig.add_trace(
            go.Scatter(x=df.index, y=macd_df["macd"], name="MACD", line=dict(color=C_AZUL, width=1.3)),
            row=2,
            col=1,
        )
        fig.add_trace(
            go.Scatter(
                x=df.index, y=macd_df["senal"], name="Señal", line=dict(color="#f97316", width=1.2)
            ),
            row=2,
            col=1,
        )

    fig.update_layout(
        height=430,
        margin=dict(l=8, r=8, t=10, b=8),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis_rangeslider_visible=False,
        legend=dict(orientation="h", y=1.12, x=0, font=dict(size=10)),
        hovermode="x unified",
    )
    fig.update_xaxes(showgrid=False, rangeslider_visible=False)
    fig.update_yaxes(gridcolor="#e2e8f0", zeroline=False)
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
