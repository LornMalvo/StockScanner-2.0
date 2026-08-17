"""Persistencia en Supabase.

La app funciona sin base de datos (modo consulta): si faltan las credenciales,
`cliente()` devuelve None y cada función lo comunica en la interfaz en vez de
romper. El esquema SQL está en sql/schema.sql.
"""

from __future__ import annotations

from datetime import datetime, timezone

import streamlit as st

try:
    from supabase import Client, create_client
except ImportError:  # la librería es opcional en desarrollo local
    Client = None  # type: ignore
    create_client = None  # type: ignore


T_FAVORITOS = "favoritos"
T_ANALISIS = "analisis_historico"
T_CARTERA = "cartera_posiciones"
T_PAPER = "paper_trading_posiciones"
T_NIVELES = "paper_trading_niveles"

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
def listar_cartera() -> list[dict]:
    sb = cliente()
    if sb is None:
        return []
    try:
        r = sb.table(T_CARTERA).select("*").eq("usuario_id", _usuario()).execute()
        return r.data or []
    except Exception:
        return []


def registrar_posicion_real(datos: dict) -> bool:
    sb = cliente()
    if sb is None:
        return False
    try:
        sb.table(T_CARTERA).insert({**datos, "usuario_id": _usuario(), "creado_en": _ahora()}).execute()
        return True
    except Exception:
        return False


# --------------------------------------------------------- paper trading ----
def abrir_paper_trade(ticker: str, plan: dict, contexto: dict) -> bool:
    """Persiste la ejecución del plan DCA y sus niveles asociados."""
    sb = cliente()
    if sb is None:
        return False
    try:
        posicion = (
            sb.table(T_PAPER)
            .insert(
                {
                    "usuario_id": _usuario(),
                    "ticker": ticker.upper(),
                    "estado": "abierta",
                    "precio_apertura": plan.get("precio_referencia"),
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
        posicion_id = (posicion.data or [{}])[0].get("id")
        if not posicion_id:
            return True

        niveles = [
            {
                "posicion_id": posicion_id,
                "tipo": "entrada",
                "nivel": n["nivel"],
                "precio": n["precio"],
                "peso": n["peso_capital"],
                "ejecutado": n["nivel"] == 1,
                "motivos": ", ".join(n["motivos"]),
            }
            for n in plan.get("entradas", [])
        ] + [
            {
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
        if niveles:
            sb.table(T_NIVELES).insert(niveles).execute()
        return True
    except Exception:
        return False


def listar_paper_trades(estado: str | None = "abierta") -> list[dict]:
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


def cerrar_paper_trade(posicion_id, precio_cierre: float, motivo: str = "manual") -> bool:
    sb = cliente()
    if sb is None:
        return False
    try:
        sb.table(T_PAPER).update(
            {
                "estado": "cerrada",
                "precio_cierre": precio_cierre,
                "motivo_cierre": motivo,
                "cerrada_en": _ahora(),
            }
        ).eq("id", posicion_id).execute()
        return True
    except Exception:
        return False
