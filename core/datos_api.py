"""Capa de acceso a datos externos (yfinance, Finnhub, SEC EDGAR).

Principios:
  * Ninguna función lanza excepciones al llamante: ante fallo devuelven None o
    una estructura vacía, y anotan el motivo en la clave `errores`.
  * Nada se rellena con ceros. Lo que no llega, no existe.
  * Todo va cacheado con TTL para no agotar las cuotas de API.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pandas as pd
import requests
import streamlit as st
import yfinance as yf

from config.settings import TTL_FUNDAMENTALES, TTL_FX, TTL_NOTICIAS, TTL_PRECIO
from utils.formato import es_valido, num, primero_valido

SEC_UA = "StockScanner/1.0 (contacto: cambia-esto@ejemplo.com)"
FINNHUB_BASE = "https://finnhub.io/api/v1"


def _clave(nombre: str) -> str | None:
    """Lee una credencial de st.secrets sin romper si no está definida."""
    try:
        valor = st.secrets.get(nombre)
    except Exception:
        return None
    return str(valor) if valor else None


# ============================================================ tipo de cambio ==
@st.cache_data(ttl=TTL_FX, show_spinner=False)
def obtener_fx_usd_eur() -> float | None:
    """USD -> EUR en tiempo real. None si no se puede resolver."""
    try:
        hist = yf.Ticker("EURUSD=X").history(period="5d", interval="1h")
        if hist.empty:
            return None
        eurusd = float(hist["Close"].dropna().iloc[-1])
        return 1 / eurusd if eurusd > 0 else None
    except Exception:
        return None


# ==================================================================== yfinance =
@st.cache_data(ttl=TTL_FUNDAMENTALES, show_spinner=False)
def obtener_info(ticker: str) -> dict:
    try:
        info = yf.Ticker(ticker).get_info() or {}
    except Exception:
        info = {}
    return info


@st.cache_data(ttl=TTL_PRECIO, show_spinner=False)
def obtener_historico(ticker: str, periodo: str = "5y", intervalo: str = "1d") -> pd.DataFrame:
    try:
        df = yf.Ticker(ticker).history(period=periodo, interval=intervalo, auto_adjust=False)
    except Exception:
        return pd.DataFrame()
    if df is None or df.empty:
        return pd.DataFrame()
    df = df.dropna(subset=["Close"])
    df.index = pd.to_datetime(df.index).tz_localize(None)
    return df


@st.cache_data(ttl=TTL_PRECIO, show_spinner=False)
def obtener_precio_actual(ticker: str) -> float | None:
    try:
        rapido = yf.Ticker(ticker).fast_info
        precio = primero_valido(rapido.get("last_price"), rapido.get("regular_market_price"))
        if precio:
            return precio
    except Exception:
        pass
    hist = obtener_historico(ticker, periodo="5d")
    return float(hist["Close"].iloc[-1]) if not hist.empty else None


@st.cache_data(ttl=TTL_FUNDAMENTALES, show_spinner=False)
def obtener_estados_financieros(ticker: str) -> dict:
    """Cuenta de resultados, balance y flujo de caja (anual y trimestral)."""
    salida = {
        "resultados": pd.DataFrame(),
        "balance": pd.DataFrame(),
        "flujo_caja": pd.DataFrame(),
        "resultados_trim": pd.DataFrame(),
    }
    try:
        t = yf.Ticker(ticker)
        salida["resultados"] = t.income_stmt if t.income_stmt is not None else pd.DataFrame()
        salida["balance"] = t.balance_sheet if t.balance_sheet is not None else pd.DataFrame()
        salida["flujo_caja"] = t.cashflow if t.cashflow is not None else pd.DataFrame()
        salida["resultados_trim"] = (
            t.quarterly_income_stmt if t.quarterly_income_stmt is not None else pd.DataFrame()
        )
    except Exception:
        pass
    return salida


@st.cache_data(ttl=TTL_FUNDAMENTALES, show_spinner=False)
def obtener_earnings(ticker: str) -> dict:
    """Último resultado publicado (EPS real vs. estimado) y próxima fecha.

    Se prioriza Finnhub para el desglose de sorpresas (incluye ingresos) y se
    usa yfinance como respaldo.
    """
    salida = {
        "ultimo": None,
        "proxima_fecha": None,
        "historial": [],
        "fuente": None,
    }

    # --- Finnhub: sorpresas de EPS ---------------------------------------
    fh = _finnhub("/stock/earnings", {"symbol": ticker})
    if isinstance(fh, list) and fh:
        historial = sorted(fh, key=lambda x: x.get("period", ""), reverse=True)
        ultimo = historial[0]
        salida["historial"] = historial[:8]
        salida["ultimo"] = {
            "periodo": ultimo.get("period"),
            "eps_real": num(ultimo.get("actual")),
            "eps_estimado": num(ultimo.get("estimate")),
            "sorpresa_pct": num(ultimo.get("surprisePercent")),
            "ingresos_real": None,
            "ingresos_estimado": None,
        }
        salida["fuente"] = "Finnhub"

    # --- Finnhub: calendario de resultados (incluye ingresos) ------------
    hoy = date.today()
    cal = _finnhub(
        "/calendar/earnings",
        {
            "symbol": ticker,
            "from": (hoy - timedelta(days=200)).isoformat(),
            "to": (hoy + timedelta(days=200)).isoformat(),
        },
    )
    if isinstance(cal, dict):
        eventos = cal.get("earningsCalendar") or []
        futuros = sorted(
            [e for e in eventos if e.get("date", "") >= hoy.isoformat()],
            key=lambda e: e["date"],
        )
        if futuros:
            salida["proxima_fecha"] = futuros[0]["date"]
        pasados = sorted(
            [e for e in eventos if e.get("date", "") < hoy.isoformat()],
            key=lambda e: e["date"],
            reverse=True,
        )
        if pasados and salida["ultimo"]:
            p = pasados[0]
            salida["ultimo"]["ingresos_real"] = num(p.get("revenueActual"))
            salida["ultimo"]["ingresos_estimado"] = num(p.get("revenueEstimate"))
            salida["ultimo"]["fecha"] = p.get("date")

    # --- Respaldo yfinance ------------------------------------------------
    if salida["ultimo"] is None or salida["proxima_fecha"] is None:
        try:
            fechas = yf.Ticker(ticker).get_earnings_dates(limit=12)
        except Exception:
            fechas = None
        if fechas is not None and not fechas.empty:
            fechas = fechas.copy()
            fechas.index = pd.to_datetime(fechas.index).tz_localize(None)
            futuras = fechas[fechas.index.date >= hoy]
            pasadas = fechas[fechas.index.date < hoy]
            if salida["proxima_fecha"] is None and not futuras.empty:
                salida["proxima_fecha"] = futuras.index.min().date().isoformat()
            if salida["ultimo"] is None and not pasadas.empty:
                fila = pasadas.iloc[0]
                salida["ultimo"] = {
                    "periodo": pasadas.index[0].date().isoformat(),
                    "fecha": pasadas.index[0].date().isoformat(),
                    "eps_real": num(fila.get("Reported EPS")),
                    "eps_estimado": num(fila.get("EPS Estimate")),
                    "sorpresa_pct": num(fila.get("Surprise(%)")),
                    "ingresos_real": None,
                    "ingresos_estimado": None,
                }
                salida["fuente"] = "yfinance"
    return salida


@st.cache_data(ttl=TTL_NOTICIAS, show_spinner=False)
def obtener_noticias(ticker: str, limite: int = 5) -> list[dict]:
    """Últimas noticias, de más reciente a más antigua, con enlace a la fuente."""
    noticias: list[dict] = []
    hoy = date.today()
    fh = _finnhub(
        "/company-news",
        {
            "symbol": ticker,
            "from": (hoy - timedelta(days=30)).isoformat(),
            "to": hoy.isoformat(),
        },
    )
    if isinstance(fh, list):
        for n in fh:
            if not n.get("headline") or not n.get("url"):
                continue
            noticias.append(
                {
                    "titular": n["headline"],
                    "url": n["url"],
                    "fuente": n.get("source"),
                    "fecha": datetime.fromtimestamp(n["datetime"]) if n.get("datetime") else None,
                }
            )

    if len(noticias) < limite:
        try:
            crudas = yf.Ticker(ticker).news or []
        except Exception:
            crudas = []
        for n in crudas:
            contenido = n.get("content", n)
            url = (
                contenido.get("canonicalUrl", {}).get("url")
                if isinstance(contenido.get("canonicalUrl"), dict)
                else contenido.get("link") or n.get("link")
            )
            titular = contenido.get("title") or n.get("title")
            if not url or not titular:
                continue
            marca = contenido.get("pubDate") or n.get("providerPublishTime")
            try:
                fecha = (
                    datetime.fromisoformat(str(marca).replace("Z", "+00:00")).replace(tzinfo=None)
                    if isinstance(marca, str)
                    else datetime.fromtimestamp(marca)
                    if marca
                    else None
                )
            except Exception:
                fecha = None
            noticias.append(
                {
                    "titular": titular,
                    "url": url,
                    "fuente": (contenido.get("provider") or {}).get("displayName")
                    if isinstance(contenido.get("provider"), dict)
                    else n.get("publisher"),
                    "fecha": fecha,
                }
            )

    vistos, unicas = set(), []
    for n in sorted(noticias, key=lambda x: x["fecha"] or datetime.min, reverse=True):
        if n["url"] in vistos:
            continue
        vistos.add(n["url"])
        unicas.append(n)
    return unicas[:limite]


@st.cache_data(ttl=TTL_FUNDAMENTALES, show_spinner=False)
def obtener_consenso(ticker: str) -> dict:
    """Consenso de analistas: precio objetivo, cobertura y grado de unanimidad."""
    info = obtener_info(ticker)
    salida = {
        "precio_objetivo": primero_valido(info.get("targetMeanPrice")),
        "objetivo_alto": primero_valido(info.get("targetHighPrice")),
        "objetivo_bajo": primero_valido(info.get("targetLowPrice")),
        "n_analistas": primero_valido(info.get("numberOfAnalystOpinions")),
        "recomendacion": info.get("recommendationKey"),
        "unanimidad": None,
    }

    trend = _finnhub("/stock/recommendation", {"symbol": ticker})
    if isinstance(trend, list) and trend:
        ult = sorted(trend, key=lambda x: x.get("period", ""), reverse=True)[0]
        compra = (ult.get("strongBuy") or 0) + (ult.get("buy") or 0)
        total = compra + (ult.get("hold") or 0) + (ult.get("sell") or 0) + (
            ult.get("strongSell") or 0
        )
        if total:
            salida["unanimidad"] = compra / total
            if not es_valido(salida["n_analistas"]):
                salida["n_analistas"] = float(total)
    return salida


# ==================================================================== Finnhub ==
def _finnhub(ruta: str, params: dict) -> dict | list | None:
    token = _clave("FINNHUB_API_KEY")
    if not token:
        return None
    try:
        r = requests.get(
            f"{FINNHUB_BASE}{ruta}", params={**params, "token": token}, timeout=12
        )
        if r.status_code != 200:
            return None
        return r.json()
    except Exception:
        return None


@st.cache_data(ttl=TTL_FUNDAMENTALES, show_spinner=False)
def obtener_perfil_finnhub(ticker: str) -> dict:
    datos = _finnhub("/stock/profile2", {"symbol": ticker})
    return datos if isinstance(datos, dict) else {}


# =================================================================== SEC EDGAR ==
@st.cache_data(ttl=86400, show_spinner=False)
def obtener_cik(ticker: str) -> str | None:
    try:
        r = requests.get(
            "https://www.sec.gov/files/company_tickers.json",
            headers={"User-Agent": SEC_UA},
            timeout=15,
        )
        if r.status_code != 200:
            return None
        for fila in r.json().values():
            if fila.get("ticker", "").upper() == ticker.upper():
                return str(fila["cik_str"]).zfill(10)
    except Exception:
        return None
    return None


@st.cache_data(ttl=86400, show_spinner=False)
def obtener_hechos_sec(ticker: str, conceptos: tuple[str, ...] = ()) -> dict:
    """Serie anual de conceptos XBRL declarados a la SEC (fuente primaria).

    Se emplea como contraste de los fundamentales de yfinance y como respaldo
    cuando estos faltan. Solo aplica a emisores estadounidenses.
    """
    conceptos = conceptos or (
        "Revenues",
        "NetIncomeLoss",
        "StockholdersEquity",
        "Assets",
        "Liabilities",
        "NetCashProvidedByUsedInOperatingActivities",
        "CommonStockSharesOutstanding",
    )
    cik = obtener_cik(ticker)
    if not cik:
        return {}
    salida: dict[str, list[dict]] = {}
    for concepto in conceptos:
        try:
            r = requests.get(
                f"https://data.sec.gov/api/xbrl/companyconcept/CIK{cik}/us-gaap/{concepto}.json",
                headers={"User-Agent": SEC_UA},
                timeout=15,
            )
            if r.status_code != 200:
                continue
            unidades = r.json().get("units", {})
            registros = unidades.get("USD") or unidades.get("shares") or []
            anuales = [
                {"fin": x.get("end"), "valor": num(x.get("val")), "forma": x.get("form")}
                for x in registros
                if x.get("form") in ("10-K", "20-F") and x.get("fp") == "FY"
            ]
            if anuales:
                salida[concepto] = sorted(anuales, key=lambda x: x["fin"], reverse=True)[:6]
        except Exception:
            continue
    return salida


# ============================================================ agregador único ==
def obtener_paquete(ticker: str) -> dict:
    """Recopila en una sola estructura todo lo necesario para el análisis."""
    ticker = ticker.strip().upper()
    info = obtener_info(ticker)
    historico = obtener_historico(ticker)
    perfil = obtener_perfil_finnhub(ticker)

    existe = bool(info.get("longName") or info.get("shortName")) or not historico.empty
    precio = primero_valido(
        info.get("currentPrice"),
        info.get("regularMarketPrice"),
        obtener_precio_actual(ticker),
    )

    return {
        "ticker": ticker,
        "existe": existe,
        "info": info,
        "perfil": perfil,
        "historico": historico,
        "precio": precio,
        "moneda": info.get("currency") or perfil.get("currency"),
        "nombre": info.get("longName") or info.get("shortName") or perfil.get("name"),
        "sector": info.get("sector") or perfil.get("finnhubIndustry"),
        "industria": info.get("industry"),
        "descripcion": info.get("longBusinessSummary"),
        "estados": obtener_estados_financieros(ticker),
        "earnings": obtener_earnings(ticker),
        "noticias": obtener_noticias(ticker),
        "consenso": obtener_consenso(ticker),
        "sec": obtener_hechos_sec(ticker),
        "fx_usd_eur": obtener_fx_usd_eur(),
        "generado": datetime.utcnow().isoformat(timespec="seconds"),
    }
