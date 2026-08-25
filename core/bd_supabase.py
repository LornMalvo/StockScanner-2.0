"""Persistencia en Supabase.

La app funciona sin base de datos (modo consulta): si faltan las credenciales,
`cliente()` devuelve None y cada función lo comunica en la interfaz en vez de
romper. El esquema SQL está en sql/schema.sql.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import streamlit as st

from config.settings import CARTERA_DIVISA_BASE

try:
    from supabase import Client, create_client
except ImportError:  # la librería es opcional en desarrollo local
    Client = None  # type: ignore
    create_client = None  # type: ignore


T_FAVORITOS = "favoritos"
T_ANALISIS = "analisis_historico"
T_CARTERA = "cartera_posiciones"
T_CARTERA_OPS = "cartera_operaciones"
T_PAPER = "paper_trading_posiciones"
T_NIVELES = "paper_trading_niveles"
T_EJECUCIONES = "paper_trading_ejecuciones"
T_TRADUCCIONES = "descripciones_traducidas"
T_CACHE_API = "cache_api"
T_DCA_OVERRIDES = "dca_overrides"

USUARIO_DEFECTO = "local"


@st.cache_resource(show_spinner=False)
def cliente():
    """Cliente Supabase reutilizado entre reruns. None si no hay credenciales."""
    if create_client is None:
        return None
    try:
        url = st.secrets.get("SUPABASE_URL")
        key = st.secrets.get("SUPABASE_KEY")
    except Exception:
        return None
    if not url or not key:
        return None
    try:
        return create_client(str(url), str(key))
    except Exception:
        return None


def hay_conexion() -> bool:
    return cliente() is not None


def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat()


def _usuario() -> str:
    return st.session_state.get("usuario_id", USUARIO_DEFECTO)


# ------------------------------------------------------------- favoritos ----
def listar_favoritos() -> list[dict]:
    sb = cliente()
    if sb is None:
        return []
    try:
        r = (
            sb.table(T_FAVORITOS)
            .select("*")
            .eq("usuario_id", _usuario())
            .order("creado_en", desc=True)
            .execute()
        )
        return r.data or []
    except Exception:
        return []


def es_favorito(ticker: str) -> bool:
    return any(f.get("ticker") == ticker.upper() for f in listar_favoritos())


def alternar_favorito(ticker: str, nombre: str | None = None, sector: str | None = None) -> bool:
    """Añade o elimina el ticker de favoritos. Devuelve el estado resultante."""
    sb = cliente()
    if sb is None:
        return False
    ticker = ticker.upper()
    try:
        if es_favorito(ticker):
            sb.table(T_FAVORITOS).delete().eq("usuario_id", _usuario()).eq(
                "ticker", ticker
            ).execute()
            estado = False
        else:
            sb.table(T_FAVORITOS).insert(
                {
                    "usuario_id": _usuario(),
                    "ticker": ticker,
                    "nombre": nombre,
                    "sector": sector,
                    "creado_en": _ahora(),
                }
            ).execute()
            estado = True
    except Exception:
        return es_favorito(ticker)
    return estado


# ------------------------------------------------- histórico de análisis ----
def guardar_analisis(ticker: str, resumen: dict) -> bool:
    sb = cliente()
    if sb is None:
        return False
    try:
        sb.table(T_ANALISIS).insert(
            {
                "usuario_id": _usuario(),
                "ticker": ticker.upper(),
                "precio": resumen.get("precio"),
                "fair_value": resumen.get("fair_value"),
                "upside_pct": resumen.get("upside_pct"),
                "puntuacion_calidad": resumen.get("puntuacion_calidad"),
                "puntuacion_timing": resumen.get("puntuacion_timing"),
                "senal_timing": resumen.get("senal_timing"),
                "veredicto": resumen.get("veredicto"),
                "payload": resumen.get("payload"),
                "creado_en": _ahora(),
            }
        ).execute()
        return True
    except Exception:
        return False


def historico_analisis(ticker: str, limite: int = 30) -> list[dict]:
    sb = cliente()
    if sb is None:
        return []
    try:
        r = (
            sb.table(T_ANALISIS)
            .select("*")
            .eq("usuario_id", _usuario())
            .eq("ticker", ticker.upper())
            .order("creado_en", desc=True)
            .limit(limite)
            .execute()
        )
        return r.data or []
    except Exception:
        return []


# ---------------------------------------------------------------- cartera ----
# Modelo de libro de operaciones. `cartera_posiciones` es solo la CABECERA de
# una operación completa (un "trade"): identidad, divisas y ciclo de vida.
# Ninguna cifra se almacena ahí: acciones vivas, precio medio y P&L se derivan
# de `cartera_operaciones` en `core/cartera.py`. El único campo denormalizado
# es `estado`, que no es una métrica sino un marcador de ciclo de vida escrito
# por el mismo código que inserta la operación que lo provoca (y que permite
# filtrar posiciones abiertas sin leer el libro entero).
def listar_cartera(estado: str | None = None) -> list[dict]:
    """Cabeceras de posición. `estado=None` devuelve abiertas y cerradas."""
    sb = cliente()
    if sb is None:
        return []
    try:
        q = sb.table(T_CARTERA).select("*").eq("usuario_id", _usuario())
        if estado:
            q = q.eq("estado", estado)
        return q.order("abierta_en", desc=True).execute().data or []
    except Exception:
        return []


def posicion_abierta(ticker: str) -> dict | None:
    """Cabecera abierta del ticker, si la hay. Una compra sobre un ticker sin
    posición abierta arranca una posición NUEVA: así la rentabilidad por
    operación no mezcla dos trades independientes separados en el tiempo."""
    sb = cliente()
    if sb is None:
        return None
    try:
        r = (
            sb.table(T_CARTERA)
            .select("*")
            .eq("usuario_id", _usuario())
            .eq("ticker", ticker.upper())
            .eq("estado", "abierta")
            .limit(1)
            .execute()
        )
        filas = r.data or []
        return filas[0] if filas else None
    except Exception:
        return None


def listar_operaciones(posicion_id=None) -> list[dict]:
    """Libro de operaciones. Sin `posicion_id`, TODAS las del usuario en una
    sola petición: la vista de cartera las agrupa después en memoria, que sale
    mucho más barato que una consulta por posición."""
    sb = cliente()
    if sb is None:
        return []
    try:
        q = sb.table(T_CARTERA_OPS).select("*").eq("usuario_id", _usuario())
        if posicion_id is not None:
            q = q.eq("posicion_id", posicion_id)
        return q.order("fecha").order("id").execute().data or []
    except Exception:
        return []


def operaciones_por_posicion() -> dict:
    """Libro completo indexado por `posicion_id` (una sola petición)."""
    agrupadas: dict = {}
    for op in listar_operaciones():
        agrupadas.setdefault(op.get("posicion_id"), []).append(op)
    return agrupadas


def registrar_compra(
    ticker: str,
    acciones: float,
    precio: float,
    fecha,
    comisiones: float = 0.0,
    notas: str | None = None,
    nombre: str | None = None,
    divisa_cotizacion: str | None = None,
) -> bool:
    """Añade una compra, abriendo la posición si el ticker no tiene una viva."""
    sb = cliente()
    if sb is None:
        return False
    ticker = ticker.upper()
    try:
        cabecera = posicion_abierta(ticker)
        if cabecera is None:
            creada = (
                sb.table(T_CARTERA)
                .insert(
                    {
                        "usuario_id": _usuario(),
                        "ticker": ticker,
                        "nombre": nombre,
                        "divisa": CARTERA_DIVISA_BASE,
                        "divisa_cotizacion": divisa_cotizacion,
                        "estado": "abierta",
                        "abierta_en": str(fecha),
                        "creado_en": _ahora(),
                    }
                )
                .execute()
            )
            cabecera = (creada.data or [{}])[0]
        posicion_id = cabecera.get("id")
        if not posicion_id:
            return False

        # Si la cabecera existía sin divisa de cotización resuelta y ahora sí
        # la tenemos, se aprovecha para completarla.
        if divisa_cotizacion and not cabecera.get("divisa_cotizacion"):
            actualizar_divisa_cotizacion(posicion_id, divisa_cotizacion)

        sb.table(T_CARTERA_OPS).insert(
            {
                "usuario_id": _usuario(),
                "posicion_id": posicion_id,
                "ticker": ticker,
                "tipo": "compra",
                "acciones": float(acciones),
                "precio": float(precio),
                "comisiones": float(comisiones or 0),
                "fecha": str(fecha),
                "notas": notas,
                "creado_en": _ahora(),
            }
        ).execute()
        return True
    except Exception:
        return False


def registrar_venta(
    posicion_id,
    ticker: str,
    acciones: float,
    precio: float,
    fecha,
    comisiones: float = 0.0,
    notas: str | None = None,
) -> bool:
    """Añade una venta y cierra la cabecera si deja la posición a cero.

    La comprobación de sobreventa se hace ANTES, en la interfaz, con
    `core/cartera.py::validar_venta()`; aquí solo se persiste.
    """
    sb = cliente()
    if sb is None:
        return False
    try:
        sb.table(T_CARTERA_OPS).insert(
            {
                "usuario_id": _usuario(),
                "posicion_id": posicion_id,
                "ticker": ticker.upper(),
                "tipo": "venta",
                "acciones": float(acciones),
                "precio": float(precio),
                "comisiones": float(comisiones or 0),
                "fecha": str(fecha),
                "notas": notas,
                "creado_en": _ahora(),
            }
        ).execute()
        sincronizar_estado(posicion_id, fecha_cierre=fecha)
        return True
    except Exception:
        return False


def sincronizar_estado(posicion_id, fecha_cierre=None) -> None:
    """Recalcula `estado` a partir del libro y lo escribe si ha cambiado.

    Se llama tras cada venta y tras borrar una operación: borrar la venta que
    cerró una posición tiene que volver a abrirla, o la cabecera mentiría.
    """
    from core import cartera as _cartera  # import local: evita ciclo al importar

    sb = cliente()
    if sb is None:
        return
    try:
        resumen = _cartera.resumen_posicion(listar_operaciones(posicion_id))
        cerrada = resumen["acciones"] <= 0
        sb.table(T_CARTERA).update(
            {
                "estado": "cerrada" if cerrada else "abierta",
                "cerrada_en": (str(fecha_cierre) if cerrada and fecha_cierre else None),
            }
        ).eq("id", posicion_id).execute()
    except Exception:
        return


def eliminar_operacion(operacion_id, posicion_id) -> bool:
    """Borra una operación del libro (corrección de errores de registro).

    Si la posición se queda sin operaciones, se borra también la cabecera:
    una posición vacía no es información, es basura.
    """
    sb = cliente()
    if sb is None:
        return False
    try:
        sb.table(T_CARTERA_OPS).delete().eq("id", operacion_id).execute()
        if not listar_operaciones(posicion_id):
            sb.table(T_CARTERA).delete().eq("id", posicion_id).execute()
        else:
            sincronizar_estado(posicion_id)
        return True
    except Exception:
        return False


def eliminar_posicion(posicion_id) -> bool:
    """Borra la posición entera con su libro (cascade en el esquema)."""
    sb = cliente()
    if sb is None:
        return False
    try:
        sb.table(T_CARTERA).delete().eq("id", posicion_id).execute()
        return True
    except Exception:
        return False


def actualizar_divisa_cotizacion(posicion_id, divisa: str) -> bool:
    sb = cliente()
    if sb is None:
        return False
    try:
        sb.table(T_CARTERA).update({"divisa_cotizacion": divisa.upper()}).eq(
            "id", posicion_id
        ).execute()
        return True
    except Exception:
        return False


# --------------------------------------------------------- paper trading ----
# Modelo: `paper_trading_niveles` es el PLAN (estático, congelado al
# guardar). `paper_trading_ejecuciones` es el LIBRO DE EVENTOS reales — igual
# que `cartera_operaciones` para la cartera real. `core/paper_trading.py`
# combina ambos; aquí solo hay CRUD y la sincronización del campo `estado`
# denormalizado en la cabecera.
def listar_paper_trades(estado: str | None = None) -> list[dict]:
    """Cabeceras de plan. `estado=None` devuelve todas."""
    sb = cliente()
    if sb is None:
        return []
    try:
        q = sb.table(T_PAPER).select("*").eq("usuario_id", _usuario())
        if estado:
            q = q.eq("estado", estado)
        return q.order("abierta_en", desc=True).execute().data or []
    except Exception:
        return []


def plan_activo(ticker: str) -> dict | None:
    """Plan no terminado (ni cerrado ni descartado) para ese ticker, si lo
    hay. Evita guardar dos planes simulados vivos a la vez sobre el mismo
    valor, que confundiría el seguimiento."""
    sb = cliente()
    if sb is None:
        return None
    try:
        r = (
            sb.table(T_PAPER)
            .select("*")
            .eq("usuario_id", _usuario())
            .eq("ticker", ticker.upper())
            .not_.in_("estado", ["cerrada", "descartada"])
            .limit(1)
            .execute()
        )
        filas = r.data or []
        return filas[0] if filas else None
    except Exception:
        return None


def niveles_por_posicion() -> dict:
    """Todos los niveles del usuario, agrupados por `posicion_id` (1 petición)."""
    sb = cliente()
    if sb is None:
        return {}
    try:
        filas = (
            sb.table(T_NIVELES)
            .select("*")
            .eq("usuario_id", _usuario())
            .order("tipo")
            .order("nivel")
            .execute()
            .data
            or []
        )
    except Exception:
        return {}
    agrupadas: dict = {}
    for n in filas:
        agrupadas.setdefault(n.get("posicion_id"), []).append(n)
    return agrupadas


def listar_niveles(posicion_id) -> list[dict]:
    sb = cliente()
    if sb is None:
        return []
    try:
        return (
            sb.table(T_NIVELES)
            .select("*")
            .eq("posicion_id", posicion_id)
            .order("tipo")
            .order("nivel")
            .execute()
            .data
            or []
        )
    except Exception:
        return []


def ejecuciones_por_posicion() -> dict:
    """Todas las ejecuciones del usuario, agrupadas por `posicion_id`."""
    sb = cliente()
    if sb is None:
        return {}
    try:
        filas = (
            sb.table(T_EJECUCIONES)
            .select("*")
            .eq("usuario_id", _usuario())
            .order("fecha")
            .order("id")
            .execute()
            .data
            or []
        )
    except Exception:
        return {}
    agrupadas: dict = {}
    for e in filas:
        agrupadas.setdefault(e.get("posicion_id"), []).append(e)
    return agrupadas


def listar_ejecuciones(posicion_id) -> list[dict]:
    sb = cliente()
    if sb is None:
        return []
    try:
        return (
            sb.table(T_EJECUCIONES)
            .select("*")
            .eq("posicion_id", posicion_id)
            .order("fecha")
            .order("id")
            .execute()
            .data
            or []
        )
    except Exception:
        return []


def guardar_plan_paper_trading(ticker: str, plan: dict, contexto: dict, capital_asignado: float) -> int | None:
    """Congela el plan DCA como posición en seguimiento (`estado='vigilancia'`).

    `contexto` trae la foto del análisis en el momento de guardar: `moneda`
    (para poder convertir ejecuciones futuras a EUR), `fair_value`,
    `upside_pct`, `puntuacion_calidad`, `puntuacion_timing`, `veredicto`.
    Devuelve el id de la posición creada, o None si falla.
    """
    sb = cliente()
    if sb is None:
        return None
    ticker = ticker.upper()
    try:
        creada = (
            sb.table(T_PAPER)
            .insert(
                {
                    "usuario_id": _usuario(),
                    "ticker": ticker,
                    "estado": "vigilancia",
                    "precio_referencia": plan.get("precio_referencia"),
                    "fair_value": contexto.get("fair_value"),
                    "upside_pct": contexto.get("upside_pct"),
                    "capital_asignado": float(capital_asignado),
                    "divisa_cotizacion": contexto.get("moneda"),
                    "precio_medio_estimado": plan.get("precio_medio_estimado"),
                    "objetivo_medio_estimado": plan.get("objetivo_medio_estimado"),
                    "stop_loss": (plan.get("stop_loss") or {}).get("precio"),
                    "puntuacion_calidad": contexto.get("puntuacion_calidad"),
                    "puntuacion_timing": contexto.get("puntuacion_timing"),
                    "veredicto": contexto.get("veredicto"),
                    "abierta_en": _ahora(),
                }
            )
            .execute()
        )
        posicion_id = (creada.data or [{}])[0].get("id")
        if not posicion_id:
            return None

        niveles = [
            {
                "usuario_id": _usuario(),
                "posicion_id": posicion_id,
                "tipo": "entrada",
                "nivel": n["nivel"],
                "precio": n["precio"],
                "peso": n["peso_capital"],
                "ejecutado": False,
                "motivos": ", ".join(n["motivos"]),
            }
            for n in plan.get("entradas", [])
        ] + [
            {
                "usuario_id": _usuario(),
                "posicion_id": posicion_id,
                "tipo": "salida",
                "nivel": n["nivel"],
                "precio": n["precio"],
                "peso": n["peso_posicion"],
                "ejecutado": False,
                "motivos": ", ".join(n["motivos"]),
            }
            for n in plan.get("salidas", [])
        ]
        stop = plan.get("stop_loss") or {}
        if stop.get("precio") is not None:
            niveles.append(
                {
                    "usuario_id": _usuario(),
                    "posicion_id": posicion_id,
                    "tipo": "stop",
                    "nivel": 1,
                    "precio": stop["precio"],
                    "peso": None,
                    "ejecutado": False,
                    "motivos": stop.get("base"),
                }
            )
        if niveles:
            sb.table(T_NIVELES).insert(niveles).execute()
        return posicion_id
    except Exception:
        return None


def registrar_ejecucion(
    posicion_id,
    ticker: str,
    tipo: str,
    tipo_ejecucion: str,
    acciones: float,
    precio: float,
    fecha,
    fx_usd_eur,
    nivel_id=None,
    notas: str | None = None,
) -> bool:
    """Añade un evento real al libro (una entrada o una salida ejecutada).

    `fx_usd_eur` debe llegar ya resuelto (o None si la divisa es EUR): la
    interfaz es quien decide si hay tipo de cambio antes de llamar aquí, para
    no guardar nunca una ejecución que después no se pueda convertir a euros.
    """
    sb = cliente()
    if sb is None:
        return False
    try:
        sb.table(T_EJECUCIONES).insert(
            {
                "usuario_id": _usuario(),
                "posicion_id": posicion_id,
                "nivel_id": nivel_id,
                "ticker": ticker.upper(),
                "tipo": tipo,
                "tipo_ejecucion": tipo_ejecucion,
                "acciones": float(acciones),
                "precio": float(precio),
                "fx_usd_eur": fx_usd_eur,
                "fecha": str(fecha),
                "notas": notas,
                "creado_en": _ahora(),
            }
        ).execute()
        if nivel_id is not None:
            sb.table(T_NIVELES).update(
                {"ejecutado": True, "ejecutado_en": _ahora()}
            ).eq("id", nivel_id).execute()
        sincronizar_estado_paper(posicion_id)
        return True
    except Exception:
        return False


def cerrar_manual(
    posicion_id, ticker: str, acciones: float, precio: float, fecha, fx_usd_eur, motivo: str = "Cierre manual"
) -> bool:
    """Vende sin pasar por un nivel de salida planificado (p. ej. stop loss
    saltado, o decisión de cerrar antes de tiempo)."""
    return registrar_ejecucion(
        posicion_id,
        ticker,
        "salida",
        "mercado",
        acciones,
        precio,
        fecha,
        fx_usd_eur,
        nivel_id=None,
        notas=motivo,
    )


def eliminar_ejecucion(ejecucion_id, posicion_id, nivel_id=None) -> bool:
    """Corrige un registro erróneo. Si era la única ejecución de su nivel,
    el nivel vuelve a quedar pendiente."""
    sb = cliente()
    if sb is None:
        return False
    try:
        sb.table(T_EJECUCIONES).delete().eq("id", ejecucion_id).execute()
        if nivel_id is not None:
            quedan = (
                sb.table(T_EJECUCIONES)
                .select("id")
                .eq("nivel_id", nivel_id)
                .limit(1)
                .execute()
                .data
            )
            if not quedan:
                sb.table(T_NIVELES).update({"ejecutado": False, "ejecutado_en": None}).eq(
                    "id", nivel_id
                ).execute()
        sincronizar_estado_paper(posicion_id)
        return True
    except Exception:
        return False


def sincronizar_estado_paper(posicion_id) -> None:
    """Recalcula `estado` (y, si cierra, `cerrada_en`/`precio_cierre`/
    `motivo_cierre`) a partir del libro de niveles + ejecuciones."""
    from core import cartera as _cartera
    from core import paper_trading as _pt

    sb = cliente()
    if sb is None:
        return
    try:
        niveles = listar_niveles(posicion_id)
        ejecuciones = listar_ejecuciones(posicion_id)
        entradas = [n for n in niveles if n.get("tipo") == "entrada"]
        n_ent_ej = sum(1 for n in entradas if n.get("ejecutado"))

        # Conteo de acciones vivas: no depende de la divisa (una acción es
        # una acción), así que se usa el precio nativo tal cual, sin
        # necesidad de convertir a euros solo para esta comprobación.
        operaciones_nativas = [
            {
                "id": e.get("id"),
                "tipo": "compra" if e.get("tipo") == "entrada" else "venta",
                "acciones": e.get("acciones"),
                "precio": e.get("precio"),
                "comisiones": 0.0,
                "fecha": e.get("fecha"),
            }
            for e in ejecuciones
        ]
        acciones_vivas = _cartera.resumen_posicion(operaciones_nativas)["acciones"]
        hubo = bool(ejecuciones)
        hubo_venta = any(e.get("tipo") == "salida" for e in ejecuciones)
        estado = _pt.derivar_estado(len(entradas), n_ent_ej, hubo_venta, acciones_vivas, hubo)

        actualizacion = {"estado": estado}
        if estado == "cerrada":
            ultima = ejecuciones[-1] if ejecuciones else {}
            actualizacion["cerrada_en"] = ultima.get("fecha")
            actualizacion["precio_cierre"] = ultima.get("precio")
            actualizacion["motivo_cierre"] = ultima.get("notas") or (
                "Plan completado" if ultima.get("nivel_id") else "Cierre manual"
            )
        else:
            actualizacion["cerrada_en"] = None
            actualizacion["precio_cierre"] = None
            actualizacion["motivo_cierre"] = None

        sb.table(T_PAPER).update(actualizacion).eq("id", posicion_id).execute()
    except Exception:
        return


def descartar_plan(posicion_id) -> bool:
    """Solo válido desde `vigilancia` (nada ejecutado todavía). No se
    comprueba aquí de forma estricta más allá de confiar en que la interfaz
    solo ofrece este botón cuando el estado lo permite; como defensa mínima,
    se rechaza si ya hay ejecuciones registradas."""
    sb = cliente()
    if sb is None:
        return False
    try:
        if listar_ejecuciones(posicion_id):
            return False
        sb.table(T_PAPER).update({"estado": "descartada"}).eq("id", posicion_id).execute()
        return True
    except Exception:
        return False


def eliminar_plan(posicion_id) -> bool:
    sb = cliente()
    if sb is None:
        return False
    try:
        sb.table(T_PAPER).delete().eq("id", posicion_id).execute()
        return True
    except Exception:
        return False


def actualizar_capital_asignado(posicion_id, capital: float) -> bool:
    sb = cliente()
    if sb is None:
        return False
    try:
        sb.table(T_PAPER).update({"capital_asignado": float(capital)}).eq("id", posicion_id).execute()
        return True
    except Exception:
        return False


def marcar_notificado_nivel1(posicion_id) -> bool:
    sb = cliente()
    if sb is None:
        return False
    try:
        sb.table(T_PAPER).update({"notificado_nivel1": True}).eq("id", posicion_id).execute()
        return True
    except Exception:
        return False


# ----------------------------------------------- descripciones traducidas --
def obtener_descripcion_traducida(ticker: str, hash_original: str) -> str | None:
    """Devuelve la traducción cacheada si existe Y el texto en inglés no ha
    cambiado desde que se tradujo (comparando `hash_original`). Si yfinance
    actualiza la descripción, el hash difiere y se trata como caché vacía
    para forzar una traducción nueva en vez de servir una obsoleta."""
    sb = cliente()
    if sb is None:
        return None
    try:
        r = sb.table(T_TRADUCCIONES).select("texto_traducido, hash_original").eq(
            "ticker", ticker.upper()
        ).limit(1).execute()
        filas = r.data or []
        if not filas or filas[0].get("hash_original") != hash_original:
            return None
        return filas[0].get("texto_traducido")
    except Exception:
        return None


def guardar_descripcion_traducida(
    ticker: str, hash_original: str, texto_original: str, texto_traducido: str
) -> bool:
    sb = cliente()
    if sb is None:
        return False
    try:
        sb.table(T_TRADUCCIONES).upsert(
            {
                "ticker": ticker.upper(),
                "hash_original": hash_original,
                "texto_original": texto_original,
                "texto_traducido": texto_traducido,
                "traducido_en": _ahora(),
            },
            on_conflict="ticker",
        ).execute()
        return True
    except Exception:
        return False


# --------------------------------------------------- override manual (DCA) --
# Selección manual de niveles del Plan DCA (Análisis Individual). Se guarda
# como SNAPSHOT (precio, peso, motivos en el momento de elegir), no como
# referencia a una zona: el motor recalcula las zonas en cada análisis, así
# que un índice o ID no significaría nada la próxima vez que se abra el
# ticker. El override queda fijo hasta que el usuario lo cambie o lo borre.
def obtener_override_dca(ticker: str) -> dict:
    """Devuelve `{"entradas": [...], "salidas": [...]}` con los niveles
    guardados, cada lista ordenada por `nivel` y ya en el formato que espera
    `core.plan_dca.construir_plan(..., override=...)`. Listas vacías si no
    hay override guardado o no hay conexión."""
    sb = cliente()
    resultado = {"entradas": [], "salidas": []}
    if sb is None:
        return resultado
    try:
        filas = (
            sb.table(T_DCA_OVERRIDES)
            .select("*")
            .eq("usuario_id", _usuario())
            .eq("ticker", ticker.upper())
            .order("nivel")
            .execute()
            .data
            or []
        )
    except Exception:
        return resultado
    for f in filas:
        clave = "entradas" if f.get("tipo") == "entrada" else "salidas"
        resultado[clave].append(
            {
                "precio": f.get("precio"),
                "peso": f.get("peso"),
                "motivos": (f.get("motivos") or "").split(" · ") if f.get("motivos") else [],
            }
        )
    return resultado


def guardar_override_dca(ticker: str, tipo: str, niveles: list[dict]) -> bool:
    """Sustituye por completo los niveles guardados de un lado (`tipo` =
    'entrada' o 'salida') por `niveles`, una lista de hasta 3 zonas en orden
    de nivel (cada una con `precio`, `peso`, `motivos`). Borra primero el lado
    para no dejar niveles antiguos "huérfanos" si el usuario pasa de 3
    selecciones a 2."""
    sb = cliente()
    if sb is None:
        return False
    ticker = ticker.upper()
    try:
        sb.table(T_DCA_OVERRIDES).delete().eq("usuario_id", _usuario()).eq(
            "ticker", ticker
        ).eq("tipo", tipo).execute()
        if niveles:
            sb.table(T_DCA_OVERRIDES).insert(
                [
                    {
                        "usuario_id": _usuario(),
                        "ticker": ticker,
                        "tipo": tipo,
                        "nivel": i + 1,
                        "precio": float(z["precio"]),
                        "peso": z.get("peso"),
                        "motivos": " · ".join(z.get("motivos") or []) or None,
                        "actualizado_en": _ahora(),
                    }
                    for i, z in enumerate(niveles[:3])
                ]
            ).execute()
        return True
    except Exception:
        return False


def borrar_override_dca(ticker: str, tipo: str | None = None) -> bool:
    """Vuelve al cálculo automático. Sin `tipo`, borra ambos lados."""
    sb = cliente()
    if sb is None:
        return False
    try:
        q = sb.table(T_DCA_OVERRIDES).delete().eq("usuario_id", _usuario()).eq(
            "ticker", ticker.upper()
        )
        if tipo:
            q = q.eq("tipo", tipo)
        q.execute()
        return True
    except Exception:
        return False


# --------------------------------------------------- caché L2 genérica (API) --
# Respaldo persistente para lo que casi nunca cambia (estados financieros,
# perfil de Finnhub, CIK de SEC). La caché en memoria (`_almacen()` /
# `st.cache_data` en datos_api.py) es L1: rápida, pero se vacía entera cada
# vez que Streamlit Community Cloud reinicia el contenedor por inactividad.
# Esta tabla es L2: sobrevive a ese reinicio, así que el primer análisis del
# día no vuelve a pagar el peor caso completo de peticiones. No sustituye a
# L1 (que sigue siendo más rápida en caliente), solo la respalda cuando el
# proceso se reinicia. Sin usuario_id: estos datos no dependen de quién
# pregunta, son los mismos para todos.
#
# `valor` se guarda como JSON (columna jsonb). Estructuras que no son
# directamente serializables (p. ej. DataFrames de pandas) se convierten
# antes de llamar a `cache_l2_guardar` — ver `_estados_a_json()` en
# datos_api.py para el caso de los estados financieros.
def cache_l2_leer(clave: str, ttl_segundos: float):
    """Devuelve el valor cacheado si existe y no ha superado `ttl_segundos`.

    None si no hay conexión, no hay entrada, o la entrada ha caducado.
    """
    sb = cliente()
    if sb is None:
        return None
    try:
        r = (
            sb.table(T_CACHE_API)
            .select("valor, guardado_en")
            .eq("clave", clave)
            .limit(1)
            .execute()
        )
        filas = r.data or []
        if not filas:
            return None
        marca = filas[0].get("guardado_en")
        if not marca:
            return None
        guardado = datetime.fromisoformat(str(marca).replace("Z", "+00:00"))
        edad = (datetime.now(timezone.utc) - guardado).total_seconds()
        if edad > ttl_segundos:
            return None
        # El cliente de Supabase ya deserializa la columna jsonb a
        # dict/list/etc. Si por lo que sea llega como texto (driver o
        # versión distintos), se intenta parsear; si no, se devuelve tal
        # cual para no romper con un error de tipo silencioso.
        valor = filas[0].get("valor")
        if isinstance(valor, str):
            try:
                return json.loads(valor)
            except Exception:
                return valor
        return valor
    except Exception:
        return None


def cache_l2_guardar(clave: str, valor) -> bool:
    """Guarda (o sobrescribe) el valor bajo `clave`. `valor` debe ser
    JSON-serializable (dict, list, str, número, None, o combinaciones).

    Se pasa el objeto Python tal cual (no `json.dumps` manual): el propio
    cliente de Supabase serializa el payload completo a JSON al hacer la
    petición, y la columna es `jsonb`. Serializar aquí a mano produciría un
    doble-encoding (un string JSON guardado dentro de otro string JSON).
    """
    sb = cliente()
    if sb is None:
        return False
    try:
        sb.table(T_CACHE_API).upsert(
            {"clave": clave, "valor": valor, "guardado_en": _ahora()},
            on_conflict="clave",
        ).execute()
        return True
    except Exception:
        return False
