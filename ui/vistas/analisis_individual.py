"""Apartado "Análisis Individual": los 6 bloques descritos en el wireframe."""

from __future__ import annotations

import html

import streamlit as st

from config.settings import (
    C_PRIMARIO,
    C_ROJO,
    C_TEXTO_TENUE,
    C_VERDE,
    CARTERA_DIVISAS_CONVERTIBLES,
    CONSENSO_ANALISTAS_ES,
    CONSENSO_MIN_ANALISTAS,
    CURRENT_RATIO_MEDIANO_SECTOR,
    C_AMBAR,
    C_VERDE_OSCURO,
    DEBT_EQUITY_MEDIANO_SECTOR,
    EV_EBITDA_MEDIANO_SECTOR,
    FORWARD_PER_MEDIANO_SECTOR,
    MARGEN_EBITDA_MEDIANO_SECTOR,
    MARGEN_BRUTO_MEDIANO_SECTOR,
    MARGEN_NETO_MEDIANO_SECTOR,
    MARGEN_OPERATIVO_MEDIANO_SECTOR,
    PAPER_ESTADOS,
    PB_MEDIANO_SECTOR,
    PEG_MEDIANO_SECTOR,
    PER_MEDIANO_SECTOR,
    PESOS_CALIDAD,
    PESOS_TIMING,
    PS_MEDIANO_SECTOR,
    ROA_MEDIANO_SECTOR,
    ROE_MEDIANO_SECTOR,
    ROIC_MEDIANO_SECTOR,
    TEXTO_ND,
    TRIMESTRES_EVOLUCION,
)
from core import alertas_telegram, bd_supabase, datos_api, indicadores, plan_dca, timing, traduccion, valoracion
from ui import componentes as C
from utils.formato import (
    dias_hasta,
    es_valido,
    fmt_compacto,
    fmt_compacto_usd_eur,
    fmt_fecha,
    fmt_num,
    fmt_pct,
    fmt_usd_eur,
    primero_valido,
)


def _precio_fmt(valor, p: dict) -> str:
    """Precio en la moneda del valor. Si es USD, incluye su conversión a EUR
    entre paréntesis (regla del proyecto: todo importe en $ debe mostrar su €).
    """
    if not es_valido(valor):
        return TEXTO_ND
    moneda = p.get("moneda") or ""
    if moneda == "USD":
        return fmt_usd_eur(valor, p.get("fx_usd_eur"))
    return f"{fmt_num(valor)} {moneda}".strip()


# ------------------------------------------------------------ orquestación --
def ejecutar_analisis(ticker: str, incluir_noticias: bool = True) -> dict:
    """Encadena datos -> técnico -> valoración -> calidad -> timing -> plan.

    `incluir_noticias=False` se usa desde el Rastreador: las noticias no
    alimentan ningún cálculo (Calidad, Valoración, Timing), así que pedirlas
    en un escaneo por lote solo tira peticiones a la basura.
    """
    paquete = datos_api.obtener_paquete(ticker, incluir_noticias=incluir_noticias)
    if not paquete["existe"]:
        return {"error": f"No se han encontrado datos para el ticker «{ticker}»."}

    referencia = datos_api.obtener_referencia_mercado(paquete.get("sector"))
    tecnico = indicadores.calcular_todo(paquete["historico"], referencia)
    fair_value = valoracion.calcular_fair_value(paquete)
    calidad = valoracion.puntuar_calidad(paquete, fair_value)
    momento = timing.calcular_timing(paquete, tecnico, fair_value, calidad)

    # Zonas en bruto para los desplegables del override manual, y el propio
    # override guardado: SOLO en Análisis Individual (incluir_noticias=True).
    # El Rastreador reutiliza esta función para docenas de tickers por
    # escaneo y no usa el override — pedirlo igualmente añadiría una consulta
    # a Supabase por ticker sin ningún consumidor al otro lado.
    if incluir_noticias:
        zonas_entrada = plan_dca.zonas_confluencia_soporte(tecnico.get("precio"), tecnico)
        zonas_salida = plan_dca.zonas_confluencia_resistencia(
            tecnico.get("precio"), tecnico, fair_value.get("fair_value")
        )
        override = bd_supabase.obtener_override_dca(ticker) if bd_supabase.hay_conexion() else {}
    else:
        zonas_entrada, zonas_salida, override = [], [], {}

    plan = plan_dca.construir_plan(paquete, tecnico, fair_value, override=override or None)
    veredicto = plan_dca.veredicto_final(calidad, fair_value, momento, plan)

    return {
        "paquete": paquete,
        "tecnico": tecnico,
        "valoracion": fair_value,
        "calidad": calidad,
        "timing": momento,
        "plan": plan,
        "veredicto": veredicto,
        "zonas_disponibles": {"entradas": zonas_entrada, "salidas": zonas_salida},
        "override_activo": override,
    }


def _guardar_en_historico(a: dict) -> None:
    if not bd_supabase.hay_conexion():
        return
    bd_supabase.guardar_analisis(
        a["paquete"]["ticker"],
        {
            "precio": a["paquete"].get("precio"),
            "fair_value": a["valoracion"].get("fair_value"),
            "upside_pct": a["valoracion"].get("upside_pct"),
            "puntuacion_calidad": a["calidad"].get("puntuacion"),
            "puntuacion_timing": a["timing"].get("puntuacion"),
            "senal_timing": a["timing"].get("senal"),
            "veredicto": a["veredicto"].get("etiqueta"),
            "payload": {
                "alerta": a["valoracion"].get("alerta", {}).get("etiqueta"),
                "excluidos_valoracion": a["valoracion"].get("excluidos"),
                "excluidos_calidad": a["calidad"].get("excluidos"),
            },
        },
    )


# ------------------------------------------------------------------ render --
def render() -> None:
    # --- barra de búsqueda -------------------------------------------------
    col_input, col_boton = st.columns([5, 1])
    with col_input:
        ticker = st.text_input(
            "Ticker",
            key="entrada_ticker",
            placeholder="Introduce el ticker (por ejemplo, AAPL)",
            label_visibility="collapsed",
        )
    with col_boton:
        analizar = st.button("Analizar", type="primary", use_container_width=True)

    if analizar and ticker.strip():
        # Instrumentación: mide solo ESTE análisis, no lo acumulado de la
        # sesión. El resumen se vuelca a los logs de la app (visibles en
        # "Manage app" de Streamlit Community Cloud), nunca a la interfaz.
        # Es lo que permite distinguir un fallo de fundamentales por límite
        # de Yahoo de uno por ticker inexistente, y ver cuánto está
        # aportando cada capa de caché tras un redespliegue.
        datos_api.reset_metricas()
        with st.spinner("Recopilando datos y calculando…"):
            st.session_state["analisis"] = ejecutar_analisis(ticker)
        datos_api.log_resumen_metricas(f"Análisis individual · {ticker.strip().upper()}")
        if "error" not in st.session_state["analisis"]:
            _guardar_en_historico(st.session_state["analisis"])

    analisis = st.session_state.get("analisis")
    if not analisis:
        st.info("Introduce un ticker y pulsa **Analizar** para generar el informe completo.")
        return
    if "error" in analisis:
        st.error(analisis["error"])
        return

    _bloque_1_cabecera(analisis)

    izquierda, derecha = st.columns([1, 2], gap="medium")
    with izquierda:
        with st.container(border=True):
            _bloque_2_descripcion(analisis)
    with derecha:
        with st.container(border=True):
            _bloque_3_grafico(analisis)

    c1, c2, c3 = st.columns(3, gap="medium")
    with c1:
        with st.container(border=True):
            _bloque_4_calidad(analisis)
    with c2:
        with st.container(border=True):
            _bloque_5_timing(analisis)
    with c3:
        with st.container(border=True):
            _bloque_6_plan(analisis)


# ============================================================== Bloque 1 ======
def _bloque_1_cabecera(a: dict) -> None:
    p = a["paquete"]

    col_id, col_precio, col_fav = st.columns([3, 2, 1.4])

    with col_id:
        st.markdown('<div class="ss-etiqueta">Ticker analizado</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="ss-ticker">{html.escape(p["ticker"])}</div>', unsafe_allow_html=True)
        st.markdown(
            f'<div class="ss-empresa">{html.escape(p.get("nombre") or TEXTO_ND)}</div>'
            f'<div class="ss-sector">{html.escape(p.get("sector") or TEXTO_ND)}'
            f'{" · " + html.escape(p["industria"]) if p.get("industria") else ""}</div>',
            unsafe_allow_html=True,
        )

    with col_precio:
        st.markdown(
            '<div class="ss-etiqueta">Precio actual de cotización</div>', unsafe_allow_html=True
        )
        precio = p.get("precio")
        if es_valido(precio):
            st.markdown(
                f'<div class="ss-precio">{html.escape(_precio_fmt(precio, p))}</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(f'<div class="ss-nd">{TEXTO_ND}</div>', unsafe_allow_html=True)

    with col_fav:
        st.write("")
        if bd_supabase.hay_conexion():
            favorito = bd_supabase.es_favorito(p["ticker"])
            key = "btn_favorito_on" if favorito else "btn_favorito_off"
            if C.boton_favorito(favorito, key=key):
                bd_supabase.alternar_favorito(p["ticker"], p.get("nombre"), p.get("sector"))
                st.rerun()
        else:
            st.button(
                "☆",
                disabled=True,
                help="Configura SUPABASE_URL y SUPABASE_KEY en los secrets para usar Favoritos.",
            )


# ============================================================== Bloque 2 ======
def _bloque_2_descripcion(a: dict) -> None:
    p = a["paquete"]
    fx = p.get("fx_usd_eur")
    C.titulo_bloque("Descripción, noticias y últimos resultados")

    descripcion = p.get("descripcion")
    if descripcion:
        recorte_previo = descripcion[:600]  # margen sobre los 520 mostrados; ahorra tokens de traducción
        texto, es_traduccion = traduccion.traducir_descripcion(p["ticker"], recorte_previo)
        texto = texto or recorte_previo
        st.caption(texto[:520] + ("…" if len(texto) > 520 or len(descripcion) > 600 else ""))
        if not es_traduccion:
            st.caption("Descripción en inglés (traducción no disponible).")
    else:
        st.markdown(f'<div class="ss-nd">{TEXTO_ND}</div>', unsafe_allow_html=True)
        _diagnostico_info(p)

    st.markdown("**Últimas noticias**")
    C.lista_noticias(p.get("noticias", []))

    st.markdown("**Últimos resultados presentados**")
    e = p.get("earnings", {})
    ultimo = e.get("ultimo")
    if not ultimo:
        st.markdown(f'<div class="ss-nd">{TEXTO_ND}</div>', unsafe_allow_html=True)
    else:
        C.metrica("Periodo", fmt_fecha(ultimo.get("fecha") or ultimo.get("periodo")))
        C.metrica("BPA publicado", fmt_num(ultimo.get("eps_real")))
        C.metrica("BPA estimado", fmt_num(ultimo.get("eps_estimado")))
        _linea_sorpresa("BPA", ultimo.get("eps_real"), ultimo.get("eps_estimado"))
        C.metrica("Ingresos publicados", fmt_compacto_usd_eur(ultimo.get("ingresos_real"), fx))
        C.metrica("Ingresos estimados", fmt_compacto_usd_eur(ultimo.get("ingresos_estimado"), fx))
        _linea_sorpresa("Ingresos", ultimo.get("ingresos_real"), ultimo.get("ingresos_estimado"))

    proxima = e.get("proxima_fecha")
    dias = dias_hasta(proxima)
    texto = fmt_fecha(proxima) if proxima else TEXTO_ND
    if dias is not None and dias >= 0:
        texto += f"  (en {dias} días)"
    C.metrica("Próxima presentación de resultados", texto)

    st.markdown("**Racha de sorpresas de resultados**")
    C.racha_sorpresas(valoracion.racha_sorpresas(p.get("earnings", {}).get("historial") or []))

    st.markdown(f"**Evolución de los últimos {TRIMESTRES_EVOLUCION} trimestres**")
    C.evolucion_trimestral(valoracion.series_trimestrales(p), p.get("moneda"))


def _linea_sorpresa(concepto: str, real, estimado) -> None:
    etiqueta = f"¿{concepto} superó estimaciones?"
    if not es_valido(real) or not es_valido(estimado) or estimado == 0:
        C.metrica(etiqueta, TEXTO_ND)
        return
    desviacion = (real - estimado) / abs(estimado) * 100
    if abs(desviacion) < 0.5:
        C.metrica_color(etiqueta, f"En línea ({fmt_pct(desviacion)})", C_TEXTO_TENUE)
    elif desviacion > 0:
        C.metrica_color(etiqueta, f"Superó ({fmt_pct(desviacion)})", C_VERDE)
    else:
        C.metrica_color(etiqueta, f"No superó ({fmt_pct(desviacion)})", C_ROJO)


def _diagnostico_info(p: dict) -> None:
    """Muestra la causa real cuando yfinance no ha podido servir los fundamentales.

    Solo aparece cuando `datos_api.obtener_info` ha dejado constancia del
    error en la clave interna `_ss_error`; así se distingue "Yahoo no tiene
    ese dato para este ticker" (fila con TEXTO_ND) de "la petición ha
    fallado" (aquí se ve el motivo exacto para poder corregirlo).
    """
    errores = (p.get("info") or {}).get("_ss_error")
    if not errores:
        return
    with st.expander("⚠️ Los fundamentales no se han podido cargar — ver motivo"):
        for e in errores:
            st.code(e, language=None)
        st.caption(
            "Esto es un fallo de conexión con la fuente de datos, no una ausencia real del "
            "dato. Compártelo tal cual para poder corregirlo."
        )


# ============================================================== Bloque 3 ======
def _bloque_3_grafico(a: dict) -> None:
    p, t = a["paquete"], a["tecnico"]
    fx = p.get("fx_usd_eur")
    info = p.get("info", {})
    sector = p.get("sector")
    precio = p.get("precio")
    C.titulo_bloque("Cotización · MACD y datos fundamentales y técnicos")

    plan_en_grafico = _toggle_plan_dca(a)
    C.grafico_precio_macd(p.get("historico"), t, p["ticker"], plan=plan_en_grafico)
    _diagnostico_info(p)

    col_f, col_t = st.columns(2)
    with col_f:
        st.markdown("**Fundamentales**")
        C.metrica("Capitalización", fmt_compacto_usd_eur(info.get("marketCap"), fx))
        C.metrica("Nº de acciones en circulación", fmt_compacto(info.get("sharesOutstanding")))
        _bloque_valoracion(info, sector)
        _bloque_rentabilidad(info, a["calidad"]["lecturas"], sector)
        _bloque_balance_caja(info, fx, sector)
    with col_t:
        st.markdown("**Técnicos**")
        C.metrica_nota("RSI (14)", fmt_num(t.get("rsi"), 1), _nivel_rsi(t.get("rsi")))
        C.metrica("MACD", fmt_num(t.get("macd"), 3))
        C.metrica("Señal MACD", fmt_num(t.get("macd_senal"), 3))
        C.metrica("ADX (14)", fmt_num(t.get("adx"), 1))
        C.metrica("ATR (14)", fmt_num(t.get("atr"), 2))
        _fila_distancia("Media móvil 50", t.get("mm50"), precio, fx)
        _fila_distancia("Media móvil 200", t.get("mm200"), precio, fx)
        _fila_distancia("Máximo 52 semanas", t.get("max_52s"), precio, fx)
        _fila_distancia("Mínimo 52 semanas", t.get("min_52s"), precio, fx)
        C.metrica("Variación 1 año", fmt_pct(t.get("variacion_1a_pct")))
        C.metrica("Volumen medio 3 meses", fmt_compacto(t.get("volumen_medio_3m")))
        _filas_riesgo_mercado(info)

    if es_valido(fx):
        st.markdown(
            f'<div class="ss-anotacion">Tipo de cambio aplicado: 1 USD = '
            f'{fmt_num(fx, 4)} EUR (yfinance, tiempo real).</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f'<div class="ss-anotacion">Conversión a euros: {TEXTO_ND}.</div>', unsafe_allow_html=True
        )


def _filas_riesgo_mercado(info: dict) -> None:
    """Short interest, short ratio y beta: tres datos ya descargados en
    `info` de yfinance que no se mostraban en ninguna parte de la app.

    Short interest y short ratio son relevantes para un plan DCA: un valor
    con una parte grande del flotante en corto apoyándose en un soporte se
    comporta distinto de uno sin presión bajista, tanto al caer (la presión
    vendedora puede acelerar la caída) como al rebotar (recompras forzadas
    de las posiciones cortas amplifican el rebote). La beta sitúa el valor
    frente al mercado: cuánto se mueve por cada punto que se mueve el S&P.

    El nivel se anota junto al dato en vez de colorearlo: ninguno de los
    tres es "malo" ni "bueno" por sí solo -- depende del contexto -- y
    pintarlo de rojo/verde sugeriría un juicio que el dato no soporta.
    """
    corto_pct = primero_valido(info.get("shortPercentOfFloat"))
    if es_valido(corto_pct):
        # yfinance lo da en tanto por uno (0,1186 = 11,86 % del flotante).
        pct = float(corto_pct) * 100
        C.metrica_nota("Short interest (% flotante)", fmt_num(pct, 2, " %"), _nivel_corto(pct))
    else:
        C.metrica("Short interest (% flotante)", TEXTO_ND)

    ratio = primero_valido(info.get("shortRatio"))
    if es_valido(ratio):
        C.metrica_nota(
            "Short ratio (días para cubrir)",
            fmt_num(ratio, 2),
            _nivel_short_ratio(float(ratio)),
        )
    else:
        C.metrica("Short ratio (días para cubrir)", TEXTO_ND)

    beta = primero_valido(info.get("beta"))
    if es_valido(beta):
        C.metrica_nota("Beta (β)", fmt_num(float(beta), 2), _nivel_beta(float(beta)))
    else:
        C.metrica("Beta (β)", TEXTO_ND)


def _nivel_corto(pct: float) -> str:
    """Zona del % del flotante en corto. Cortes habituales del mercado."""
    if pct < 2:
        return "Muy bajo"
    if pct < 5:
        return "Bajo"
    if pct < 10:
        return "Moderado"
    if pct < 20:
        return "Alto"
    return "Muy alto"


def _nivel_short_ratio(ratio: float) -> str:
    """Días de volumen medio que harían falta para cerrar todos los cortos.

    Por encima de ~5 días el mercado empieza a considerar que hay riesgo de
    short squeeze: cerrar las posiciones exige más volumen del que el valor
    negocia en una semana.
    """
    if ratio < 1:
        return "Muy bajo"
    if ratio < 3:
        return "Bajo"
    if ratio < 5:
        return "Moderado"
    if ratio < 8:
        return "Alto"
    return "Muy alto"


def _nivel_beta(beta: float) -> str:
    """Sensibilidad frente al mercado: beta 1 = se mueve como el índice."""
    if beta < 0:
        return "Inversa al mercado"
    if beta < 0.8:
        return "Defensiva"
    if beta < 1.2:
        return "En línea con el mercado"
    if beta < 1.6:
        return "Agresiva"
    return "Muy agresiva"


def _toggle_plan_dca(a: dict) -> dict | None:
    """Interruptor para superponer el plan DCA sobre las velas.

    Devuelve el plan si el interruptor está activo (y el plan existe), o None
    para que el gráfico se dibuje limpio. La `key` incluye el ticker para que
    el estado no se arrastre de un valor a otro al analizar uno nuevo.
    """
    plan = a.get("plan") or {}
    ticker = a["paquete"]["ticker"]
    disponible = bool(plan.get("disponible"))

    activo = st.toggle(
        "Mostrar Plan DCA",
        key=f"plan_en_grafico_{ticker}",
        value=False,
        disabled=not disponible,
    )
    # Sin tooltip: el motivo de que el plan no esté disponible es información
    # que hay que ver, no que descubrir pasando el ratón por encima de un
    # control desactivado.
    if not disponible:
        st.caption(f"Plan no disponible: {plan.get('motivo', 'sin datos suficientes')}.")
    return plan if (activo and disponible) else None


def _fila_distancia(etiqueta: str, valor, precio, fx=None) -> None:
    """Métrica técnica junto a su distancia en % respecto al precio actual.
    Solo la distancia lleva color (verde si es positiva, rojo si es negativa);
    el valor de la media/máximo/mínimo se muestra en el estilo normal, en
    USD con su conversión a EUR entre paréntesis (regla del proyecto para
    todo importe monetario)."""
    if not es_valido(valor):
        C.metrica(etiqueta, TEXTO_ND)
        return
    texto = fmt_usd_eur(valor, fx)
    if es_valido(precio) and float(valor) != 0:
        distancia = (float(precio) / float(valor) - 1) * 100
        color = C_VERDE if distancia >= 0 else C_ROJO
        C.metrica_distancia(etiqueta, texto, fmt_pct(distancia), color)
    else:
        C.metrica(etiqueta, texto)


def _nivel_rsi(valor) -> str | None:
    """Clasifica el RSI en su zona de sobrecompra/sobreventa."""
    if not es_valido(valor):
        return None
    v = float(valor)
    if v <= 20:
        return "Extrema Sobreventa"
    if v <= 30:
        return "Sobreventa"
    if v <= 45:
        return "Zona Neutral-Bajista"
    if v <= 55:
        return "Zona Neutral"
    if v <= 69:
        return "Zona Neutral-Alcista"
    if v <= 80:
        return "Sobrecompra"
    return "Extrema Sobrecompra"


def _destaca_sector(valor, referencia, menor_es_mejor: bool) -> bool:
    """True si el valor supera la media de su sector con un margen relevante
    (>3 %). Sin dato propio o de referencia, no se resalta (nunca en verde
    por defecto)."""
    if not es_valido(valor) or not es_valido(referencia) or referencia == 0:
        return False
    ratio = float(valor) / float(referencia)
    return ratio < 0.97 if menor_es_mejor else ratio > 1.03


def _bloque_valoracion(info: dict, sector: str | None) -> None:
    st.markdown("**Valoración**")
    filas = [
        ("PER (trailing)", primero_valido(info.get("trailingPE")), PER_MEDIANO_SECTOR.get(sector), False),
        ("PER Forward", primero_valido(info.get("forwardPE")), FORWARD_PER_MEDIANO_SECTOR.get(sector), True),
        (
            "PEG",
            primero_valido(info.get("trailingPegRatio"), info.get("pegRatio")),
            PEG_MEDIANO_SECTOR.get(sector),
            True,
        ),
        ("Precio / Ventas", primero_valido(info.get("priceToSalesTrailing12Months")), PS_MEDIANO_SECTOR.get(sector), False),
        ("Precio / Valor contable", primero_valido(info.get("priceToBook")), PB_MEDIANO_SECTOR.get(sector), False),
        ("EV/EBITDA", primero_valido(info.get("enterpriseToEbitda")), EV_EBITDA_MEDIANO_SECTOR.get(sector), True),
    ]
    for etiqueta, valor, referencia, mostrar_media in filas:
        destaca = _destaca_sector(valor, referencia, menor_es_mejor=True)
        media = fmt_num(referencia) if mostrar_media and es_valido(referencia) else None
        C.metrica_fundamental(etiqueta, fmt_num(valor) if es_valido(valor) else TEXTO_ND, destaca, media)


def _bloque_rentabilidad(info: dict, lecturas: dict, sector: str | None) -> None:
    st.markdown("**Rentabilidad**")
    filas = [
        ("Margen Neto", primero_valido(info.get("profitMargins")), MARGEN_NETO_MEDIANO_SECTOR.get(sector), True),
        ("Margen Operativo", primero_valido(info.get("operatingMargins")), MARGEN_OPERATIVO_MEDIANO_SECTOR.get(sector), True),
        ("Margen EBITDA", primero_valido(info.get("ebitdaMargins")), MARGEN_EBITDA_MEDIANO_SECTOR.get(sector), False),
        ("ROE", primero_valido(info.get("returnOnEquity")), ROE_MEDIANO_SECTOR.get(sector), True),
        ("ROIC", lecturas.get("roic"), ROIC_MEDIANO_SECTOR.get(sector), False),
        ("ROA", primero_valido(info.get("returnOnAssets")), ROA_MEDIANO_SECTOR.get(sector), False),
    ]
    for etiqueta, valor, referencia, mostrar_media in filas:
        destaca = _destaca_sector(valor, referencia, menor_es_mejor=False)
        media = fmt_pct(referencia, 1, ya_en_pct=False) if mostrar_media and es_valido(referencia) else None
        texto = fmt_pct(valor, 1, ya_en_pct=False) if es_valido(valor) else TEXTO_ND
        C.metrica_fundamental(etiqueta, texto, destaca, media)


def _bloque_balance_caja(info: dict, fx, sector: str | None) -> None:
    st.markdown("**Balance y Caja**")
    C.metrica("Caja Total", fmt_compacto_usd_eur(info.get("totalCash"), fx))
    C.metrica("Deuda Total", fmt_compacto_usd_eur(info.get("totalDebt"), fx))

    dte = primero_valido(info.get("debtToEquity"))
    C.metrica_fundamental(
        "Ratio Deuda/Equity",
        fmt_num(dte) if es_valido(dte) else TEXTO_ND,
        _destaca_sector(dte, DEBT_EQUITY_MEDIANO_SECTOR.get(sector), menor_es_mejor=True),
    )
    cr = primero_valido(info.get("currentRatio"))
    C.metrica_fundamental(
        "Current Ratio",
        fmt_num(cr) if es_valido(cr) else TEXTO_ND,
        _destaca_sector(cr, CURRENT_RATIO_MEDIANO_SECTOR.get(sector), menor_es_mejor=False),
    )
    C.metrica("Operating Cash Flow", fmt_compacto_usd_eur(info.get("operatingCashflow"), fx))
    C.metrica("Free Cash Flow", fmt_compacto_usd_eur(info.get("freeCashflow"), fx))


# ============================================================== Bloque 4 ======
def _bloque_4_calidad(a: dict) -> None:
    v, q, p = a["valoracion"], a["calidad"], a["paquete"]
    C.titulo_bloque("Salud / Calidad fundamental y Valor objetivo")

    st.markdown("**Puntuación de calidad**")
    C.nota(q.get("puntuacion"), C_PRIMARIO)

    st.markdown("**Valor objetivo justo**")
    fv = v.get("fair_value")
    st.markdown(
        f'<div class="ss-precio">{html.escape(_precio_fmt(fv, p))}</div>'
        if es_valido(fv)
        else f'<div class="ss-nd">{TEXTO_ND}</div>',
        unsafe_allow_html=True,
    )
    alerta = v.get("alerta", {})
    C.alerta(alerta.get("etiqueta", TEXTO_ND), alerta.get("color", "#94a3b8"))
    C.metrica("Precio actual de cotización", _precio_fmt(p.get("precio"), p))
    C.metrica("Potencial (upside)", fmt_pct(v.get("upside_pct")))
    if v.get("peso_consenso_doble"):
        n = p.get("consenso", {}).get("n_analistas")
        cobertura = f" ({n:.0f})" if es_valido(n) else ""
        st.caption(
            f"Peso doble aplicado al consenso: cobertura ≥ {CONSENSO_MIN_ANALISTAS} "
            f"analistas{cobertura}."
        )

    with st.expander("Desglose de la valoración"):
        for nombre, comp in v["componentes"].items():
            valor = comp["valor"]
            peso = v["pesos_aplicados"].get(_clave_peso(nombre))
            sufijo = f"  ·  peso {peso * 100:.0f} %" if peso else "  ·  excluido del cálculo"
            C.metrica(nombre, _precio_fmt(valor, p) + sufijo)
            for n in comp["detalle"].get("notas", []):
                st.caption(f"↳ {n}")
        C.metrica("Cobertura del modelo", fmt_pct(v.get("cobertura", 0) * 100, 0))

    with st.expander("Métricas de calidad"):
        L = q["lecturas"]
        sub = q["subpuntuaciones"]
        sector = p.get("sector")
        ref_margen = MARGEN_NETO_MEDIANO_SECTOR.get(sector)
        ref_bruto = MARGEN_BRUTO_MEDIANO_SECTOR.get(sector)
        ref_roe = ROE_MEDIANO_SECTOR.get(sector)

        def _linea(clave: str, etiqueta: str) -> None:
            """Fila 'texto de la métrica: +X,X/máx' coloreada por calidad.

            El color sale de la sub-puntuación 0-100 de la propia métrica:
            verde >=70, ámbar >=40, rojo por debajo. Las métricas sin dato se
            muestran en gris y no penalizan (su peso se redistribuye).
            """
            peso_max = PESOS_CALIDAD.get(clave, 0)
            valor_sub = sub.get(clave)
            if not es_valido(valor_sub) or not peso_max:
                C.metrica_color(f"{etiqueta}: sin dato", "excluido", C_TEXTO_TENUE)
                return
            puntos = valor_sub / 100 * peso_max
            color = C_VERDE_OSCURO if valor_sub >= 70 else (C_AMBAR if valor_sub >= 40 else C_ROJO)
            C.metrica_color(etiqueta, f"+{puntos:.1f}/{peso_max:.0f}", color)

        def _pct(valor, decimales: int = 1) -> str:
            return f"{valor * 100:.{decimales}f} %" if es_valido(valor) else TEXTO_ND

        # --- I. Crecimiento y Eficiencia -------------------------------------
        bl = q["bloques"]["I. Crecimiento y Eficiencia"]
        st.markdown(f"**I. Crecimiento y Eficiencia — {bl['obtenidos']:.1f}/{bl['maximo']:.0f}**")
        _linea(
            "tendencia_ingresos",
            f"Crec. ingresos {_pct(L.get('cagr_ingresos'))} × estabilidad "
            f"×{L.get('estabilidad_ingresos', 1.0):.2f}",
        )
        _linea(
            "tendencia_beneficios",
            f"Crec. beneficios {_pct(L.get('cagr_beneficios'))} × estabilidad "
            f"×{L.get('estabilidad_beneficios', 1.0):.2f}",
        )
        rot, rot_prev = L.get("rotacion_activos"), L.get("rotacion_activos_prev")
        _linea(
            "rotacion_activos",
            f"Rotación de activos {rot:.2f}× (año anterior {rot_prev:.2f}×)"
            if es_valido(rot) and es_valido(rot_prev)
            else "Rotación de activos",
        )

        # --- II. Rentabilidad y Calidad --------------------------------------
        bl = q["bloques"]["II. Rentabilidad y Calidad"]
        st.markdown(f"**II. Rentabilidad y Calidad — {bl['obtenidos']:.1f}/{bl['maximo']:.0f}**")
        _linea("roic", f"ROIC {_pct(L.get('roic'))} (ref. coste de capital ~9 %)")
        _linea(
            "calidad_beneficio",
            f"Calidad del beneficio FCF/BN {L['fcf_sobre_beneficio']:.2f}×"
            if es_valido(L.get("fcf_sobre_beneficio"))
            else "Calidad del beneficio (FCF/BN)",
        )
        _linea(
            "margen_neto",
            f"Margen neto {_pct(L.get('margen_neto'))}"
            + (f" (ref. sector >{ref_margen * 100:.0f} %)" if es_valido(ref_margen) else ""),
        )
        _linea(
            "margen_bruto",
            f"Margen bruto {_pct(L.get('margen_bruto'))}"
            + (f" (ref. sector >{ref_bruto * 100:.0f} %)" if es_valido(ref_bruto) else ""),
        )
        _linea("roa", f"ROA {_pct(L.get('roa'))} (escala 0-12 %)")
        _linea(
            "roe",
            f"ROE {_pct(L.get('roe'))}"
            + (f" (ref. sector >{ref_roe * 100:.0f} %)" if es_valido(ref_roe) else ""),
        )

        # --- III. Salud Financiera -------------------------------------------
        bl = q["bloques"]["III. Salud Financiera"]
        st.markdown(f"**III. Salud Financiera — {bl['obtenidos']:.1f}/{bl['maximo']:.0f}**")
        nde = L.get("net_debt_ebitda")
        _linea(
            "net_debt_ebitda",
            f"Net Debt/EBITDA {nde:.2f}× (ref. <2×)" if es_valido(nde) else "Net Debt/EBITDA",
        )
        dil = L.get("dilucion")
        _linea(
            "dilucion",
            f"Dilución {dil * 100:+.1f} % de acciones vs año anterior"
            if es_valido(dil)
            else "Dilución (acciones en circulación)",
        )
        fcf_solidez = sub.get("fcf_solidez")
        if es_valido(fcf_solidez):
            if fcf_solidez >= 100:
                txt_fcf = "Free Cash Flow positivo"
            elif fcf_solidez > 0:
                txt_fcf = "FCF negativo por CAPEX de expansión (CFO positivo)"
            else:
                txt_fcf = "FCF negativo (operativa débil)"
        else:
            txt_fcf = "Free Cash Flow"
        _linea("fcf_solidez", txt_fcf)
        ci = L.get("cobertura_intereses")
        _linea(
            "cobertura_intereses",
            f"Cobertura de intereses (EBIT/Gasto) {ci:.1f}× (ref. >6×)"
            if es_valido(ci)
            else "Cobertura de intereses (EBIT/Gasto intereses)",
        )
        cr = L.get("current_ratio")
        _linea(
            "current_ratio",
            f"Current Ratio {cr:.2f}× (ref. >1,5×)" if es_valido(cr) else "Current Ratio",
        )
        de = L.get("debt_equity")
        _linea(
            "debt_equity",
            f"Debt/Equity {de:.0f} % (ref. <50 %)" if es_valido(de) else "Debt/Equity",
        )
        ap, ap_prev = L.get("apalancamiento"), L.get("apalancamiento_prev")
        _linea(
            "apalancamiento",
            f"Apalancamiento (deuda LP/activos) {_pct(ap)} vs {_pct(ap_prev)} el año anterior"
            if es_valido(ap) and es_valido(ap_prev)
            else "Apalancamiento decreciente",
        )
        cr_prev = L.get("current_ratio_prev")
        _linea(
            "liquidez_creciente",
            f"Liquidez corriente {cr:.2f}× vs {cr_prev:.2f}× el año anterior"
            if es_valido(cr) and es_valido(cr_prev)
            else "Liquidez corriente creciente",
        )

        # --- IV. Valoración Relativa -----------------------------------------
        bl = q["bloques"]["IV. Valoración Relativa"]
        st.markdown(f"**IV. Valoración Relativa — {bl['obtenidos']:.1f}/{bl['maximo']:.0f}**")
        peg = L.get("peg")
        _linea("peg", f"PEG {peg:.2f} (ref. <1,0)" if es_valido(peg) else "PEG")
        fwd, per = L.get("forward_per"), L.get("per")
        _linea(
            "forward_per",
            f"PER Forward {fwd:.1f}× vs PER actual {per:.1f}×"
            if es_valido(fwd) and es_valido(per)
            else "PER Forward vs PER actual",
        )
        eve, eve_sector = L.get("ev_ebitda"), L.get("ev_ebitda_sector")
        _linea(
            "ev_ebitda",
            f"EV/EBITDA {eve:.1f}× vs sector {eve_sector:.1f}×"
            if es_valido(eve) and es_valido(eve_sector)
            else (f"EV/EBITDA {eve:.1f}×" if es_valido(eve) else "EV/EBITDA vs sector"),
        )
        per_hist = L.get("per_historico_5a")
        _linea(
            "per_vs_historico",
            f"PER {per:.1f}× vs propio 5a (mediana) {per_hist:.1f}×"
            if es_valido(per) and es_valido(per_hist)
            else "PER vs histórico propio (5a)",
        )
        per_sector = L.get("per_sector")
        _linea(
            "per_vs_sector",
            f"PER {per:.1f}× vs sector {per_sector:.1f}×"
            if es_valido(per) and es_valido(per_sector)
            else "PER vs sector",
        )

        C.metrica("Cobertura del modelo", fmt_pct(q.get("cobertura", 0) * 100, 0))
        if q["excluidos"]:
            st.caption("Excluidos por falta de dato: " + ", ".join(q["excluidos"]))


def _clave_peso(nombre: str) -> str:
    return {
        "DCF": "dcf",
        "Múltiplos": "multiplos",
        "EV/EBITDA sectorial": "ev_ebitda",
        "Valoración PEG": "peg",
        "Consenso analistas": "consenso",
    }.get(nombre, nombre.lower())


# ============================================================== Bloque 5 ======
def _bloque_5_timing(a: dict) -> None:
    tm = a["timing"]
    C.titulo_bloque("Valoración del timing y Señal de entrada")

    st.markdown("**Puntuación de timing**")
    C.nota(tm.get("puntuacion"), tm.get("color", "#94a3b8"))
    st.write("")
    C.alerta(tm.get("senal", TEXTO_ND), tm.get("color", "#94a3b8"))

    if tm.get("nota_salud"):
        st.caption(tm["nota_salud"])

    clave_consenso = (a["paquete"].get("consenso", {}).get("recomendacion") or "").lower()
    texto_consenso, color_consenso = CONSENSO_ANALISTAS_ES.get(clave_consenso, (TEXTO_ND, "#94a3b8"))
    C.metrica_pastilla("Consenso de analistas", texto_consenso, color_consenso)
    n_analistas = a["paquete"].get("consenso", {}).get("n_analistas")
    C.metrica("Analistas que cubren", fmt_num(n_analistas, 0))

    with st.expander("Componentes del timing"):
        _desglose_timing(tm, a["paquete"])
        C.metrica("Cobertura del modelo", fmt_pct((tm.get("cobertura") or 0) * 100, 0))
        if tm.get("excluidos"):
            st.caption("Excluidos por falta de dato: " + ", ".join(tm["excluidos"]))


def _texto_cruce_medias(cm: dict) -> tuple[str, str]:
    """Texto y color de la fila informativa de Golden/Death Cross.

    Sin fracción de puntos a propósito (a diferencia de `_linea`): dejar
    claro de un vistazo que no pondera en la nota de timing, solo aporta
    contexto ya recogido en ADX, MM50 y MM200.
    """
    if not cm or cm.get("estado_actual") is None:
        return "Sin datos suficientes de MM50 / MM200", C_TEXTO_TENUE

    sesiones = cm.get("sesiones_desde_cruce")
    tipo = cm.get("tipo_ultimo_cruce")
    if sesiones is not None and tipo == "golden":
        plural = "sesión" if sesiones == 1 else "sesiones"
        return f"Golden Cross activo (hace {sesiones} {plural})", C_VERDE_OSCURO
    if sesiones is not None and tipo == "death":
        plural = "sesión" if sesiones == 1 else "sesiones"
        return f"Death Cross activo (hace {sesiones} {plural})", C_ROJO

    if cm.get("proximo_a_cruzar"):
        objetivo = "Golden Cross" if cm.get("estado_actual") == "bajista" else "Death Cross"
        distancia = abs(cm.get("distancia_pct") or 0.0)
        return f"Convergiendo: MM50 a {fmt_num(distancia, 1)} % del {objetivo}", C_AMBAR

    tendencia = "alcista" if cm.get("estado_actual") == "alcista" else "bajista"
    return f"Tendencia de medias {tendencia} establecida (sin cruce reciente)", C_TEXTO_TENUE


def _desglose_timing(tm: dict, p: dict) -> None:
    """Una fila por métrica, ORDENADAS DE MAYOR A MENOR PESO (mismo criterio
    que el desglose de Calidad): valor real a la izquierda y puntos
    obtenidos a la derecha, con el mismo código de color (verde ≥70, ámbar
    ≥40, rojo por debajo; gris si no hay dato). Cierra con una fila
    informativa SIN peso propio: el estado del cruce MM50/MM200."""
    L = tm.get("lecturas", {})
    comp = tm.get("componentes", {})

    def _linea(clave: str, etiqueta: str) -> None:
        peso_max = PESOS_TIMING.get(clave, 0)
        valor_sub = comp.get(clave)
        if not es_valido(valor_sub) or not peso_max:
            C.metrica_color(f"{etiqueta}: sin dato", "excluido", C_TEXTO_TENUE)
            return
        puntos = valor_sub / 100 * peso_max
        color = C_VERDE_OSCURO if valor_sub >= 70 else (C_AMBAR if valor_sub >= 40 else C_ROJO)
        C.metrica_color(etiqueta, f"+{puntos:.1f}/{peso_max:.0f}", color)

    # --- se construye el texto de cada métrica primero; el orden de render --
    # se decide después, por peso, para que cambiar PESOS_TIMING reordene la
    # tabla automáticamente sin tocar esta función.
    textos: dict[str, str] = {}

    rsi = L.get("rsi")
    textos["rsi"] = f"RSI {fmt_num(rsi, 1)}" if es_valido(rsi) else "RSI (14)"

    cruce, mejora = L.get("macd_cruce_alcista"), L.get("macd_mejora")
    if cruce is None:
        textos["macd"] = "MACD vs señal"
    else:
        estado = "cruce alcista" if cruce else "cruce bajista"
        if mejora is True:
            estado += ", histograma mejorando"
        elif mejora is False:
            estado += ", histograma deteriorándose"
        textos["macd"] = (
            f"MACD {fmt_num(L.get('macd'), 2)} vs señal {fmt_num(L.get('macd_senal'), 2)} "
            f"({estado})"
        )

    obv = L.get("obv_tendencia_pct")
    textos["obv"] = f"Pendiente del OBV {fmt_pct(obv, 1)} (escala ±5 %)" if es_valido(obv) else "OBV"

    adx, dm, dme = L.get("adx"), L.get("di_mas"), L.get("di_menos")
    if es_valido(adx) and es_valido(dm) and es_valido(dme):
        # Por debajo de 20 el ADX no acredita tendencia: decir "bajista" solo
        # porque −DI supera a +DI por unas décimas sería sobreinterpretar ruido.
        if adx < 20:
            direccion = "sin tendencia definida"
        else:
            direccion = "tendencia alcista" if dm > dme else "tendencia bajista"
        textos["adx"] = (
            f"ADX {fmt_num(adx, 1)} · +DI {fmt_num(dm, 1)} / −DI {fmt_num(dme, 1)} ({direccion})"
        )
    elif es_valido(adx):
        textos["adx"] = f"ADX {fmt_num(adx, 1)} (sin dirección)"
    else:
        textos["adx"] = "ADX (14) con dirección"

    vol, var_corta = L.get("volumen_relativo"), L.get("variacion_corta_pct")
    if es_valido(vol):
        textos["volumen_relativo"] = f"Volumen 5 sesiones ×{fmt_num(vol, 2)} sobre media 3 m"
        if es_valido(var_corta):
            textos["volumen_relativo"] += f" · precio {fmt_pct(var_corta, 1)}"
    else:
        textos["volumen_relativo"] = "Volumen relativo reciente"

    d50, d200 = L.get("distancia_mm50_pct"), L.get("distancia_mm200_pct")
    textos["mm50"] = (
        f"Precio {fmt_pct(d50, 1)} respecto a la MM50" if es_valido(d50) else "Distancia a la MM50"
    )
    textos["mm200"] = (
        f"Precio {fmt_pct(d200, 1)} respecto a la MM200"
        if es_valido(d200)
        else "Distancia a la MM200"
    )

    pos = L.get("posicion_ath_atl")
    textos["distancia_ath_atl"] = (
        f"Posición en el rango ATL-ATH {fmt_num(pos, 0)} %"
        if es_valido(pos)
        else "Distancia a ATH / ATL"
    )

    var1a = L.get("variacion_1a_pct")
    textos["variacion_1a"] = (
        f"Variación a 1 año {fmt_pct(var1a, 1)}" if es_valido(var1a) else "Variación a 1 año"
    )

    zona = L.get("zona_confluencia") or {}
    if zona.get("precio") is not None:
        textos["confluencia_dca"] = (
            f"Zona DCA más cercana en {_precio_fmt(zona.get('precio'), p)} "
            f"({fmt_pct(zona.get('distancia_pct'), 1)}, confluencia {fmt_num(zona.get('peso'), 1)})"
        )
    else:
        textos["confluencia_dca"] = "Proximidad a zona de confluencia DCA"

    ups = L.get("upside_pct")
    textos["upside"] = (
        f"Potencial sobre el valor objetivo {fmt_pct(ups, 1)}"
        if es_valido(ups)
        else "Potencial sobre el valor objetivo"
    )

    peg = L.get("peg")
    textos["peg"] = f"PEG {fmt_num(peg, 2)} (escala 3,0 → 0,8)" if es_valido(peg) else "PEG"

    salud = L.get("salud")
    textos["salud_fundamental"] = (
        f"Salud fundamental {fmt_num(salud, 0)}/100" if es_valido(salud) else "Salud fundamental"
    )

    fr, simbolo = L.get("fuerza_relativa_pct"), L.get("referencia_simbolo")
    if es_valido(fr):
        # Es un DIFERENCIAL de rentabilidad, así que se expresa en puntos
        # porcentuales (pp) y no en %: mezclar ambas unidades induce a error.
        textos["fuerza_relativa"] = (
            f"Fuerza relativa a 3 m vs {simbolo or 'mercado'}: "
            f"{fmt_pct(fr, 1).replace(' %', ' pp')}"
        )
    else:
        textos["fuerza_relativa"] = "Fuerza relativa vs sector / mercado"

    dias = L.get("dias_earnings")
    textos["proximidad_earnings"] = (
        f"Próximos resultados en {dias:.0f} días"
        if es_valido(dias) and dias >= 0
        else "Proximidad de resultados"
    )

    # --- render: de mayor a menor peso, empates por orden de PESOS_TIMING ---
    orden = [clave for clave, _ in sorted(PESOS_TIMING.items(), key=lambda kv: -kv[1])]
    for clave in orden:
        _linea(clave, textos.get(clave, clave))
        if clave == "confluencia_dca" and zona.get("motivos"):
            # El motor DCA acumula un motivo por candidato, así que una zona
            # con cuatro pivotes históricos repite "Soporte histórico" cuatro
            # veces. Aquí se muestra cada tipo una sola vez, con recuento si
            # aparece varias veces; el peso de la zona ya refleja la
            # acumulación.
            vistos: dict[str, int] = {}
            for m in zona["motivos"]:
                vistos[m] = vistos.get(m, 0) + 1
            st.caption(
                "↳ " + " · ".join(m if n == 1 else f"{m} (×{n})" for m, n in vistos.items())
            )

    # --- fila informativa sin peso: cruce de medias --------------------------
    st.caption("Sin peso propio en la puntuación — información de contexto:")
    texto_cm, color_cm = _texto_cruce_medias(L.get("cruce_medias") or {})
    C.metrica_color("Cruce de medias (MM50 / MM200)", texto_cm, color_cm)


# ============================================================== Bloque 6 ======
def _bloque_6_plan(a: dict) -> None:
    plan, p = a["plan"], a["paquete"]
    ver = a["veredicto"]
    C.titulo_bloque("Plan de inversión DCA y Valoración final")

    C.alerta(ver["etiqueta"], ver["color"])
    st.caption(" · ".join(ver["motivos"]))

    if not plan.get("disponible"):
        st.markdown(
            f'<div class="ss-nd">{TEXTO_ND}: {plan.get("motivo", "")}</div>', unsafe_allow_html=True
        )
        return

    _override_dca(a)

    st.markdown("**Niveles de entrada**")
    for n in plan["entradas"]:
        etiqueta = f"Entrada {n['nivel']} · {n['peso_capital'] * 100:.0f} % del capital"
        if n.get("manual"):
            etiqueta += " · 🔧 Selección manual"
        C.nivel_plan(
            etiqueta,
            _precio_fmt(n["precio"], p),
            fmt_pct(n["distancia_pct"]),
            n["motivos"],
        )

    st.markdown("**Niveles de salida**")
    for n in plan["salidas"]:
        etiqueta = f"Salida {n['nivel']} · {n['peso_posicion'] * 100:.0f} % de la posición"
        if n.get("manual"):
            etiqueta += " · 🔧 Selección manual"
        C.nivel_plan(
            etiqueta,
            _precio_fmt(n["precio"], p),
            fmt_pct(n["distancia_pct"]),
            n["motivos"],
        )

    st.markdown("**Stop loss**")
    sl = plan["stop_loss"]
    C.nivel_plan("Stop loss", _precio_fmt(sl["precio"], p), fmt_pct(sl["distancia_pct"]), [sl["base"]])

    C.metrica("Precio medio estimado", _precio_fmt(plan["precio_medio_estimado"], p))
    C.metrica("Objetivo medio estimado", _precio_fmt(plan["objetivo_medio_estimado"], p))
    C.metrica("Ratio riesgo / recompensa", fmt_num(plan["ratio_riesgo_recompensa"]))

    st.divider()
    _panel_paper_trading(a, plan)


def _etiqueta_zona(zona: dict, p: dict) -> str:
    """Peso PRIMERO a propósito, y abreviado a 'P' para dejar sitio de sobra
    al precio: el desplegable trunca por ancho, y con pesos de dos dígitos un
    formato "precio · peso X.X" cortaba a mitad del número (ej. "peso 1" en
    vez de "peso 11.8" — parecía un peso distinto, no uno truncado). Los
    motivos no van aquí: ya se muestran completos en el caption de debajo,
    sin límite de ancho."""
    precio_fmt = _precio_fmt(zona["precio"], p).replace(" $", "$").replace(" €", "€")
    return f"P{zona.get('peso', 0):.1f} · {precio_fmt}"


def _indice_por_defecto(zonas: list[dict], precio_actual: float | None) -> int:
    """Preselecciona en el desplegable la zona que ya habría elegido el
    motor automático (o el override guardado), para que activar el modo
    manual arranque desde el plan ya calculado y no desde cero."""
    if precio_actual is None:
        return 0
    for i, z in enumerate(zonas):
        if abs(z["precio"] - precio_actual) < 1e-6:
            return i
    return 0


def _recalcular_plan(a: dict) -> dict:
    """Reconstruye `plan` (y el veredicto) a partir de un override recién
    guardado o borrado, reutilizando `paquete`/`tecnico`/`valoracion` ya
    calculados en `a` — SIN volver a llamar a yfinance/Finnhub/SEC. El
    override que compara `plan_dca.construir_plan()` es siempre el que
    devuelve Supabase en este momento, no el que había al abrir la página."""
    ticker = a["paquete"]["ticker"]
    override = bd_supabase.obtener_override_dca(ticker)
    plan = plan_dca.construir_plan(a["paquete"], a["tecnico"], a["valoracion"], override=override or None)
    veredicto = plan_dca.veredicto_final(a["calidad"], a["valoracion"], a["timing"], plan)
    a["plan"] = plan
    a["veredicto"] = veredicto
    a["override_activo"] = override
    return a


def _override_dca(a: dict) -> None:
    """Interruptor de selección manual de niveles, sobre las zonas que ya
    detecta el motor de confluencia. Solo entre las zonas detectadas — nada
    de precio libre — y persistido en Supabase como snapshot (precio, peso,
    motivos), no como referencia a una zona que puede dejar de existir en el
    próximo análisis."""
    p = a["paquete"]
    ticker = p["ticker"]
    zonas = a.get("zonas_disponibles") or {"entradas": [], "salidas": []}
    plan = a["plan"]
    conectado = bd_supabase.hay_conexion()

    hay_override = bool(a.get("override_activo", {}).get("entradas") or a.get("override_activo", {}).get("salidas"))
    etiqueta = "🔧 Ajustar niveles manualmente" + (" (override activo)" if hay_override else "")
    activo = st.toggle(etiqueta, value=False, key=f"override_dca_{ticker}")
    if not activo:
        return

    if not conectado:
        st.warning("Configura SUPABASE_URL y SUPABASE_KEY para guardar una selección manual.")
        return
    if not zonas["entradas"] and not zonas["salidas"]:
        st.info("El motor no ha detectado zonas de confluencia para este ticker.")
        return

    st.caption(
        "Elige entre las zonas que ya detecta el motor. La selección sustituye al "
        "cálculo automático hasta que la restablezcas."
    )

    col_e, col_s = st.columns(2)
    elegidas_entrada: list[dict] = []
    with col_e:
        st.markdown("**Entradas**")
        if not zonas["entradas"]:
            st.caption("Sin zonas de soporte detectadas en rango.")
        for i in range(min(3, len(zonas["entradas"]))):
            actual = plan["entradas"][i]["precio"] if i < len(plan.get("entradas", [])) else None
            idx = st.selectbox(
                f"Entrada {i + 1}",
                options=list(range(len(zonas["entradas"]))),
                index=_indice_por_defecto(zonas["entradas"], actual),
                format_func=lambda j: _etiqueta_zona(zonas["entradas"][j], p),
                key=f"override_entrada_{ticker}_{i}",
            )
            zona_elegida = zonas["entradas"][idx]
            elegidas_entrada.append(zona_elegida)
            st.caption("Componentes: " + ", ".join(zona_elegida.get("motivos") or ["—"]))

    elegidas_salida: list[dict] = []
    with col_s:
        st.markdown("**Salidas**")
        if not zonas["salidas"]:
            st.caption("Sin zonas de resistencia detectadas en rango.")
        for i in range(min(3, len(zonas["salidas"]))):
            actual = plan["salidas"][i]["precio"] if i < len(plan.get("salidas", [])) else None
            idx = st.selectbox(
                f"Salida {i + 1}",
                options=list(range(len(zonas["salidas"]))),
                index=_indice_por_defecto(zonas["salidas"], actual),
                format_func=lambda j: _etiqueta_zona(zonas["salidas"][j], p),
                key=f"override_salida_{ticker}_{i}",
            )
            zona_elegida = zonas["salidas"][idx]
            elegidas_salida.append(zona_elegida)
            st.caption("Componentes: " + ", ".join(zona_elegida.get("motivos") or ["—"]))

    col_guardar, col_restablecer = st.columns(2)
    if col_guardar.button("Guardar selección manual", type="primary", use_container_width=True, key=f"guardar_override_{ticker}"):
        ok_e = bd_supabase.guardar_override_dca(ticker, "entrada", elegidas_entrada) if elegidas_entrada else True
        ok_s = bd_supabase.guardar_override_dca(ticker, "salida", elegidas_salida) if elegidas_salida else True
        if ok_e and ok_s:
            st.session_state["analisis"] = _recalcular_plan(a)
            st.rerun()
        else:
            st.error("No se ha podido guardar la selección. Revisa la conexión con Supabase.")

    if hay_override and col_restablecer.button("Restablecer automático", use_container_width=True, key=f"reset_override_{ticker}"):
        if bd_supabase.borrar_override_dca(ticker):
            st.session_state["analisis"] = _recalcular_plan(a)
            st.rerun()
        else:
            st.error("No se ha podido restablecer. Revisa la conexión con Supabase.")


def _panel_paper_trading(a: dict, plan: dict) -> None:
    """Reemplaza el antiguo "Ejecutar plan en Paper Trading": ahora el plan
    se GUARDA en seguimiento (estado inicial 'vigilancia'), esté o no el
    precio ya en la Entrada 1 — la ejecución real de cada nivel se hace
    después, desde el apartado Paper Trading."""
    p, v = a["paquete"], a["valoracion"]
    ticker = p["ticker"]
    moneda = p.get("moneda")
    conectado = bd_supabase.hay_conexion()

    if not conectado:
        st.button(
            "Guardar plan en Paper Trading",
            disabled=True,
            use_container_width=True,
            help="Configura SUPABASE_URL y SUPABASE_KEY para guardar planes.",
        )
        return

    if moneda not in CARTERA_DIVISAS_CONVERTIBLES:
        st.button(
            "Guardar plan en Paper Trading",
            disabled=True,
            use_container_width=True,
            help=f"Divisa de cotización ({moneda or TEXTO_ND}) no soportada todavía para el "
            "seguimiento en euros. Se admiten valores en "
            + " y ".join(CARTERA_DIVISAS_CONVERTIBLES) + ".",
        )
        return

    existente = bd_supabase.plan_activo(ticker)
    if existente:
        etiqueta = PAPER_ESTADOS.get(existente.get("estado"), (existente.get("estado"),))[0]
        st.info(
            f"Ya hay un plan en seguimiento para {ticker} ({etiqueta}). "
            "Gestiónalo desde el apartado Paper Trading."
        )
        return

    # `vertical_alignment="bottom"` alinea la base del input con la del botón
    # sin trucos. El `st.write("")` que se usaba antes asumía que la etiqueta
    # ocupaba exactamente una línea; con el icono del tooltip se partía en dos
    # y el botón quedaba desplazado (además de depender del ancho de pantalla).
    col_capital, col_boton = st.columns([1, 2], vertical_alignment="bottom")
    capital = col_capital.number_input(
        "Capital asignado (€)",
        min_value=0.0,
        step=100.0,
        format="%.2f",
        key=f"capital_paper_{ticker}",
    )
    with col_boton:
        guardar = st.button("Guardar plan en Paper Trading", type="primary", use_container_width=True)

    st.caption(
        "Presupuesto total en euros para las 3 entradas del plan, según su reparto "
        "de peso (40 / 35 / 25 %)."
    )

    if not guardar:
        return
    if capital <= 0:
        st.warning("Indica el capital asignado (€) antes de guardar el plan.")
        return

    posicion_id = bd_supabase.guardar_plan_paper_trading(
        ticker,
        plan,
        {
            "moneda": moneda,
            "fair_value": v.get("fair_value"),
            "upside_pct": v.get("upside_pct"),
            "puntuacion_calidad": a["calidad"].get("puntuacion"),
            "puntuacion_timing": a["timing"].get("puntuacion"),
            "veredicto": a["veredicto"]["etiqueta"],
        },
        capital,
    )
    if posicion_id:
        if alertas_telegram.disponible():
            alertas_telegram.alerta_plan_ejecutado(ticker, plan, a["veredicto"]["etiqueta"])
        st.session_state["seccion"] = "Paper Trading"
        st.rerun()
    else:
        st.error("No se ha podido guardar el plan. Revisa la conexión con Supabase.")
