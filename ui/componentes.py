"""Componentes visuales reutilizables."""

from __future__ import annotations

import html

import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from config.settings import C_AZUL, C_PRIMARIO, C_ROJO, C_TEAL, C_VERDE, TEXTO_ND
from utils.formato import es_valido, fmt_num, fmt_pct


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


def metrica(etiqueta: str, valor: str, ayuda: str | None = None) -> None:
    """Fila etiqueta/valor. Los valores ausentes se marcan explícitamente.

    Si se pasa `ayuda`, la etiqueta muestra un tooltip nativo del navegador
    (atributo `title`) al posar el ratón encima -- sin dependencias nuevas,
    aunque no es accesible por tacto puro en móvil (ahí queda como texto
    normal, sin el subrayado punteado)."""
    clase = "ss-nd" if valor == TEXTO_ND else ""
    if ayuda:
        etiqueta_html = (
            f'<span title="{html.escape(ayuda)}" '
            f'style="cursor:help;border-bottom:1px dotted #94a3b8">{html.escape(etiqueta)}</span>'
        )
    else:
        etiqueta_html = f"<span>{html.escape(etiqueta)}</span>"
    st.markdown(
        f'<div class="ss-metrica">{etiqueta_html}'
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


def metrica_pastilla(etiqueta: str, texto_pastilla: str, color: str) -> None:
    """Fila etiqueta/valor donde el valor se muestra como pastilla de color
    (mismo estilo que `badge`, pero alineado en la rejilla de métricas junto
    a su etiqueta). Pensado para estados categóricos con pocos valores
    posibles (p. ej. consenso de analistas: compra fuerte/compra/mantener/
    venta/venta fuerte), donde el color comunica la lectura de un vistazo."""
    if texto_pastilla == TEXTO_ND:
        metrica(etiqueta, texto_pastilla)
        return
    st.markdown(
        f'<div class="ss-metrica"><span>{html.escape(etiqueta)}</span>'
        f'<span class="ss-badge" style="background:{color}">{html.escape(texto_pastilla)}</span></div>',
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


# --------------------------------------------------- superposición plan DCA --
# Opacidad decreciente por nivel: el nivel 1 (el más cercano y el de mayor peso
# de capital) es el más sólido, el 3 el más tenue.
_PLAN_OPACIDADES = (0.90, 0.65, 0.45)


def _niveles_plan_dca(plan: dict) -> list[dict]:
    """Aplana el plan DCA en una lista de líneas dibujables.

    Devuelve, por cada nivel: precio, etiqueta corta, color, opacidad, tipo de
    trazo y grosor. Los niveles sin precio válido se descartan (regla del
    proyecto: un dato ausente no se sustituye por nada, simplemente no se
    pinta).
    """
    lineas: list[dict] = []

    for n in plan.get("entradas") or []:
        if not es_valido(n.get("precio")):
            continue
        indice = int(n.get("nivel", len(lineas) + 1)) - 1
        lineas.append(
            {
                "precio": float(n["precio"]),
                "etiqueta": f"E{n.get('nivel', indice + 1)}",
                "distancia_pct": n.get("distancia_pct"),
                "color": C_VERDE,
                "opacidad": _PLAN_OPACIDADES[min(max(indice, 0), 2)],
                "trazo": "dash",
                "grosor": 1.3,
            }
        )

    for n in plan.get("salidas") or []:
        if not es_valido(n.get("precio")):
            continue
        indice = int(n.get("nivel", len(lineas) + 1)) - 1
        lineas.append(
            {
                "precio": float(n["precio"]),
                "etiqueta": f"S{n.get('nivel', indice + 1)}",
                "distancia_pct": n.get("distancia_pct"),
                "color": C_TEAL,
                "opacidad": _PLAN_OPACIDADES[min(max(indice, 0), 2)],
                "trazo": "dot",
                "grosor": 1.3,
            }
        )

    sl = plan.get("stop_loss") or {}
    if es_valido(sl.get("precio")):
        lineas.append(
            {
                "precio": float(sl["precio"]),
                "etiqueta": "SL",
                "distancia_pct": sl.get("distancia_pct"),
                "color": C_ROJO,
                "opacidad": 0.95,
                "trazo": "dashdot",
                "grosor": 1.8,
            }
        )

    return lineas


def _pintar_plan_dca(fig, plan: dict, df) -> int:
    """Superpone las entradas, salidas y stop loss del plan sobre las velas.

    Se dibujan como `shapes` (add_hline) y no como trazas: así no ensucian la
    leyenda ni el hover unificado del eje X, y no se cuelan en el subgráfico
    del MACD. Las etiquetas van fuera del área de dibujo (margen derecho) para
    no taparlas con las velas.

    Devuelve los píxeles de margen derecho que necesita reservar el llamante
    para que no se corte ninguna etiqueta (0 si no ha pintado nada).
    """
    lineas = _niveles_plan_dca(plan)
    if not lineas:
        return 0

    ancho_etiqueta = 0
    for linea in lineas:
        fig.add_hline(
            y=linea["precio"],
            line=dict(color=linea["color"], width=linea["grosor"], dash=linea["trazo"]),
            opacity=linea["opacidad"],
            row=1,
            col=1,
        )
        distancia = fmt_pct(linea["distancia_pct"])
        texto = f"{linea['etiqueta']} · {fmt_num(linea['precio'])}"
        if distancia != TEXTO_ND:
            texto += f" ({distancia})"
        ancho_etiqueta = max(ancho_etiqueta, len(texto))
        fig.add_annotation(
            xref="x domain",
            x=1.008,
            xanchor="left",
            yref="y",
            y=linea["precio"],
            yanchor="middle",
            text=texto,
            showarrow=False,
            align="left",
            font=dict(size=9, color=linea["color"]),
            opacity=max(linea["opacidad"], 0.75),
        )

    # El eje Y se fija a mano para que quepa el plan completo aunque algún
    # nivel caiga fuera del rango de las velas visibles: ver el plan en
    # contexto importa más que la amplitud de la vela (decisión consciente;
    # un stop lejano aplanará algo el gráfico). No se delega en el autorango
    # de Plotly porque las `shapes` no siempre lo empujan.
    precios = [linea["precio"] for linea in lineas]
    minimo = min([float(df["Low"].min())] + precios)
    maximo = max([float(df["High"].max())] + precios)
    if es_valido(minimo) and es_valido(maximo) and maximo > minimo:
        margen = (maximo - minimo) * 0.04
        fig.update_yaxes(range=[minimo - margen, maximo + margen], row=1, col=1)

    # Margen derecho a medida de la etiqueta más larga (~5,4 px por carácter a
    # tamaño 9) para que no se corte ninguna. Acotado para no comerse el
    # gráfico si algún día las etiquetas crecen.
    return min(140, int(12 + ancho_etiqueta * 5.4))


def grafico_precio_macd(historico, tecnico: dict, ticker: str, plan: dict | None = None) -> None:
    """Velas + MM50/MM200 arriba, MACD abajo, con eje X compartido.

    Si se pasa `plan` (el dict de `core.plan_dca.construir_plan`) y está
    disponible, superpone sobre las velas los 3 niveles de entrada, los 3 de
    salida y el stop loss. El llamante decide si lo pasa o no (toggle de la
    vista); aquí no se consulta ningún estado de la interfaz.
    """
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

    # El plan se pinta al final, ya con todas las trazas puestas: así el
    # cálculo del rango del eje Y ve el gráfico completo.
    margen_derecho = 8
    if plan and plan.get("disponible"):
        # hueco para las etiquetas, que van fuera del área de dibujo
        margen_derecho = _pintar_plan_dca(fig, plan, df) or 8

    fig.update_layout(
        height=430,
        margin=dict(l=8, r=margen_derecho, t=10, b=8),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis_rangeslider_visible=False,
        legend=dict(orientation="h", y=1.12, x=0, font=dict(size=10)),
        hovermode="x unified",
    )
    fig.update_xaxes(showgrid=False, rangeslider_visible=False)
    fig.update_yaxes(gridcolor="#e2e8f0", zeroline=False)
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
