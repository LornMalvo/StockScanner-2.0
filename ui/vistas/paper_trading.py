"""Apartado "Paper Trading": seguimiento de los planes DCA guardados.

Un plan pasa por `core/paper_trading.py` (que a su vez delega en
`core/cartera.py`) para separar dos cifras que NO deben confundirse:

- **Proyectado**: lo que dice el plan tal como se diseñó (congelado en la
  cabecera al guardar), sin importar si se ha ejecutado nada.
- **Real**: lo que de verdad se ha ejecutado en la simulación, derivado del
  libro de eventos. Es lo único que gobierna el P&L.

DIVISA. Igual que en Cartera: el capital asignado está en euros, la
cotización llega en la divisa nativa del ticker. Cada ejecución guarda su
propio tipo de cambio histórico; `registrar_ejecucion()` exige que la
conversión sea posible ANTES de guardar, así que aquí solo hay que resolver
el tipo de cambio de HOY para sugerir acciones y para la vista general.
"""

from __future__ import annotations

from datetime import date

import streamlit as st

from config.settings import (
    C_ROJO,
    C_TEXTO_TENUE,
    C_VERDE,
    PAPER_ESTADOS,
    PAPER_ESTADOS_ACTIVOS,
    PAPER_ESTADOS_CERRADOS,
    PAPER_ESTADOS_DESCARTADOS,
    TEXTO_ND,
)
from core import alertas_telegram, bd_supabase, datos_api, paper_trading as pt
from ui import componentes as C
from utils.formato import es_valido, fmt_eur, fmt_fecha, fmt_num, fmt_pct


# ------------------------------------------------------------- utilidades ----
def _color(valor) -> str:
    if not es_valido(valor):
        return C_TEXTO_TENUE
    return C_VERDE if float(valor) >= 0 else C_ROJO


def _precio_fmt_nativo(valor, moneda: str | None) -> str:
    if not es_valido(valor):
        return TEXTO_ND
    return f"{fmt_num(valor)} {moneda or ''}".strip()


# ------------------------------------------------------------ carga de datos --
def _cargar() -> tuple[list[dict], dict, dict]:
    """(cabeceras, niveles por posición, ejecuciones por posición)."""
    posiciones = bd_supabase.listar_paper_trades()
    niveles = bd_supabase.niveles_por_posicion()
    ejecuciones = bd_supabase.ejecuciones_por_posicion()
    return posiciones, niveles, ejecuciones


def _resumenes(posiciones, niveles, ejecuciones, precios, fx) -> dict:
    salida = {}
    for pos in posiciones:
        pid = pos["id"]
        moneda = pos.get("divisa_cotizacion")
        precio_nativo = precios.get(pos["ticker"])
        r = pt.resumen_posicion(
            niveles.get(pid, []),
            ejecuciones.get(pid, []),
            moneda,
            precio_nativo,
            fx,
            pos.get("capital_asignado"),
            precio_medio_proyectado=pos.get("precio_medio_estimado"),
            objetivo_medio_proyectado=pos.get("objetivo_medio_estimado"),
        )
        r["precio_actual_nativo"] = precio_nativo
        salida[pid] = r
    return salida


def _notificar_si_toca_nivel1(pos: dict, niveles: list[dict], precio_nativo) -> None:
    if pos.get("estado") != "vigilancia" or pos.get("notificado_nivel1"):
        return
    if not es_valido(precio_nativo) or not alertas_telegram.disponible():
        return
    entrada1 = next((n for n in niveles if n.get("tipo") == "entrada" and n.get("nivel") == 1), None)
    if not entrada1 or not es_valido(entrada1.get("precio")):
        return
    if float(precio_nativo) <= float(entrada1["precio"]):
        if alertas_telegram.alerta_nivel_alcanzado(pos["ticker"], "Entrada", 1, float(precio_nativo)):
            bd_supabase.marcar_notificado_nivel1(pos["id"])


# ------------------------------------------------------------- agregados -----
def _cabecera(posiciones: list[dict], resumenes: dict) -> None:
    # El estado que manda es SIEMPRE el persistido en la cabecera, nunca el
    # derivado del resumen (que no puede distinguir 'descartada' — ver nota
    # en core/paper_trading.py). Filtrar por resumen[...]["estado_derivado"]
    # aquí contaría un plan descartado como "activo".
    activos = [resumenes[p["id"]] for p in posiciones if p["estado"] in PAPER_ESTADOS_ACTIVOS]
    capital_asignado = sum(r.get("capital_asignado") or 0 for r in activos)
    capital_ejecutado = sum(r.get("capital_ejecutado") or 0 for r in activos)
    latente = sum(r["latente"] for r in activos if es_valido(r.get("latente")))
    realizado = sum(r.get("realizado") or 0 for r in resumenes.values())

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Planes activos", str(len(activos)))
    c2.metric("Capital asignado", fmt_eur(capital_asignado))
    c3.metric("Capital ejecutado", fmt_eur(capital_ejecutado))
    c4.metric("P/L realizado (todo)", fmt_eur(realizado, signo=True))
    if latente:
        st.caption(f"P/L latente de los planes activos con precio disponible: {fmt_eur(latente, signo=True)}")


# -------------------------------------------------------------- ejecución ----
def _form_ejecutar_nivel(pos: dict, nivel: dict, resumen: dict) -> None:
    """Formulario para disparar un nivel de entrada o salida pendiente, con
    dos modos: al precio planificado del nivel, o al precio de mercado de
    hoy — registrados de forma distinta (`tipo_ejecucion`) para no mezclar
    ambas cosas al evaluar si el sistema funciona."""
    pid, moneda = pos["id"], pos.get("divisa_cotizacion")
    tipo = nivel["tipo"]  # 'entrada' | 'salida'
    clave = f"{tipo}_{nivel['id']}"

    with st.expander(f"Ejecutar {tipo} {nivel['nivel']} · {_precio_fmt_nativo(nivel['precio'], moneda)}"):
        modo = st.radio(
            "Precio de ejecución",
            ["Al nivel planificado", "A precio de mercado (hoy)"],
            key=f"modo_{clave}",
            horizontal=True,
        )
        tipo_ejecucion = "nivel" if modo == "Al nivel planificado" else "mercado"

        precio_mercado = None
        if tipo_ejecucion == "mercado":
            precio_mercado = datos_api.obtener_precio_actual(pos["ticker"])
            if not es_valido(precio_mercado):
                st.warning("No se ha podido obtener el precio de mercado actual. Inténtalo de nuevo.")
                return
        precio_ejecucion = float(precio_mercado) if tipo_ejecucion == "mercado" else float(nivel["precio"])

        fx = datos_api.obtener_fx_usd_eur()
        fx_fila = None if (moneda or "").upper() == "EUR" else fx
        if (moneda or "").upper() != "EUR" and not es_valido(fx):
            st.warning("No se ha podido obtener el tipo de cambio USD/EUR ahora mismo. Inténtalo de nuevo.")
            return

        if tipo == "entrada":
            sugeridas = pt.sugerir_acciones(
                pos.get("capital_asignado"), nivel.get("peso"), precio_ejecucion, moneda, fx
            )
        else:
            # Salida: por defecto se vende el % planificado de lo que hay vivo hoy.
            peso = nivel.get("peso") or 0
            sugeridas = (resumen["acciones"] or 0) * float(peso)

        with st.form(f"form_ejecutar_{clave}", clear_on_submit=True):
            c1, c2 = st.columns(2)
            acciones = c1.number_input(
                "Acciones",
                min_value=0.0,
                value=float(sugeridas) if es_valido(sugeridas) else 0.0,
                step=1.0,
                format="%.4f",
                key=f"acc_{clave}",
            )
            fecha = c2.date_input("Fecha", value=date.today(), key=f"fec_{clave}")
            st.caption(f"Precio de ejecución: {_precio_fmt_nativo(precio_ejecucion, moneda)}")
            enviar = st.form_submit_button("Confirmar ejecución", type="primary")

        if not enviar:
            return
        if acciones <= 0:
            st.warning("Las acciones deben ser mayores que cero.")
            return
        if tipo == "salida":
            error = pt.validar_venta_salida(resumen["ejecuciones"], moneda, acciones)
            if error:
                st.warning(error)
                return

        ok = bd_supabase.registrar_ejecucion(
            pid,
            pos["ticker"],
            tipo,
            tipo_ejecucion,
            acciones,
            precio_ejecucion,
            fecha,
            fx_fila,
            nivel_id=nivel["id"],
        )
        if ok:
            st.rerun()
        else:
            st.error("No se ha podido registrar la ejecución.")


def _form_cierre_manual(pos: dict, resumen: dict) -> None:
    pid, moneda = pos["id"], pos.get("divisa_cotizacion")
    with st.expander("Cerrar manualmente (p. ej. stop loss)"):
        precio_mercado = datos_api.obtener_precio_actual(pos["ticker"])
        fx = datos_api.obtener_fx_usd_eur()
        if (moneda or "").upper() != "EUR" and not es_valido(fx):
            st.warning("No se ha podido obtener el tipo de cambio USD/EUR ahora mismo. Inténtalo de nuevo.")
            return
        fx_fila = None if (moneda or "").upper() == "EUR" else fx

        with st.form(f"form_cierre_{pid}", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            acciones = c1.number_input(
                "Acciones a vender",
                min_value=0.0,
                max_value=float(resumen["acciones"]),
                value=float(resumen["acciones"]),
                step=1.0,
                format="%.4f",
            )
            precio = c2.number_input(
                "Precio",
                min_value=0.0,
                value=float(precio_mercado) if es_valido(precio_mercado) else 0.0,
                step=0.01,
                format="%.4f",
            )
            fecha = c3.date_input("Fecha", value=date.today())
            motivo = st.text_input("Motivo", value="Stop loss")
            enviar = st.form_submit_button("Confirmar cierre", type="primary")

        if not enviar:
            return
        error = pt.validar_venta_salida(resumen["ejecuciones"], moneda, acciones)
        if error:
            st.warning(error)
        elif precio <= 0:
            st.warning("El precio debe ser mayor que cero.")
        elif bd_supabase.cerrar_manual(pid, pos["ticker"], acciones, precio, fecha, fx_fila, motivo=motivo):
            st.rerun()
        else:
            st.error("No se ha podido registrar el cierre.")


# ------------------------------------------------------------- tarjeta -------
def _niveles_plan(pos: dict, niveles: list[dict], resumen: dict) -> None:
    moneda = pos.get("divisa_cotizacion")
    with st.expander("Plan y ejecución", expanded=pos["estado"] in ("vigilancia", "parcial_entrada")):
        for tipo, titulo in (("entrada", "Entradas"), ("salida", "Salidas")):
            st.markdown(f"**{titulo}**")
            for n in sorted((x for x in niveles if x["tipo"] == tipo), key=lambda x: x["nivel"]):
                bajo_medio = resumen.get("salidas_bajo_medio", {}).get(n["nivel"], False)
                etiqueta = f"{tipo.capitalize()} {n['nivel']}"
                if n.get("ejecutado"):
                    C.metrica(etiqueta, f"✔ ejecutado — {_precio_fmt_nativo(n['precio'], moneda)}")
                elif tipo == "salida" and bajo_medio:
                    C.metrica(
                        etiqueta,
                        f"{_precio_fmt_nativo(n['precio'], moneda)} (por debajo del precio medio real)",
                    )
                else:
                    C.metrica(etiqueta, _precio_fmt_nativo(n["precio"], moneda))
                if n.get("motivos"):
                    st.caption(f"↳ {n['motivos']}")
                if not n.get("ejecutado") and pos["estado"] not in ("cerrada", "descartada"):
                    _form_ejecutar_nivel(pos, n, resumen)

        stop = next((x for x in niveles if x["tipo"] == "stop"), None)
        if stop:
            C.metrica("Stop loss", _precio_fmt_nativo(stop["precio"], moneda))


def _tarjeta(pos: dict, niveles: list[dict], resumen: dict) -> None:
    estado = pos["estado"]
    etiqueta_estado, color_estado = PAPER_ESTADOS.get(estado, (estado, C_TEXTO_TENUE))

    with st.container(border=True):
        cab, met = st.columns([1.6, 2.6])

        with cab:
            st.markdown(f"### {pos['ticker']}")
            C.badge(etiqueta_estado, color_estado)
            st.caption(pos.get("veredicto") or TEXTO_ND)
            st.caption(f"Guardado el {fmt_fecha(pos.get('abierta_en'))}")
            progreso = resumen["progreso"]
            st.caption(
                f"{progreso['entradas_ejecutadas']}/{progreso['entradas_totales']} entradas · "
                f"{progreso['salidas_ejecutadas']}/{progreso['salidas_totales']} salidas"
            )

        with met:
            C.metrica(
                "Precio de referencia (diseño)",
                _precio_fmt_nativo(pos.get("precio_referencia"), pos.get("divisa_cotizacion")),
            )
            C.metrica(
                "Precio actual",
                _precio_fmt_nativo(resumen.get("precio_actual_nativo"), pos.get("divisa_cotizacion")),
            )
            C.metrica_nota(
                "Fair value / potencial (al diseñar)",
                _precio_fmt_nativo(pos.get("fair_value"), pos.get("divisa_cotizacion")),
                fmt_pct(pos.get("upside_pct")) if es_valido(pos.get("upside_pct")) else None,
            )
            st.caption("Precio medio — real (ejecutado) vs proyectado (si se llenara el plan):")
            C.metrica("Precio medio real (€)", fmt_eur(resumen["precio_medio"]))
            C.metrica(
                "Precio medio proyectado (€, informativo)",
                _precio_fmt_nativo(resumen.get("precio_medio_proyectado"), pos.get("divisa_cotizacion")),
            )
            C.metrica(
                "Capital",
                f"{fmt_eur(resumen['capital_ejecutado'])} ejecutado de "
                f"{fmt_eur(resumen['capital_asignado'])} "
                f"({fmt_eur(resumen['capital_pendiente'])} pendiente)"
                if es_valido(resumen["capital_asignado"])
                else TEXTO_ND,
            )
            if resumen["acciones"] > 0:
                C.metrica_distancia(
                    "P/L latente",
                    fmt_eur(resumen["latente"], signo=True),
                    fmt_pct(resumen["latente_pct"]),
                    _color(resumen["latente"]),
                )
            if abs(resumen["realizado"]) > 0.005:
                C.metrica_color(
                    "P/L realizado", fmt_eur(resumen["realizado"], signo=True), _color(resumen["realizado"])
                )

        for aviso in resumen["avisos"]:
            st.warning(aviso)

        acciones_fila = st.columns(3)
        if estado == "vigilancia":
            if acciones_fila[0].button("Descartar plan", key=f"descartar_{pos['id']}"):
                if bd_supabase.descartar_plan(pos["id"]):
                    st.rerun()
                else:
                    st.error("No se ha podido descartar (¿ya tiene ejecuciones?).")
        if estado in ("cerrada", "descartada"):
            if acciones_fila[0].button("Eliminar plan", key=f"eliminar_{pos['id']}"):
                if bd_supabase.eliminar_plan(pos["id"]):
                    st.rerun()
                else:
                    st.error("No se ha podido eliminar el plan.")

        if estado not in ("cerrada", "descartada"):
            _niveles_plan(pos, niveles, resumen)
            if resumen["acciones"] > 0:
                _form_cierre_manual(pos, resumen)
        else:
            with st.expander("Plan (histórico)"):
                for n in sorted(niveles, key=lambda x: (x["tipo"], x["nivel"])):
                    marca = "✔" if n.get("ejecutado") else "—"
                    C.metrica(
                        f"{n['tipo'].capitalize()} {n['nivel']} {marca}",
                        _precio_fmt_nativo(n["precio"], pos.get("divisa_cotizacion")),
                    )
                if pos.get("motivo_cierre"):
                    st.caption(f"Cierre: {pos['motivo_cierre']} el {fmt_fecha(pos.get('cerrada_en'))}")


# ------------------------------------------------------------------ render ---
def render() -> None:
    st.markdown("#### Paper Trading")

    if not bd_supabase.hay_conexion():
        st.warning("Sin conexión con Supabase: las posiciones simuladas no se pueden recuperar.")
        return

    posiciones, niveles, ejecuciones = _cargar()
    if not posiciones:
        st.info(
            "No hay planes guardados. Guarda un plan DCA desde el Análisis Individual "
            "(botón «Guardar plan en Paper Trading»)."
        )
        return

    tickers = [p["ticker"] for p in posiciones if p["estado"] in PAPER_ESTADOS_ACTIVOS]
    precios = datos_api.obtener_precios_lote(tickers) if tickers else {}
    fx = datos_api.obtener_fx_usd_eur()

    resumenes = _resumenes(posiciones, niveles, ejecuciones, precios, fx)

    # Aviso único de "ya toca Entrada 1" para planes en vigilancia.
    for pos in posiciones:
        if pos["estado"] == "vigilancia":
            _notificar_si_toca_nivel1(pos, niveles.get(pos["id"], []), precios.get(pos["ticker"]))

    _cabecera(posiciones, resumenes)
    st.divider()

    activos = [p for p in posiciones if p["estado"] in PAPER_ESTADOS_ACTIVOS]
    cerrados = [p for p in posiciones if p["estado"] in PAPER_ESTADOS_CERRADOS]
    descartados = [p for p in posiciones if p["estado"] in PAPER_ESTADOS_DESCARTADOS]

    t_activos, t_cerrados, t_descartados = st.tabs(
        [f"Activos ({len(activos)})", f"Cerrados ({len(cerrados)})", f"Descartados ({len(descartados)})"]
    )
    with t_activos:
        if not activos:
            st.info("No hay planes activos.")
        for pos in activos:
            _tarjeta(pos, niveles.get(pos["id"], []), resumenes[pos["id"]])
    with t_cerrados:
        if not cerrados:
            st.info("Todavía no se ha cerrado ningún plan.")
        for pos in cerrados:
            _tarjeta(pos, niveles.get(pos["id"], []), resumenes[pos["id"]])
    with t_descartados:
        if not descartados:
            st.info("No hay planes descartados.")
        for pos in descartados:
            _tarjeta(pos, niveles.get(pos["id"], []), resumenes[pos["id"]])
