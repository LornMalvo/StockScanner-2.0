"""Apartado "Análisis Individual": los 6 bloques descritos en el wireframe."""

from __future__ import annotations

import html

import streamlit as st

from config.settings import (
    C_PRIMARIO,
    C_ROJO,
    C_TEXTO_TENUE,
    C_VERDE,
    CURRENT_RATIO_MEDIANO_SECTOR,
    DEBT_EQUITY_MEDIANO_SECTOR,
    EV_EBITDA_MEDIANO_SECTOR,
    FORWARD_PER_MEDIANO_SECTOR,
    MARGEN_EBITDA_MEDIANO_SECTOR,
    MARGEN_NETO_MEDIANO_SECTOR,
    MARGEN_OPERATIVO_MEDIANO_SECTOR,
    PB_MEDIANO_SECTOR,
    PEG_MEDIANO_SECTOR,
    PER_MEDIANO_SECTOR,
    PESOS_CALIDAD,
    PS_MEDIANO_SECTOR,
    ROA_MEDIANO_SECTOR,
    ROE_MEDIANO_SECTOR,
    ROIC_MEDIANO_SECTOR,
    TEXTO_ND,
)
from core import alertas_telegram, bd_supabase, datos_api, indicadores, plan_dca, timing, valoracion
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
def ejecutar_analisis(ticker: str) -> dict:
    """Encadena datos -> técnico -> valoración -> calidad -> timing -> plan."""
    paquete = datos_api.obtener_paquete(ticker)
    if not paquete["existe"]:
        return {"error": f"No se han encontrado datos para el ticker «{ticker}»."}

    tecnico = indicadores.calcular_todo(paquete["historico"])
    fair_value = valoracion.calcular_fair_value(paquete)
    calidad = valoracion.puntuar_calidad(paquete, fair_value)
    momento = timing.calcular_timing(paquete, tecnico, fair_value, calidad)
    plan = plan_dca.construir_plan(paquete, tecnico, fair_value)
    veredicto = plan_dca.veredicto_final(calidad, fair_value, momento, plan)

    return {
        "paquete": paquete,
        "tecnico": tecnico,
        "valoracion": fair_value,
        "calidad": calidad,
        "timing": momento,
        "plan": plan,
        "veredicto": veredicto,
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
        with st.spinner("Recopilando datos y calculando…"):
            st.session_state["analisis"] = ejecutar_analisis(ticker)
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
        st.caption(descripcion[:520] + ("…" if len(descripcion) > 520 else ""))
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

    C.grafico_precio_macd(p.get("historico"), t, p["ticker"])
    _diagnostico_info(p)

    col_f, col_t = st.columns(2)
    with col_f:
        st.markdown("**Fundamentales**")
        C.metrica("Capitalización", fmt_compacto_usd_eur(info.get("marketCap"), fx))
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
        _fila_distancia("Media móvil 50", t.get("mm50"), precio)
        _fila_distancia("Media móvil 200", t.get("mm200"), precio)
        _fila_distancia("Máximo 52 semanas", t.get("max_52s"), precio)
        _fila_distancia("Mínimo 52 semanas", t.get("min_52s"), precio)
        C.metrica("Variación 1 año", fmt_pct(t.get("variacion_1a_pct")))
        C.metrica("Volumen medio 3 meses", fmt_compacto(t.get("volumen_medio_3m")))

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


def _fila_distancia(etiqueta: str, valor, precio) -> None:
    """Métrica técnica junto a su distancia en % respecto al precio actual.
    Solo la distancia lleva color (verde si es positiva, rojo si es negativa);
    el valor de la media/máximo/mínimo se muestra en el estilo normal."""
    if not es_valido(valor):
        C.metrica(etiqueta, TEXTO_ND)
        return
    texto = fmt_num(valor)
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
    C.metrica("Potencial (upside)", fmt_pct(v.get("upside_pct")))
    if v.get("peso_consenso_doble"):
        st.caption("Peso doble aplicado al consenso: cobertura ≥ 10 analistas.")

    with st.expander("Desglose de la valoración"):
        for nombre, comp in v["componentes"].items():
            valor = comp["valor"]
            peso = v["pesos_aplicados"].get(_clave_peso(nombre))
            sufijo = f"  ·  peso {peso * 100:.0f} %" if peso else "  ·  excluido del cálculo"
            C.metrica(nombre, _precio_fmt(valor, p) + sufijo)
            for n in comp["detalle"].get("notas", []):
                st.caption(f"↳ {n}")
            formula = comp["detalle"].get("formula")
            if formula:
                ver_calculo = st.toggle(
                    "Ver cálculo", key=f"toggle_formula_{_clave_peso(nombre)}_{p['ticker']}"
                )
                if ver_calculo:
                    st.caption(formula)
        C.metrica("Cobertura del modelo", fmt_pct(v.get("cobertura", 0) * 100, 0))

    with st.expander("Piotroski F-Score"):
        pio = q["piotroski"]
        C.metrica("Puntuación", f"{pio['puntos']} / {pio['evaluados']} criterios evaluables")
        for criterio, cumple in pio["criterios"].items():
            simbolo = "✔  (+1)" if cumple else ("✘  (+0)" if cumple is False else TEXTO_ND)
            C.metrica(criterio, simbolo)

    with st.expander("Métricas de calidad"):
        L = q["lecturas"]
        sub = q["subpuntuaciones"]
        sector = p.get("sector")
        ref_margen = MARGEN_NETO_MEDIANO_SECTOR.get(sector)
        ref_roe = ROE_MEDIANO_SECTOR.get(sector)

        def _pts(clave: str) -> str:
            """'+X,X/máx' según la sub-puntuación 0-100 y el peso de esa métrica."""
            valor_sub = sub.get(clave)
            peso_max = PESOS_CALIDAD.get(clave, 0)
            if not es_valido(valor_sub) or not peso_max:
                return "Excluido (sin dato)"
            return f"+{valor_sub / 100 * peso_max:.1f}/{peso_max:.0f}"

        pio = q["piotroski"]
        C.metrica(f"Piotroski F-Score ({pio['puntos']}/{pio['evaluados']} criterios)", _pts("piotroski"))

        if es_valido(L.get("per")) and es_valido(L.get("per_sector")):
            C.metrica(f"PER {L['per']:.1f}× vs sector {L['per_sector']:.1f}×", _pts("per_vs_sector"))
        else:
            C.metrica("PER vs sector", _pts("per_vs_sector"))

        if es_valido(L.get("per")) and es_valido(L.get("per_historico_5a")):
            C.metrica(
                f"PER {L['per']:.1f}× vs histórico propio 5a (mediana) {L['per_historico_5a']:.1f}×",
                _pts("per_vs_historico"),
            )
        else:
            C.metrica("PER vs histórico propio (5a, mediana)", _pts("per_vs_historico"))

        if es_valido(L.get("forward_per")) and es_valido(L.get("per")):
            C.metrica(f"Forward PER {L['forward_per']:.1f}× vs PER actual {L['per']:.1f}×", _pts("forward_per"))
        else:
            C.metrica("Forward PER vs PER actual", _pts("forward_per"))

        if es_valido(L.get("margen_neto")):
            ref_txt = f" (ref. sector >{ref_margen * 100:.0f} %)" if es_valido(ref_margen) else ""
            C.metrica(f"Margen neto {L['margen_neto'] * 100:.1f} %{ref_txt}", _pts("margen_neto"))
        else:
            C.metrica("Margen neto", _pts("margen_neto"))

        if es_valido(L.get("roe")):
            ref_txt = f" (ref. sector >{ref_roe * 100:.0f} %)" if es_valido(ref_roe) else ""
            C.metrica(f"ROE {L['roe'] * 100:.1f} %{ref_txt}", _pts("roe"))
        else:
            C.metrica("ROE", _pts("roe"))

        if es_valido(L.get("roic")):
            C.metrica(f"ROIC {L['roic'] * 100:.1f} % (escala 2 %-20 %)", _pts("roic"))
        else:
            C.metrica("ROIC", _pts("roic"))

        if es_valido(L.get("peg")):
            C.metrica(f"PEG {L['peg']:.2f} (escala 0,8-3,0×, menos es mejor)", _pts("peg"))
        else:
            C.metrica("PEG", _pts("peg"))

        if es_valido(L.get("cagr_ingresos")):
            C.metrica(
                f"Crec. ingresos {L['cagr_ingresos'] * 100:.1f} % × estabilidad "
                f"×{L.get('estabilidad_ingresos', 1.0):.2f}",
                _pts("tendencia_ingresos"),
            )
        else:
            C.metrica("Crec. ingresos × estabilidad", _pts("tendencia_ingresos"))

        if es_valido(L.get("cagr_beneficios")):
            C.metrica(
                f"Crec. beneficios {L['cagr_beneficios'] * 100:.1f} % × estabilidad "
                f"×{L.get('estabilidad_beneficios', 1.0):.2f}",
                _pts("tendencia_beneficios"),
            )
        else:
            C.metrica("Crec. beneficios × estabilidad", _pts("tendencia_beneficios"))

        if es_valido(L.get("fcf_sobre_beneficio")):
            C.metrica(f"Calidad beneficio FCF/BN {L['fcf_sobre_beneficio']:.2f}×", _pts("calidad_beneficio"))
        else:
            C.metrica("Calidad beneficio (FCF/BN)", _pts("calidad_beneficio"))

        fcf_solidez = sub.get("fcf_solidez")
        if es_valido(fcf_solidez):
            if fcf_solidez >= 100:
                etiqueta_fcf = "Solidez del FCF: positivo"
            elif fcf_solidez > 0:
                etiqueta_fcf = "Solidez del FCF: negativo por CAPEX de expansión (CFO positivo)"
            else:
                etiqueta_fcf = "Solidez del FCF: negativo (operativa débil o sin datos de CFO)"
        else:
            etiqueta_fcf = "Solidez del FCF"
        C.metrica(etiqueta_fcf, _pts("fcf_solidez"))

        if es_valido(L.get("cobertura_intereses")):
            C.metrica(f"Cobertura intereses {L['cobertura_intereses']:.1f}× (EBIT/Gasto intereses)", _pts("cobertura_intereses"))
        else:
            C.metrica("Cobertura de intereses (EBIT/Gasto intereses)", _pts("cobertura_intereses"))

        if q["excluidos"]:
            st.caption("Excluidos por falta de dato: " + ", ".join(q["excluidos"]))


def _clave_peso(nombre: str) -> str:
    return {
        "DCF": "dcf",
        "Múltiplos": "multiplos",
        "EV/EBITDA sectorial": "ev_ebitda",
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

    C.metrica("Margen de seguridad", fmt_pct(tm.get("margen_seguridad_pct")))
    C.metrica("Consenso de analistas", a["paquete"].get("consenso", {}).get("recomendacion") or TEXTO_ND)
    n_analistas = a["paquete"].get("consenso", {}).get("n_analistas")
    C.metrica("Analistas que cubren", fmt_num(n_analistas, 0))

    with st.expander("Componentes del timing"):
        etiquetas = {
            "rsi": "RSI",
            "macd": "MACD",
            "margen_seguridad": "Margen de seguridad",
            "upside": "Upside",
            "peg": "PEG (<1,5)",
            "salud_fundamental": "Salud fundamental",
            "mm50": "Distancia a MM50",
            "mm200": "Distancia a MM200",
            "variacion_1a": "Variación 1 año",
            "distancia_ath_atl": "Distancia ATH / ATL",
            "obv": "OBV",
            "adx": "ADX",
            "proximidad_earnings": "Proximidad de resultados",
        }
        for clave, etiqueta in etiquetas.items():
            valor = tm["componentes"].get(clave)
            peso = (tm.get("pesos_aplicados") or {}).get(clave)
            sufijo = f"  ·  peso {peso * 100:.0f} %" if peso else "  ·  excluido"
            C.metrica(etiqueta, (fmt_num(valor, 0) if es_valido(valor) else TEXTO_ND) + sufijo)
        C.metrica("Cobertura del modelo", fmt_pct((tm.get("cobertura") or 0) * 100, 0))


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

    st.markdown("**Niveles de entrada**")
    for n in plan["entradas"]:
        C.nivel_plan(
            f"Entrada {n['nivel']} · {n['peso_capital'] * 100:.0f} % del capital",
            _precio_fmt(n["precio"], p),
            fmt_pct(n["distancia_pct"]),
            n["motivos"],
        )

    st.markdown("**Niveles de salida**")
    for n in plan["salidas"]:
        C.nivel_plan(
            f"Salida {n['nivel']} · {n['peso_posicion'] * 100:.0f} % de la posición",
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
    _boton_paper_trading(a, plan)


def _boton_paper_trading(a: dict, plan: dict) -> None:
    p = a["paquete"]
    nivel_1 = plan["entradas"][0]["precio"]
    ejecutable = plan.get("ejecutable", False)
    conectado = bd_supabase.hay_conexion()

    if not ejecutable:
        st.button(
            "Ejecutar plan en Paper Trading",
            disabled=True,
            use_container_width=True,
            help=f"El precio actual ({_precio_fmt(p.get('precio'), p)}) todavía no ha alcanzado "
            f"el nivel 1 de entrada ({_precio_fmt(nivel_1, p)}).",
        )
        st.caption("El plan se activará cuando la cotización alcance o pierda el nivel 1 de entrada.")
        return

    if not conectado:
        st.button(
            "Ejecutar plan en Paper Trading",
            disabled=True,
            use_container_width=True,
            help="Configura SUPABASE_URL y SUPABASE_KEY para guardar operaciones.",
        )
        return

    if st.button("Ejecutar plan en Paper Trading", type="primary", use_container_width=True):
        ok = bd_supabase.abrir_paper_trade(
            p["ticker"],
            plan,
            {
                "puntuacion_calidad": a["calidad"].get("puntuacion"),
                "puntuacion_timing": a["timing"].get("puntuacion"),
                "veredicto": a["veredicto"]["etiqueta"],
            },
        )
        if ok:
            st.success("Posición simulada abierta. Disponible en el apartado Paper Trading.")
            if alertas_telegram.disponible():
                alertas_telegram.alerta_plan_ejecutado(
                    p["ticker"], plan, a["veredicto"]["etiqueta"]
                )
        else:
            st.error("No se ha podido guardar la operación. Revisa la conexión con Supabase.")
