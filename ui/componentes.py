"""Componentes visuales reutilizables."""

from __future__ import annotations

import html

import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from config.settings import (
    C_AMBAR,
    C_AZUL,
    C_PRIMARIO,
    C_ROJO,
    C_TEAL,
    C_TEXTO_TENUE,
    C_VERDE,
    GRAFICO_ALTO,
    GRAFICO_BARRAS_ALTO,
    GRAFICO_PER_ALTO,
    GRAFICO_PROPORCION_FILAS,
    PLAN_COLOR_STOP,
    PLAN_COLORES_ENTRADA,
    PLAN_COLORES_SALIDA,
    TEXTO_ND,
)
from utils.formato import es_valido, fmt_fecha, fmt_num, fmt_pct


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


def mini_ficha(
    titulo: str,
    destacado: str,
    color_destacado: str,
    subtexto: str,
    filas: list[tuple[str, str]],
    aparte: str | None = None,
    etiqueta_estado: tuple[str, str] | None = None,
    pie: str | None = None,
    color_pie: str | None = None,
) -> None:
    """Tarjeta compacta de una posición, para la rejilla de Cartera y Paper
    Trading.

    Sustituye a la ficha antigua de ~430 px, que apilaba seis métricas en
    vertical y hacía inviable revisar una cartera con muchas posiciones. Aquí
    manda UN dato (el P/L, en grande y con color), acompañado de su contexto
    en una línea y de dos o tres métricas de apoyo. El detalle completo se
    abre bajo demanda, así que nada se pierde: solo deja de ocupar pantalla
    de forma permanente.

    `pie` es una línea de contexto al final de la tarjeta -- en Paper Trading,
    la distancia que le falta al precio para tocar la Entrada 1 del plan.

    Todo se pinta en un único `st.markdown` para que las filas queden dentro
    del contenedor `.ss-mini` y hereden su interlineado comprimido. El botón
    "Ver detalle" lo pone la vista, porque tiene que ser un `st.button` real.
    """
    cabecera = f'<span class="ss-mini-tk">{html.escape(titulo)}</span>'
    if aparte:
        cabecera += f'<span class="ss-mini-aparte">{html.escape(aparte)}</span>'
    estado_html = ""
    if etiqueta_estado:
        texto_estado, color_estado = etiqueta_estado
        estado_html = (
            f'<span class="ss-badge" style="background:{color_estado}">'
            f"{html.escape(texto_estado)}</span>"
        )
    cuerpo = "".join(
        f'<div class="ss-metrica"><span>{html.escape(e)}</span>'
        f"<span>{html.escape(v)}</span></div>"
        for e, v in filas
    )
    pie_html = (
        f'<div class="ss-mini-pie" style="color:{color_pie or C_TEXTO_TENUE}">'
        f"{html.escape(pie)}</div>"
        if pie
        else ""
    )
    st.markdown(
        f'<div class="ss-mini"><div class="ss-mini-cab">{cabecera}</div>'
        f"{estado_html}"
        f'<div class="ss-mini-dest" style="color:{color_destacado}">{html.escape(destacado)}</div>'
        f'<div class="ss-mini-sub">{html.escape(subtexto)}</div>{cuerpo}{pie_html}</div>',
        unsafe_allow_html=True,
    )


def racha_sorpresas(resumen: dict) -> None:
    """Tabla compacta de sorpresas de BPA de los últimos trimestres.

    Consume `core.valoracion.racha_sorpresas()`, que a su vez explota
    `earnings["historial"]` -- un dato que se descargaba en cada análisis y
    no leía ningún módulo. Un equipo directivo que guía conservador y bate
    de forma sistemática es información distinta de un batacazo aislado, y
    hasta ahora solo se veía el último trimestre suelto, sin contexto.
    """
    filas = resumen.get("trimestres") or []
    if not filas:
        st.markdown(f'<div class="ss-nd">{TEXTO_ND}</div>', unsafe_allow_html=True)
        return

    total = resumen.get("total") or 0
    if total:
        superados = resumen.get("superados") or 0
        color = C_VERDE if superados * 2 > total else (C_ROJO if superados * 2 < total else C_AMBAR)
        st.markdown(
            f'<div class="ss-racha-tit" style="color:{color}">Superó estimaciones en '
            f"{superados} de los últimos {total} trimestres</div>",
            unsafe_allow_html=True,
        )

    celdas = ['<div class="ss-racha">']
    celdas.append(
        '<div class="ss-racha-fila ss-racha-cab"><span>Periodo</span>'
        "<span>Real</span><span>Est.</span><span>Sorpresa</span></div>"
    )
    for f in filas:
        s = f.get("sorpresa_pct")
        if not es_valido(s):
            color, texto = C_TEXTO_TENUE, TEXTO_ND
        else:
            color = C_VERDE if float(s) > 0.5 else (C_ROJO if float(s) < -0.5 else C_TEXTO_TENUE)
            texto = fmt_pct(s)
        celdas.append(
            '<div class="ss-racha-fila">'
            f"<span>{html.escape(fmt_fecha(f.get('periodo')))}</span>"
            f"<span>{html.escape(fmt_num(f.get('real')))}</span>"
            f"<span>{html.escape(fmt_num(f.get('estimado')))}</span>"
            f'<span style="color:{color};font-weight:600">{html.escape(texto)}</span></div>'
        )
    celdas.append("</div>")
    st.markdown("".join(celdas), unsafe_allow_html=True)


def _barras_horizontales(
    etiquetas: list[str],
    valores: list,
    titulo: str,
    formateador,
    alto: int = GRAFICO_BARRAS_ALTO,
    colores: list[str] | None = None,
) -> None:
    """Barras horizontales sin ejes: la etiqueta y el valor van sobre la barra.

    Pensado para una columna estrecha. Se dibuja con el eje Y invertido
    porque Plotly apila de abajo a arriba y las etiquetas llegan en el orden
    en que deben leerse (de arriba abajo).

    `colores` permite dar un color por barra cuando cada una significa algo
    distinto (la comparativa de PER); si se omite, se colorea por signo.
    """
    validos = [v for v in valores if es_valido(v)]
    if not validos:
        st.markdown(
            f'<div class="ss-mini-tit">{html.escape(titulo)}</div>'
            f'<div class="ss-nd">{TEXTO_ND}</div>',
            unsafe_allow_html=True,
        )
        return

    if colores is None:
        colores = [C_ROJO if es_valido(v) and float(v) < 0 else C_AZUL for v in valores]
    fig = go.Figure(
        go.Bar(
            x=[float(v) if es_valido(v) else 0 for v in valores],
            y=list(etiquetas),
            orientation="h",
            marker_color=colores,
            text=[formateador(v) if es_valido(v) else TEXTO_ND for v in valores],
            textposition="auto",
            insidetextanchor="start",
            hoverinfo="skip",
        )
    )
    # Rango simétrico alrededor del cero cuando hay negativos: así el eje
    # cero queda donde debe y una barra negativa no se dibuja como positiva.
    minimo, maximo = min(validos), max(validos)
    holgura = (maximo - minimo) * 0.18 or abs(maximo) * 0.18 or 1
    fig.update_layout(
        height=alto,
        margin=dict(l=4, r=4, t=20, b=4),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
        bargap=0.28,
        title=dict(text=titulo, font=dict(size=12), x=0, xanchor="left", y=0.99),
        font=dict(size=10),
        uniformtext=dict(minsize=8, mode="hide"),
    )
    fig.update_xaxes(visible=False, range=[min(0, minimo) - holgura, max(0, maximo) + holgura])
    fig.update_yaxes(autorange="reversed", showgrid=False, ticksuffix="  ")
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


def comparativa_per(pers: dict, mensaje: str | None = None) -> None:
    """PER actual frente a forward, histórico propio y mediana del sector.

    Los cuatro números ya existían por separado (dos en `info`, uno en
    `calcular_per_historico()`, otro en la tabla sectorial de `settings`);
    juntos responden de un vistazo a "¿está cara?" con las tres referencias
    que importan: su propio futuro, su propia historia y sus comparables.

    El PER actual va en color de acento y las tres referencias en tono
    neutro: la pregunta es dónde cae el actual respecto a las otras tres,
    no comparar las tres entre sí.
    """
    etiquetas, valores, colores = [], [], []
    for clave, etiqueta, color in (
        ("actual", "PER actual", C_PRIMARIO),
        ("forward", "PER forward", C_TEAL),
        ("historico", "PER medio propio 5a", C_AZUL),
        ("sector", "PER medio del sector", C_TEXTO_TENUE),
    ):
        etiquetas.append(etiqueta)
        valores.append(pers.get(clave))
        colores.append(color)

    _barras_horizontales(
        etiquetas,
        valores,
        "Comparativa de PER",
        lambda v: fmt_num(v, 1, "x"),
        alto=GRAFICO_PER_ALTO,
        colores=colores,
    )
    if mensaje:
        st.markdown(
            f'<div class="ss-per-mensaje">{html.escape(mensaje)}</div>',
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
# El NIVEL ya no se codifica bajando la opacidad (que a 1,3 px dejaba el nivel
# 3 casi invisible) sino con el tono dentro de su familia de color: entradas
# en azul de oscuro a claro, salidas en verde de oscuro a claro (ver
# PLAN_COLORES_* en config/settings.py). Todas las líneas se pintan sólidas.
_PLAN_OPACIDAD = 0.9


def _color_nivel(tipo: str, indice: int) -> str:
    """Color de un nivel según su tipo y su orden (0 = nivel 1)."""
    if tipo == "stop":
        return PLAN_COLOR_STOP
    paleta = PLAN_COLORES_ENTRADA if tipo == "entrada" else PLAN_COLORES_SALIDA
    return paleta[min(max(indice, 0), len(paleta) - 1)]


def _texto_sobre(fondo: str) -> str:
    """Blanco o casi negro, el que contraste con `fondo`.

    Los niveles 3 son tonos claros (#93c5fd, #6ee7b7): con texto blanco la
    pastilla queda ilegible. En vez de fijar el color a mano por nivel se
    calcula la luminancia relativa, así la regla sigue valiendo si algún día
    se cambia la paleta.
    """
    try:
        r, g, b = (int(fondo[i : i + 2], 16) / 255 for i in (1, 3, 5))
    except (ValueError, IndexError):
        return "#ffffff"
    luminancia = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return "#0f172a" if luminancia > 0.6 else "#ffffff"


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
                "color": _color_nivel("entrada", indice),
                "opacidad": _PLAN_OPACIDAD,
                "trazo": "dash",
                "grosor": 2.0,
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
                "color": _color_nivel("salida", indice),
                "opacidad": _PLAN_OPACIDAD,
                "trazo": "dot",
                "grosor": 2.0,
            }
        )

    sl = plan.get("stop_loss") or {}
    if es_valido(sl.get("precio")):
        lineas.append(
            {
                "precio": float(sl["precio"]),
                "etiqueta": "SL",
                "distancia_pct": sl.get("distancia_pct"),
                "color": PLAN_COLOR_STOP,
                "opacidad": 0.95,
                "trazo": "dashdot",
                "grosor": 2.4,
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
        texto = f"<b>{linea['etiqueta']}</b> {fmt_num(linea['precio'])}"
        if distancia != TEXTO_ND:
            texto += f" · {distancia}"
        # El ancho se mide sobre el texto SIN las etiquetas HTML: `<b></b>` no
        # ocupa píxeles en el render, y contarlo inflaría el margen derecho.
        ancho_etiqueta = max(ancho_etiqueta, len(texto) - 7)
        fig.add_annotation(
            xref="x domain",
            x=1.006,
            xanchor="left",
            yref="y",
            y=linea["precio"],
            yanchor="middle",
            text=texto,
            showarrow=False,
            align="left",
            # Pastilla sólida con el texto en blanco en vez de texto suelto de
            # 9 px: se lee sobre cualquier fondo y no compite con las velas.
            font=dict(size=11, color=_texto_sobre(linea["color"])),
            bgcolor=linea["color"],
            borderpad=4,
            borderwidth=0,
            opacity=1,
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

    # Margen derecho a medida de la etiqueta más larga (~6,4 px por carácter a
    # tamaño 11, más el relleno de la pastilla) para que no se corte ninguna.
    # Acotado para no comerse el gráfico si algún día las etiquetas crecen.
    return min(175, int(18 + ancho_etiqueta * 6.4))


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
        row_heights=list(GRAFICO_PROPORCION_FILAS),
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
        height=GRAFICO_ALTO,
        # Margen izquierdo holgado: con el gráfico más alto el eje Y muestra
        # más marcas y con l=8 las cifras de 4 dígitos se cortaban.
        margin=dict(l=46, r=margen_derecho, t=22, b=16),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis_rangeslider_visible=False,
        legend=dict(orientation="h", y=1.06, x=0, font=dict(size=11)),
        font=dict(size=11),
        hovermode="x unified",
    )
    fig.update_xaxes(showgrid=False, rangeslider_visible=False)
    fig.update_yaxes(gridcolor="#e2e8f0", zeroline=False)
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
