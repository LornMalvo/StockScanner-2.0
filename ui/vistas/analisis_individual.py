"""Apartado "Análisis Individual": los 6 bloques descritos en el wireframe."""

from __future__ import annotations

import html

import streamlit as st

from config.settings import C_PRIMARIO, TEXTO_ND
from core import alertas_telegram, bd_supabase, datos_api, indicadores, plan_dca, timing, valoracion
from ui import componentes as C
from utils.formato import (
    dias_hasta,
    es_valido,
    fmt_compacto,
    fmt_fecha,
    fmt_num,
    fmt_pct,
    fmt_usd_eur,
)


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
    fx = p.get("fx_usd_eur")
    moneda = p.get("moneda") or ""

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
                f'<div class="ss-precio">{fmt_num(precio)} {html.escape(moneda)}</div>',
                unsafe_allow_html=True,
            )
            if moneda == "USD":
                eur = f"{precio * fx:,.2f} €".replace(",", "@").replace(".", ",").replace("@", ".")
                sub = eur if es_valido(fx) else f"Tipo de cambio: {TEXTO_ND}"
                st.markdown(f'<div class="ss-precio-eur">{sub}</div>', unsafe_allow_html=True)
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
        C.metrica(
            "Ingresos publicados",
            fmt_usd_eur(ultimo.get("ingresos_real"), fx)
            if es_valido(ultimo.get("ingresos_real"))
            else TEXTO_ND,
        )
        C.metrica(
            "Ingresos estimados",
            fmt_compacto(ultimo.get("ingresos_estimado"))
            if es_valido(ultimo.get("ingresos_estimado"))
            else TEXTO_ND,
        )
        _linea_sorpresa("Ingresos", ultimo.get("ingresos_real"), ultimo.get("ingresos_estimado"))

    proxima = e.get("proxima_fecha")
    dias = dias_hasta(proxima)
    texto = fmt_fecha(proxima) if proxima else TEXTO_ND
    if dias is not None and dias >= 0:
        texto += f"  (en {dias} días)"
    C.metrica("Próxima presentación de resultados", texto)


def _linea_sorpresa(concepto: str, real, estimado) -> None:
    if not es_valido(real) or not es_valido(estimado) or estimado == 0:
        C.metrica(f"¿{concepto} superó estimaciones?", TEXTO_ND)
        return
    desviacion = (real - estimado) / abs(estimado) * 100
    veredicto = "Superó" if desviacion > 0 else ("En línea" if abs(desviacion) < 0.5 else "No superó")
    C.metrica(f"¿{concepto} superó estimaciones?", f"{veredicto} ({fmt_pct(desviacion)})")


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
    C.titulo_bloque("Cotización · MACD y datos fundamentales y técnicos")

    C.grafico_precio_macd(p.get("historico"), t, p["ticker"])
    _diagnostico_info(p)

    col_f, col_t = st.columns(2)
    with col_f:
        st.markdown("**Fundamentales**")
        C.metrica("Capitalización", fmt_usd_eur(info.get("marketCap"), fx, 0)
                  if es_valido(info.get("marketCap")) else TEXTO_ND)
        C.metrica("PER (trailing)", fmt_num(info.get("trailingPE")))
        C.metrica("Forward PER", fmt_num(info.get("forwardPE")))
        C.metrica("PEG", fmt_num(info.get("trailingPegRatio") or info.get("pegRatio")))
        C.metrica("Precio / Ventas", fmt_num(info.get("priceToSalesTrailing12Months")))
        C.metrica("Precio / Valor contable", fmt_num(info.get("priceToBook")))
        C.metrica("Margen neto", fmt_pct(info.get("profitMargins"), 1, ya_en_pct=False))
        C.metrica("ROE", fmt_pct(info.get("returnOnEquity"), 1, ya_en_pct=False))
        C.metrica("ROIC", fmt_pct(a["calidad"]["lecturas"].get("roic"), 1, ya_en_pct=False))
        C.metrica("Deuda / Fondos propios", fmt_num(info.get("debtToEquity")))
        C.metrica("Rentabilidad por dividendo", fmt_pct(info.get("dividendYield"), 2))
    with col_t:
        st.markdown("**Técnicos**")
        C.metrica("RSI (14)", fmt_num(t.get("rsi"), 1))
        C.metrica("MACD", fmt_num(t.get("macd"), 3))
        C.metrica("Señal MACD", fmt_num(t.get("macd_senal"), 3))
        C.metrica("ADX (14)", fmt_num(t.get("adx"), 1))
        C.metrica("ATR (14)", fmt_num(t.get("atr"), 2))
        C.metrica("Media móvil 50", fmt_num(t.get("mm50")))
        C.metrica("Media móvil 200", fmt_num(t.get("mm200")))
        C.metrica("Máximo 52 semanas", fmt_num(t.get("max_52s")))
        C.metrica("Mínimo 52 semanas", fmt_num(t.get("min_52s")))
        C.metrica("Variación 1 año", fmt_pct(t.get("variacion_1a_pct")))
        C.metrica("Volumen medio 3 meses", fmt_compacto(t.get("volumen_medio_3m")))

    if es_valido(fx):
        st.caption(f"Tipo de cambio aplicado: 1 USD = {fmt_num(fx, 4)} EUR (yfinance, tiempo real).")
    else:
        st.caption(f"Conversión a euros: {TEXTO_ND}.")


# ============================================================== Bloque 4 ======
def _bloque_4_calidad(a: dict) -> None:
    v, q, p = a["valoracion"], a["calidad"], a["paquete"]
    fx = p.get("fx_usd_eur")
    C.titulo_bloque("Salud / Calidad fundamental y Valor objetivo")

    st.markdown("**Puntuación de calidad**")
    C.nota(q.get("puntuacion"), C_PRIMARIO)

    st.markdown("**Valor objetivo justo**")
    fv = v.get("fair_value")
    st.markdown(
        f'<div class="ss-precio">{fmt_num(fv)} {html.escape(p.get("moneda") or "")}</div>'
        if es_valido(fv)
        else f'<div class="ss-nd">{TEXTO_ND}</div>',
        unsafe_allow_html=True,
    )
    if es_valido(fv) and p.get("moneda") == "USD":
        st.markdown(
            f'<div class="ss-precio-eur">{fmt_usd_eur(fv, fx).split(" / ")[-1] if es_valido(fx) else TEXTO_ND}</div>',
            unsafe_allow_html=True,
        )
    alerta = v.get("alerta", {})
    C.alerta(alerta.get("etiqueta", TEXTO_ND), alerta.get("color", "#94a3b8"))
    C.metrica("Potencial (upside)", fmt_pct(v.get("upside_pct")))
    if v.get("peso_consenso_doble"):
        st.caption("Peso doble aplicado al consenso: unanimidad y cobertura ≥ 10 analistas.")

    with st.expander("Desglose de la valoración"):
        for nombre, comp in v["componentes"].items():
            valor = comp["valor"]
            peso = v["pesos_aplicados"].get(_clave_peso(nombre))
            sufijo = f"  ·  peso {peso * 100:.0f} %" if peso else "  ·  excluido del cálculo"
            C.metrica(nombre, (fmt_num(valor) if es_valido(valor) else TEXTO_ND) + sufijo)
            for n in comp["detalle"].get("notas", []):
                st.caption(f"↳ {n}")
        C.metrica("Cobertura del modelo", fmt_pct(v.get("cobertura", 0) * 100, 0))

    with st.expander("Piotroski F-Score"):
        pio = q["piotroski"]
        C.metrica("Puntuación", f"{pio['puntos']} / {pio['evaluados']} criterios evaluables")
        for criterio, cumple in pio["criterios"].items():
            simbolo = "✔" if cumple else ("✘" if cumple is False else TEXTO_ND)
            C.metrica(criterio, simbolo)

    with st.expander("Métricas de calidad"):
        L = q["lecturas"]
        C.metrica("PER actual", fmt_num(L.get("per")))
        C.metrica("PER mediano del sector", fmt_num(L.get("per_sector")))
        C.metrica("PER medio 5 años", fmt_num(L.get("per_historico_5a")))
        C.metrica("Forward PER", fmt_num(L.get("forward_per")))
        C.metrica("Margen neto", fmt_pct(L.get("margen_neto"), 1, ya_en_pct=False))
        C.metrica("ROE", fmt_pct(L.get("roe"), 1, ya_en_pct=False))
        C.metrica("ROIC", fmt_pct(L.get("roic"), 1, ya_en_pct=False))
        C.metrica("PEG", fmt_num(L.get("peg")))
        C.metrica("CAGR ingresos", fmt_pct(L.get("cagr_ingresos"), 1, ya_en_pct=False))
        C.metrica("CAGR beneficios", fmt_pct(L.get("cagr_beneficios"), 1, ya_en_pct=False))
        C.metrica("Calidad del beneficio (FCF/BN)", fmt_num(L.get("fcf_sobre_beneficio")))
        if q["excluidos"]:
            st.caption("Excluidos por falta de dato: " + ", ".join(q["excluidos"]))


def _clave_peso(nombre: str) -> str:
    return {
        "DCF": "dcf",
        "Múltiplos": "multiplos",
        "DDM": "ddm",
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
            fmt_num(n["precio"]),
            fmt_pct(n["distancia_pct"]),
            n["motivos"],
        )

    st.markdown("**Niveles de salida**")
    for n in plan["salidas"]:
        C.nivel_plan(
            f"Salida {n['nivel']} · {n['peso_posicion'] * 100:.0f} % de la posición",
            fmt_num(n["precio"]),
            fmt_pct(n["distancia_pct"]),
            n["motivos"],
        )

    st.markdown("**Stop loss**")
    sl = plan["stop_loss"]
    C.nivel_plan("Stop loss", fmt_num(sl["precio"]), fmt_pct(sl["distancia_pct"]), [sl["base"]])

    C.metrica("Precio medio estimado", fmt_num(plan["precio_medio_estimado"]))
    C.metrica("Objetivo medio estimado", fmt_num(plan["objetivo_medio_estimado"]))
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
            help=f"El precio actual ({fmt_num(p.get('precio'))}) todavía no ha alcanzado "
            f"el nivel 1 de entrada ({fmt_num(nivel_1)}).",
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
