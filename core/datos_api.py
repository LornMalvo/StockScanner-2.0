"""Capa de acceso a datos externos (yfinance, Finnhub, SEC EDGAR).

Principios:
  * Ninguna función lanza excepciones al llamante: ante fallo devuelven None o
    una estructura vacía, y anotan el motivo en la clave `errores`.
  * Nada se rellena con ceros. Lo que no llega, no existe.
  * Todo va cacheado con TTL para no agotar las cuotas de API.
"""

from __future__ import annotations

import time
from datetime import date, datetime, timedelta

import pandas as pd
import requests
import streamlit as st
import yfinance as yf

from config.settings import TTL_FUNDAMENTALES, TTL_FX, TTL_NOTICIAS, TTL_PRECIO
from utils.formato import es_valido, num, primero_valido

SEC_UA = "StockScanner/1.0 (contacto: tu-email-real@dominio.com)"
FINNHUB_BASE = "https://finnhub.io/api/v1"

# Intervalo mínimo entre peticiones a Yahoo. Yahoo limita por IP y en
# Streamlit Community Cloud la IP es compartida con otras apps, así que el
# presupuesto real de peticiones es mucho menor de lo que parece.
INTERVALO_MIN_YAHOO = 0.4
REINTENTOS_YAHOO = 3
TTL_FALLO = 120  # un fallo se recuerda 2 min, no una hora


@st.cache_resource(show_spinner=False)
def _sesion_yfinance():
    """Sesión con huella de navegador real para las peticiones a Yahoo Finance.

    Yahoo bloquea o limita muy agresivamente las peticiones que no parecen
    venir de un navegador. Se usa `curl_cffi` con `impersonate="chrome"` para
    replicar las cabeceras TLS/HTTP de un Chrome real; si el paquete no está
    instalado se cae de vuelta a una sesión de requests normal.
    """
    try:
        from curl_cffi import requests as curl_requests

        return curl_requests.Session(impersonate="chrome")
    except ImportError:
        return requests.Session()


@st.cache_resource(show_spinner=False, max_entries=64)
def _ticker(simbolo: str) -> yf.Ticker:
    """Objeto Ticker reutilizado entre llamadas y entre reruns.

    Importante para el consumo de API: yfinance memoriza en la propia
    instancia lo que ya ha descargado, así que reutilizar el objeto evita
    repetir peticiones. Crear un `yf.Ticker` nuevo en cada llamada —como se
    hacía antes— tiraba esa caché interna a la basura y multiplicaba las
    peticiones a Yahoo.
    """
    return yf.Ticker(simbolo, session=_sesion_yfinance())


@st.cache_resource(show_spinner=False)
def _almacen() -> dict:
    """Caché manual (clave -> (marca_tiempo, valor)) compartida entre reruns.

    No se usa `st.cache_data` para los fundamentales porque cachea también los
    fallos durante todo el TTL: un único error de rate limit dejaba la ficha
    vacía durante una hora. Aquí los fallos caducan en TTL_FALLO segundos.
    """
    return {}


_ULTIMA_PETICION = {"t": 0.0}


def _throttle() -> None:
    """Espacia las peticiones a Yahoo para no disparar el límite por IP."""
    espera = INTERVALO_MIN_YAHOO - (time.monotonic() - _ULTIMA_PETICION["t"])
    if espera > 0:
        time.sleep(espera)
    _ULTIMA_PETICION["t"] = time.monotonic()


def _es_rate_limit(e: Exception) -> bool:
    texto = f"{type(e).__name__} {e}".lower()
    return "ratelimit" in texto or "rate limit" in texto or "429" in texto or "too many" in texto


def _pedir(fn, intentos: int = REINTENTOS_YAHOO):
    """Ejecuta una petición a Yahoo con throttle y reintentos escalonados.

    Devuelve (valor, error). Solo reintenta ante rate limit: cualquier otro
    error se propaga de inmediato porque reintentarlo no lo va a arreglar.
    """
    ultimo: Exception | None = None
    for intento in range(intentos):
        _throttle()
        try:
            return fn(), None
        except Exception as e:  # noqa: BLE001 - se reporta al llamante
            ultimo = e
            if _es_rate_limit(e) and intento < intentos - 1:
                time.sleep(1.5 * (2**intento))
                continue
            break
    return None, ultimo


def _cache_leer(clave: str, ttl: float):
    registro = _almacen().get(clave)
    if not registro:
        return None
    marca, valor = registro
    caducidad = TTL_FALLO if isinstance(valor, dict) and "_ss_error" in valor else ttl
    if time.time() - marca > caducidad:
        return None
    return valor


def _cache_guardar(clave: str, valor) -> None:
    _almacen()[clave] = (time.time(), valor)


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
    hist, _ = _pedir(lambda: _ticker("EURUSD=X").history(period="5d", interval="1h"))
    if hist is None or hist.empty:
        return None
    try:
        eurusd = float(hist["Close"].dropna().iloc[-1])
    except (IndexError, ValueError):
        return None
    return 1 / eurusd if eurusd > 0 else None


# ==================================================================== yfinance =
def obtener_info(ticker: str) -> dict:
    """Fundamentales de yfinance, con reintentos y diagnóstico real.

    Se intenta primero `get_info()` y, si llega vacío, la propiedad `.info`.
    Si ambas fallan se devuelve `_ss_error` con el motivo concreto, que la
    interfaz muestra en lugar de un mudo "dato no disponible".
    """
    clave = f"info:{ticker}"
    cacheado = _cache_leer(clave, TTL_FUNDAMENTALES)
    if cacheado is not None:
        return cacheado

    errores: list[str] = []
    t = _ticker(ticker)
    for nombre_metodo, obtener in (("get_info()", t.get_info), ("propiedad .info", lambda: t.info)):
        valor, error = _pedir(obtener)
        if error is not None:
            errores.append(f"{nombre_metodo}: {type(error).__name__}: {error}")
            continue
        if valor and (
            valor.get("longName") or valor.get("shortName") or valor.get("regularMarketPrice")
        ):
            _cache_guardar(clave, valor)
            return valor
        errores.append(
            f"{nombre_metodo}: respuesta sin campos de identidad"
            + (f" ({len(valor)} claves)" if valor else " (vacía)")
        )

    fallo = {"_ss_error": errores}
    _cache_guardar(clave, fallo)
    return fallo


@st.cache_data(ttl=TTL_PRECIO, show_spinner=False)
def obtener_historico(ticker: str, periodo: str = "5y", intervalo: str = "1d") -> pd.DataFrame:
    df, _ = _pedir(
        lambda: _ticker(ticker).history(period=periodo, interval=intervalo, auto_adjust=False)
    )
    if df is None or df.empty:
        return pd.DataFrame()
    df = df.dropna(subset=["Close"])
    df.index = pd.to_datetime(df.index).tz_localize(None)
    return df



@st.cache_data(ttl=TTL_PRECIO, show_spinner=False)
def obtener_precio_actual(ticker: str) -> float | None:
    """Precio actual: primero `fast_info` (endpoint ligero), luego histórico."""
    rapido, _ = _pedir(lambda: _ticker(ticker).fast_info)
    if rapido is not None:
        try:
            precio = primero_valido(rapido.get("last_price"), rapido.get("regular_market_price"))
        except Exception:
            precio = None
        if es_valido(precio):
            return precio
    hist = obtener_historico(ticker, periodo="5d")
    return float(hist["Close"].iloc[-1]) if not hist.empty else None


@st.cache_data(ttl=TTL_FUNDAMENTALES, show_spinner=False)
def obtener_estados_financieros(ticker: str) -> dict:
    """Cuenta de resultados, balance y flujo de caja (anual y trimestral).

    Cada propiedad se evalúa una sola vez: `t.income_stmt` dispara descarga la
    primera vez, y escribirlo dos veces (como en `x if x is not None`)
    duplicaba innecesariamente el trabajo.
    """
    t = _ticker(ticker)
    campos = {
        "resultados": lambda: t.income_stmt,
        "balance": lambda: t.balance_sheet,
        "flujo_caja": lambda: t.cashflow,
        "resultados_trim": lambda: t.quarterly_income_stmt,
    }
    salida: dict[str, pd.DataFrame] = {}
    for nombre, obtener in campos.items():
        valor, _ = _pedir(obtener, intentos=2)
        salida[nombre] = valor if isinstance(valor, pd.DataFrame) else pd.DataFrame()
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
        fechas, _ = _pedir(lambda: _ticker(ticker).get_earnings_dates(limit=12), intentos=2)
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
        crudas, _ = _pedir(lambda: _ticker(ticker).news, intentos=2)
        crudas = crudas or []
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
    """Recopila en una sola estructura todo lo necesario para el análisis.

    Se evita cualquier petición prescindible: el precio solo se pide aparte si
    no venía ya en `info` o en el histórico, y los datos de SEC EDGAR (8
    peticiones) se han sacado de aquí porque ningún módulo de cálculo los
    consumía; se piden bajo demanda con `obtener_hechos_sec(ticker)`.
    """
    ticker = ticker.strip().upper()
    info = obtener_info(ticker)
    historico = obtener_historico(ticker)
    perfil = obtener_perfil_finnhub(ticker)

    existe = bool(info.get("longName") or info.get("shortName")) or not historico.empty

    # Cadena de precio de más barata a más cara: info ya descargado -> último
    # cierre del histórico ya descargado -> petición nueva (solo si hace falta).
    precio = primero_valido(info.get("currentPrice"), info.get("regularMarketPrice"))
    if not es_valido(precio) and not historico.empty:
        precio = float(historico["Close"].iloc[-1])
    if not es_valido(precio):
        precio = obtener_precio_actual(ticker)

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
        "fx_usd_eur": obtener_fx_usd_eur(),
        "generado": datetime.utcnow().isoformat(timespec="seconds"),
    }
