"""Capa de acceso a datos externos (yfinance, Finnhub, SEC EDGAR).

Principios:
  * Ninguna función lanza excepciones al llamante: ante fallo devuelven None o
    una estructura vacía, y anotan el motivo en la clave `errores`.
  * Nada se rellena con ceros. Lo que no llega, no existe.
  * Todo va cacheado con TTL para no agotar las cuotas de API.
  * Ninguna petición es prescindible: antes de tocar red se comprueba L1
    (memoria), luego L2 (Supabase, solo para lo que casi nunca cambia).
"""

from __future__ import annotations

import io
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time as dtime, timedelta

try:
    from zoneinfo import ZoneInfo
except ImportError:  # Python < 3.9, no debería darse en este proyecto
    ZoneInfo = None  # type: ignore

import pandas as pd
import requests
import streamlit as st
import yfinance as yf

from config.settings import (
    ETF_MERCADO,
    ETF_SECTORIAL,
    MERCADO_HORA_APERTURA,
    MERCADO_HORA_CIERRE,
    MERCADO_ZONA_HORARIA,
    TTL_ESTADOS_FINANCIEROS,
    TTL_FUNDAMENTALES,
    TTL_FX,
    TTL_INFO_L2,
    TTL_HISTORICO_RESPALDO,
    TTL_NOTICIAS,
    TTL_PRECIO,
    TTL_REFERENCIA_MERCADO,
)
from core import bd_supabase
from utils.formato import es_valido, num, primero_valido

logger = logging.getLogger("stockscanner.api")

SEC_UA = "StockScanner/1.0 (contacto: tu-email-real@dominio.com)"
FINNHUB_BASE = "https://finnhub.io/api/v1"

# Intervalo mínimo entre peticiones a Yahoo. Yahoo limita por IP y en
# Streamlit Community Cloud la IP es compartida con otras apps, así que el
# presupuesto real de peticiones es mucho menor de lo que parece.
INTERVALO_MIN_YAHOO = 0.4
REINTENTOS_YAHOO = 3
TTL_FALLO = 120  # rate-limit u otro fallo transitorio: se recuerda 2 min
TTL_FALLO_TICKER_INEXISTENTE = 21600  # 6 h: un ticker mal escrito no va a
# empezar a existir en 2 minutos; no tiene sentido reintentarlo tan seguido.


@st.cache_resource(show_spinner=False, max_entries=64)
def _ticker(simbolo: str) -> yf.Ticker:
    """Objeto Ticker reutilizado entre llamadas y entre reruns.

    Importante para el consumo de API: yfinance memoriza en la propia
    instancia lo que ya ha descargado, así que reutilizar el objeto evita
    repetir peticiones. Crear un `yf.Ticker` nuevo en cada llamada —como se
    hacía antes— tiraba esa caché interna a la basura y multiplicaba las
    peticiones a Yahoo.

    NO se le pasa una sesión `curl_cffi` propia (se hacía antes, vía una
    función `_sesion_yfinance()` ya retirada). Era necesario en versiones
    antiguas de yfinance (0.2.x) para imitar la huella TLS de un navegador
    real y esquivar el bloqueo de Yahoo. Desde que yfinance saltó a la
    serie 1.x, la librería gestiona su propia sesión `curl_cffi` con
    impersonación de Chrome de forma interna, y pasarle una sesión propia
    hace que las peticiones devuelvan respuestas vacías sin lanzar
    excepción (no un cookie/crumb caducado: por eso ni purgar la sesión en
    memoria ni reiniciar la app lo arreglaban). Solución oficial de los
    mantenedores de yfinance: no pasar `session=`, dejar que la gestione
    yfinance. Ver github.com/ranaroussi/yfinance issue #2496.
    """
    return yf.Ticker(simbolo)


@st.cache_resource(show_spinner=False)
def _almacen() -> dict:
    """Caché manual (clave -> (marca_tiempo, valor)) compartida entre reruns.

    No se usa `st.cache_data` para los fundamentales porque cachea también los
    fallos durante todo el TTL: un único error de rate limit dejaba la ficha
    vacía durante una hora. Aquí los fallos caducan en TTL_FALLO segundos.
    """
    return {}


_ULTIMA_PETICION = {"t": 0.0}
_THROTTLE_LOCK = threading.Lock()


def _throttle() -> None:
    """Espacia las peticiones a Yahoo para no disparar el límite por IP.

    Protegido con lock: desde que `obtener_paquete()` lanza las llamadas a
    Finnhub en paralelo (`_finnhub()`, que no pasa por aquí) y algunas de
    ellas caen ocasionalmente a un respaldo de yfinance, más de un hilo
    puede llamar a `_throttle()` a la vez. Sin lock, dos hilos podrían leer
    `_ULTIMA_PETICION` antes de que ninguno la actualice y saltarse el
    espaciado entre sí.
    """
    with _THROTTLE_LOCK:
        espera = INTERVALO_MIN_YAHOO - (time.monotonic() - _ULTIMA_PETICION["t"])
        if espera > 0:
            time.sleep(espera)
            _registrar("segundos_dormido", espera)
        _ULTIMA_PETICION["t"] = time.monotonic()


# ==================================================================== métricas =
# Contador de peticiones reales, para poder medir el efecto de cualquier
# cambio en vez de estimarlo a mano. No se muestra en la UI (decisión
# explícita: no meter ruido visual) — se vuelca a los logs de la app
# (visibles en "Manage app" de Streamlit Community Cloud) con
# `log_resumen_metricas()`. `reset_metricas()` se llama al principio de un
# rastreo o análisis para medir solo ese tramo.
_METRICAS_LOCK = threading.Lock()
_METRICAS: dict[str, float] = {
    "peticiones_yahoo": 0,
    "peticiones_yahoo_lote": 0,
    "peticiones_finnhub": 0,
    "aciertos_cache_l1": 0,
    "aciertos_cache_l2": 0,
    "fallos": 0,
    # Contador aparte porque el genérico `fallos` NO ve este caso: cuando
    # Yahoo no devuelve fundamentales lo hace con un 200 (o con un 404 que
    # yfinance se traga internamente), sin lanzar excepción, así que `_pedir`
    # lo cuenta como petición correcta. Es justo el fallo que hay que poder
    # rastrear en los logs.
    "fallos_fundamentales": 0,
    "segundos_dormido": 0.0,
}


def _registrar(clave: str, delta: float = 1) -> None:
    with _METRICAS_LOCK:
        _METRICAS[clave] = _METRICAS.get(clave, 0) + delta


def reset_metricas() -> None:
    with _METRICAS_LOCK:
        for k in _METRICAS:
            _METRICAS[k] = 0.0 if isinstance(_METRICAS[k], float) else 0


def resumen_metricas() -> dict:
    with _METRICAS_LOCK:
        return dict(_METRICAS)


def log_resumen_metricas(etiqueta: str = "") -> None:
    m = resumen_metricas()
    logger.info(
        "%s peticiones reales: %d Yahoo (+%d en lote) · %d Finnhub · "
        "aciertos caché: %d L1 / %d L2 · fallos: %d (%d de fundamentales) · "
        "%.1fs de throttle",
        f"[{etiqueta}]" if etiqueta else "",
        m["peticiones_yahoo"],
        m["peticiones_yahoo_lote"],
        m["peticiones_finnhub"],
        m["aciertos_cache_l1"],
        m["aciertos_cache_l2"],
        m["fallos"],
        m["fallos_fundamentales"],
        m["segundos_dormido"],
    )


# ========================================================= calendario de mercado
def _cubo_mercado() -> str:
    """Identificador que solo cambia cuando de verdad tiene sentido revalidar
    el histórico de precio: se mantiene fijo todo el fin de semana o fuera
    de horario (cero peticiones), y cambia una vez por hora durante la
    sesión de mercado (para ir incorporando la vela del día en curso sin
    recargar cada 5 minutos). No contempla festivos NYSE en esta primera
    versión: un festivo entre semana se trata como sesión normal.

    Se usa como parte de la clave de caché manual de `obtener_historico()`
    y `obtener_historicos_lote()`, no como un TTL numérico — el cambio de
    cubo ES la invalidación.
    """
    if ZoneInfo is None:
        return "sin-zona"  # red de seguridad; no debería darse en este proyecto
    ahora = datetime.now(ZoneInfo(MERCADO_ZONA_HORARIA))
    apertura = dtime(*MERCADO_HORA_APERTURA)
    cierre = dtime(*MERCADO_HORA_CIERRE)
    if ahora.weekday() >= 5:  # sábado=5, domingo=6: mismo cubo todo el finde
        iso = ahora.isocalendar()
        return f"cerrado-{iso[0]}-w{iso[1]}"
    if not (apertura <= ahora.time() <= cierre):
        return f"cerrado-{ahora.date().isoformat()}"
    return f"abierto-{ahora.date().isoformat()}-h{ahora.hour}"


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
        _registrar("peticiones_yahoo")
        try:
            return fn(), None
        except Exception as e:  # noqa: BLE001 - se reporta al llamante
            ultimo = e
            if _es_rate_limit(e) and intento < intentos - 1:
                time.sleep(1.5 * (2**intento))
                continue
            break
    if ultimo is not None:
        _registrar("fallos")
    return None, ultimo


def _cache_leer(clave: str, ttl: float):
    registro = _almacen().get(clave)
    if not registro:
        return None
    marca, valor = registro
    if isinstance(valor, dict) and "_ss_error" in valor:
        # Un ticker que no existe no va a empezar a existir en 2 minutos:
        # ese fallo se recuerda mucho más tiempo. Un rate-limit sí puede
        # resolverse pronto, así que ese sigue caducando rápido.
        caducidad = TTL_FALLO_TICKER_INEXISTENTE if valor.get("_ss_no_existe") else TTL_FALLO
    else:
        caducidad = ttl
    if time.time() - marca > caducidad:
        return None
    _registrar("aciertos_cache_l1")
    return valor


def _cache_guardar(clave: str, valor) -> None:
    _almacen()[clave] = (time.time(), valor)


def _serializable(valor):
    """Reduce un dict de yfinance a tipos que la columna `jsonb` acepta.

    `info` es casi siempre escalares y listas, pero yfinance cuela de vez en
    cuando algún tipo de numpy o una fecha. Un solo valor no serializable
    haría fallar el `upsert` entero y perderíamos el respaldo L2 sin que se
    note: se convierte a texto lo que no sea un tipo JSON nativo.
    """
    if isinstance(valor, dict):
        return {str(k): _serializable(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [_serializable(v) for v in valor]
    if valor is None or isinstance(valor, (bool, int, float, str)):
        # bool antes que int a propósito: en Python bool ES int.
        return valor
    try:
        return float(valor)  # numpy.int64, numpy.float64, Decimal…
    except (TypeError, ValueError):
        return str(valor)


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
def _info_sin_precio(info: dict) -> dict:
    """Copia de `info` sin los campos de cotización en vivo.

    Se aplica a lo que llega de L2 (Supabase), que puede tener hasta
    `TTL_INFO_L2` de antigüedad. Los fundamentales aguantan perfectamente esa
    edad; el precio no. Al quitarlos, la cadena de precio de
    `obtener_paquete()` cae sola al siguiente eslabón (último cierre del
    histórico, que sí se revalida con el calendario de mercado) en vez de
    mostrar una cotización de hace horas como si fuera de ahora.
    """
    return {k: v for k, v in info.items() if k not in _CAMPOS_PRECIO_VIVO}


_CAMPOS_PRECIO_VIVO = (
    "currentPrice",
    "regularMarketPrice",
    "regularMarketPreviousClose",
    "regularMarketOpen",
    "regularMarketDayHigh",
    "regularMarketDayLow",
    "bid",
    "ask",
)


def marcar_ticker_inexistente(ticker: str) -> None:
    """Marca en caché que el ticker de verdad NO existe, para no reintentarlo.

    Solo debe llamarse cuando hay confirmación cruzada: ni `obtener_info()` ni
    `obtener_historico()` han devuelto nada. `obtener_info()` por sí sola NO
    puede concluirlo (ver su docstring), así que la decisión vive en
    `obtener_paquete()`, que es quien ve las dos fuentes a la vez.
    """
    clave = f"info:{ticker.strip().upper()}"
    registro = _almacen().get(clave)
    valor = registro[1] if registro else {"_ss_error": ["ticker sin datos en ninguna fuente"]}
    if isinstance(valor, dict) and "_ss_error" in valor:
        valor["_ss_no_existe"] = True
        _cache_guardar(clave, valor)


def obtener_info(ticker: str) -> dict:
    """Fundamentales de yfinance, con reintentos, respaldo en L2 y diagnóstico.

    Se intenta primero `get_info()` y, si llega vacío, la propiedad `.info`.
    Si ambas fallan *sin lanzar excepción* (respuesta 200 pero sin campos de
    identidad) puede deberse a un cookie/crumb interno de yfinance caducado
    en el `Ticker` cacheado (`_ticker`, vía `st.cache_resource`, reutilizado
    entre tickers y usuarios). Ese caso no lo cubre `_pedir()` (que solo
    reintenta ante excepciones de rate-limit), así que aquí se purga el
    `Ticker` cacheado y se reintenta una vez completa con credenciales
    frescas antes de rendirse.

    IMPORTANTE — una respuesta vacía NO significa "el ticker no existe".
    Antes se marcaba `_ss_no_existe=True` en cuanto la respuesta llegaba sin
    campos de identidad, y eso hacía que el fallo se recordara 6 h
    (`TTL_FALLO_TICKER_INEXISTENTE`). El problema: Yahoo, cuando limita por
    IP, devuelve muy a menudo un 200 con el cuerpo vacío en vez de un 429, así
    que un bloqueo pasajero quedaba clasificado como permanente y los
    fundamentales de un valor perfectamente real desaparecían durante horas
    (mientras el histórico, que va por otra ruta, seguía cargando y la ficha
    se pintaba a medias). Esa clasificación se ha movido a
    `obtener_paquete()`, que es el único punto donde se ven a la vez las dos
    fuentes; aquí todo fallo caduca en `TTL_FALLO` (2 min).

    Además se respalda en L2 (Supabase): tras un redespliegue de Streamlit
    Community Cloud, L1 está vacía y esta es la primera petición de cualquier
    análisis, justo la peor combinación posible. Con L2 el primer análisis
    tras el reinicio ya no depende de que Yahoo esté de buenas.

    Si todo falla se devuelve `_ss_error` con el motivo concreto, que la
    interfaz muestra en lugar de un mudo "dato no disponible", y que además
    queda en los logs de la app ("Manage app" de Streamlit Community Cloud).
    """
    clave = f"info:{ticker}"
    cacheado = _cache_leer(clave, TTL_FUNDAMENTALES)
    if cacheado is not None:
        return cacheado

    clave_l2 = f"info:{ticker}"
    l2 = bd_supabase.cache_l2_leer(clave_l2, TTL_INFO_L2)
    if isinstance(l2, dict) and (l2.get("longName") or l2.get("shortName")):
        _registrar("aciertos_cache_l2")
        valor = _info_sin_precio(l2)
        _cache_guardar(clave, valor)
        return valor

    errores: list[str] = []
    for intento_sesion in range(2):
        t = _ticker(ticker)
        vacio_sin_excepcion = False
        for nombre_metodo, obtener in (("get_info()", t.get_info), ("propiedad .info", lambda: t.info)):
            valor, error = _pedir(obtener)
            if error is not None:
                errores.append(f"{nombre_metodo}: {type(error).__name__}: {error}")
                continue
            if valor and (
                valor.get("longName") or valor.get("shortName") or valor.get("regularMarketPrice")
            ):
                _cache_guardar(clave, valor)
                # Solo se respalda en L2 lo que tiene identidad: una respuesta
                # que solo trae precio no sirve como fundamentales cacheados.
                if valor.get("longName") or valor.get("shortName"):
                    bd_supabase.cache_l2_guardar(clave_l2, _serializable(valor))
                return valor
            vacio_sin_excepcion = True
            errores.append(
                f"{nombre_metodo}: respuesta sin campos de identidad"
                + (f" ({len(valor)} claves)" if valor else " (vacía)")
            )

        if intento_sesion == 0 and vacio_sin_excepcion:
            _ticker.clear()
            errores.append("Ticker de yfinance purgado por respuesta vacía; reintentando con instancia nueva")
        else:
            break

    # El fallo se recuerda solo TTL_FALLO (2 min). No se decide aquí si el
    # ticker existe: eso lo resuelve `obtener_paquete()` cruzando con el
    # histórico, y si confirma que no hay nada llama a
    # `marcar_ticker_inexistente()` para alargar el recuerdo del fallo.
    _registrar("fallos_fundamentales")
    logger.warning(
        "Fundamentales no disponibles para %s (%d intentos fallidos): %s",
        ticker,
        len(errores),
        " | ".join(errores) or "sin detalle",
    )
    fallo = {"_ss_error": errores}
    _cache_guardar(clave, fallo)
    return fallo


def obtener_historico(ticker: str, periodo: str = "5y", intervalo: str = "1d") -> pd.DataFrame:
    """Histórico de precio, cacheado por cubo de calendario de mercado (ver
    `_cubo_mercado()`) en vez de un TTL fijo: mientras el mercado está
    cerrado no se dispara ni una petición, y en sesión se revalida como
    mucho una vez por hora (los indicadores técnicos se calculan sobre
    cierres diarios, no sobre el precio intradía, así que no se pierde
    precisión de señal por esto).

    Usa la misma caché manual (`_almacen()`) que `obtener_info()`, en vez de
    `st.cache_data`, para que `obtener_historicos_lote()` pueda escribir
    directamente en ella los resultados de una descarga en lote y que este
    resto del sistema los reutilice sin saber que vinieron de un lote.
    """
    clave = f"historico:{ticker}:{periodo}:{intervalo}:{_cubo_mercado()}"
    cacheado = _cache_leer(clave, TTL_HISTORICO_RESPALDO)
    if cacheado is not None:
        return cacheado if isinstance(cacheado, pd.DataFrame) else pd.DataFrame()

    df, error = _pedir(
        lambda: _ticker(ticker).history(period=periodo, interval=intervalo, auto_adjust=False)
    )
    if df is None or df.empty:
        _cache_guardar(clave, {"_ss_error": [str(error)] if error else ["histórico vacío"]})
        return pd.DataFrame()
    df = df.dropna(subset=["Close"])
    df.index = pd.to_datetime(df.index).tz_localize(None)
    _cache_guardar(clave, df)
    return df


def obtener_historicos_lote(
    tickers: list[str], periodo: str = "5y", intervalo: str = "1d"
) -> dict[str, pd.DataFrame]:
    """Histórico de varios tickers en una sola petición HTTP (`yf.download`),
    en vez de una llamada `history()` por ticker. Pensada para las vistas
    que iteran sobre una lista (Rastreador, Favoritos, Cartera, Paper
    Trading): se llama una vez antes del bucle por ticker para precalentar
    la caché, y cada función que luego llame a `obtener_historico()` para
    alguno de esos tickers encuentra la caché ya caliente.

    Solo pide red para los tickers cuya entrada de caché ya ha caducado
    (según el cubo de calendario); el resto se sirve directo de caché sin
    tocar la red, así que llamar a esto con tickers ya frescos es barato.
    """
    tickers = [t.strip().upper() for t in tickers if t and t.strip()]
    if not tickers:
        return {}

    cubo = _cubo_mercado()
    resultado: dict[str, pd.DataFrame] = {}
    pendientes: list[str] = []
    for t in tickers:
        clave = f"historico:{t}:{periodo}:{intervalo}:{cubo}"
        cacheado = _cache_leer(clave, TTL_HISTORICO_RESPALDO)
        if cacheado is not None:
            resultado[t] = cacheado if isinstance(cacheado, pd.DataFrame) else pd.DataFrame()
        else:
            pendientes.append(t)

    if not pendientes:
        return resultado

    _throttle()
    _registrar("peticiones_yahoo_lote")
    try:
        descarga = yf.download(
            tickers=pendientes,
            period=periodo,
            interval=intervalo,
            group_by="ticker",
            auto_adjust=False,
            threads=True,
            progress=False,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("Fallo en descarga en lote (%d tickers): %s", len(pendientes), e)
        _registrar("fallos")
        descarga = None

    for t in pendientes:
        clave = f"historico:{t}:{periodo}:{intervalo}:{cubo}"
        df = pd.DataFrame()
        try:
            if descarga is not None and t in descarga.columns.get_level_values(0):
                df = descarga[t].dropna(subset=["Close"])
                if not df.empty:
                    df.index = pd.to_datetime(df.index).tz_localize(None)
        except Exception:  # noqa: BLE001 - un ticker roto no debe tirar el lote
            df = pd.DataFrame()
        if df.empty:
            _cache_guardar(clave, {"_ss_error": ["sin datos en la descarga en lote"]})
        else:
            _cache_guardar(clave, df)
        resultado[t] = df
    return resultado


def obtener_precios_lote(tickers: list[str]) -> dict[str, float | None]:
    """Último cierre de varios tickers en una sola petición HTTP, reutilizando
    `obtener_historicos_lote()`. Pensada para vistas de listado (Favoritos,
    Gestión de Cartera, Paper Trading), donde no hace falta la precisión a
    segundos de `fast_info` que sí usa `obtener_precio_actual()` en el
    Análisis Individual — a cambio, N peticiones individuales se convierten
    en 1 sola para todo el lote.
    """
    historicos = obtener_historicos_lote(tickers, periodo="5d")
    return {
        t: (float(df["Close"].iloc[-1]) if not df.empty else None)
        for t, df in historicos.items()
    }



@st.cache_data(ttl=TTL_REFERENCIA_MERCADO, show_spinner=False)
def obtener_referencia_mercado(sector: str | None) -> dict:
    """Histórico del ETF sectorial de referencia (o del mercado como respaldo).

    Sirve para medir la fuerza relativa del valor: si cae solo o cae con todo
    su sector. Caché a `TTL_REFERENCIA_MERCADO` (12 h), mucho más larga que
    la de un precio en vivo: alimenta un diferencial a 63 sesiones, así que
    la frescura de un precio en vivo no aporta nada y solo multiplica
    peticiones a Yahoo sin necesidad. Al estar cacheada esta función (además
    del cubo de calendario que ya protege `obtener_historico()` por dentro),
    un acierto de caché aquí evita también la llamada interna: durante esas
    12 h, todos los tickers de un mismo sector comparten la misma descarga
    sin volver a tocar la red (en el Rastreador, un lote de 10 tecnológicas
    gasta una sola petición extra en total, no diez, y esa petición no se
    repite hasta el día siguiente).
    """
    simbolo = ETF_SECTORIAL.get(sector or "", ETF_MERCADO)
    historico = obtener_historico(simbolo, periodo="2y")
    return {
        "simbolo": simbolo,
        "nombre": ("mercado" if simbolo == ETF_MERCADO else f"sector {sector}"),
        "historico": historico,
    }


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


def _estados_a_json(estados: dict[str, pd.DataFrame]) -> dict:
    """Convierte los DataFrames de estados financieros a algo JSON-serializable
    para la caché L2 (columna jsonb en Supabase). `orient="split"` conserva
    índice y columnas; `date_format="iso"` evita ambigüedad de fechas."""
    salida = {}
    for k, df in estados.items():
        salida[k] = df.to_json(orient="split", date_format="iso") if isinstance(df, pd.DataFrame) and not df.empty else None
    return salida


def _estados_desde_json(datos: dict) -> dict[str, pd.DataFrame]:
    salida: dict[str, pd.DataFrame] = {}
    for k, v in (datos or {}).items():
        if not v:
            salida[k] = pd.DataFrame()
            continue
        try:
            salida[k] = pd.read_json(io.StringIO(v), orient="split")
        except Exception:
            salida[k] = pd.DataFrame()
    return salida


@st.cache_data(ttl=TTL_ESTADOS_FINANCIEROS, show_spinner=False)
def obtener_estados_financieros(ticker: str) -> dict:
    """Cuenta de resultados, balance y flujo de caja (anual y trimestral).

    Cada propiedad se evalúa una sola vez: `t.income_stmt` dispara descarga la
    primera vez, y escribirlo dos veces (como en `x if x is not None`)
    duplicaba innecesariamente el trabajo.

    Estos datos solo cambian 4 veces al año (publicación de resultados), así
    que además del TTL largo en memoria (L1, `TTL_ESTADOS_FINANCIEROS`) se
    respaldan en Supabase (L2): si el contenedor de Streamlit se reinicia
    por inactividad y pierde la caché en memoria, esta función encuentra el
    dato en Supabase antes de volver a pedirlo a Yahoo.
    """
    clave_l2 = f"estados:{ticker}"
    l2 = bd_supabase.cache_l2_leer(clave_l2, TTL_ESTADOS_FINANCIEROS)
    if l2 is not None:
        _registrar("aciertos_cache_l2")
        return _estados_desde_json(l2)

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

    if any(not df.empty for df in salida.values()):
        bd_supabase.cache_l2_guardar(clave_l2, _estados_a_json(salida))
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
    _registrar("peticiones_finnhub")
    try:
        r = requests.get(
            f"{FINNHUB_BASE}{ruta}", params={**params, "token": token}, timeout=12
        )
        if r.status_code != 200:
            _registrar("fallos")
            return None
        return r.json()
    except Exception:
        _registrar("fallos")
        return None


@st.cache_data(ttl=TTL_FUNDAMENTALES, show_spinner=False)
def obtener_perfil_finnhub(ticker: str) -> dict:
    """Perfil de empresa de Finnhub: sector, nombre, moneda de respaldo.

    Se usa como L2 en Supabase porque, aunque técnicamente puede cambiar
    (cambio de sector, delisting), en la práctica es casi tan estable como
    los estados financieros — no hay motivo para perderlo en cada reinicio
    del contenedor. `obtener_paquete()` además solo llama a esta función
    cuando `info` de yfinance no trae ya sector/nombre/moneda, que es la
    mayoría de los casos para tickers grandes/medianos.
    """
    clave_l2 = f"perfil_finnhub:{ticker}"
    l2 = bd_supabase.cache_l2_leer(clave_l2, TTL_ESTADOS_FINANCIEROS)
    if l2 is not None:
        _registrar("aciertos_cache_l2")
        return l2

    datos = _finnhub("/stock/profile2", {"symbol": ticker})
    salida = datos if isinstance(datos, dict) else {}
    if salida:
        bd_supabase.cache_l2_guardar(clave_l2, salida)
    return salida


# =================================================================== SEC EDGAR ==
@st.cache_data(ttl=86400, show_spinner=False)
def obtener_cik(ticker: str) -> str | None:
    """CIK del ticker en SEC EDGAR. Casi nunca cambia (solo si la empresa
    se da de baja/alta), así que se respalda en L2 con un horizonte largo:
    la petición evitada es cara (descarga el listado completo de tickers
    de la SEC, no una consulta puntual)."""
    clave_l2 = f"cik:{ticker}"
    l2 = bd_supabase.cache_l2_leer(clave_l2, TTL_ESTADOS_FINANCIEROS * 7)
    if l2 is not None:
        _registrar("aciertos_cache_l2")
        return l2 or None

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
                cik = str(fila["cik_str"]).zfill(10)
                bd_supabase.cache_l2_guardar(clave_l2, cik)
                return cik
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


@st.cache_data(ttl=TTL_FUNDAMENTALES, show_spinner=False)
def obtener_estimaciones_analistas(ticker: str) -> dict:
    """Crecimiento y BPA estimados por los analistas (pestaña Analysis de Yahoo).

    Devuelve el horizonte `+1y` (próximo ejercicio completo), que es el más
    lejano que Yahoo publica de forma fiable: no hay estimaciones a 2-3 años
    salvo la fila `LTG` de `growth_estimates`, que viene vacía en buena parte
    de los valores. Se usa para alimentar el crecimiento del DCF y la
    valoración por PEG con una cifra específica de la empresa, en vez de
    extrapolar el crecimiento pasado.

    Los nombres de estas propiedades cambian entre versiones de yfinance, así
    que se prueban varias y se ignoran silenciosamente las que no existan.
    """
    salida = {"crecimiento_1y": None, "eps_1y": None, "n_analistas_eps": None}
    t = _ticker(ticker)

    est, _ = _pedir(lambda: t.earnings_estimate, intentos=1)
    if isinstance(est, pd.DataFrame) and not est.empty and "+1y" in est.index:
        fila = est.loc["+1y"]
        salida["eps_1y"] = num(fila.get("avg"))
        salida["crecimiento_1y"] = num(fila.get("growth"))
        salida["n_analistas_eps"] = num(fila.get("numberOfAnalysts"))

    if not es_valido(salida["crecimiento_1y"]):
        cre, _ = _pedir(lambda: t.growth_estimates, intentos=1)
        if isinstance(cre, pd.DataFrame) and not cre.empty and "+1y" in cre.index:
            columna = "stockTrend" if "stockTrend" in cre.columns else cre.columns[0]
            salida["crecimiento_1y"] = num(cre.loc["+1y", columna])

    return salida


# ============================================================ agregador único ==
def obtener_paquete(ticker: str, incluir_noticias: bool = True) -> dict:
    """Recopila en una sola estructura todo lo necesario para el análisis.

    Se evita cualquier petición prescindible:
      * El precio solo se pide aparte si no venía ya en `info` o en el
        histórico.
      * Los datos de SEC EDGAR (8 peticiones) se han sacado de aquí porque
        ningún módulo de cálculo los consumía; se piden bajo demanda con
        `obtener_hechos_sec(ticker)`.
      * El perfil de Finnhub (`obtener_perfil_finnhub`) solo se pide si
        `info` de yfinance no trae ya sector/nombre/moneda — el caso
        mayoritario para tickers grandes/medianos no necesita ese respaldo.
      * `incluir_noticias=False` (usado por el Rastreador) se salta
        `obtener_noticias()` por completo: no alimenta ningún cálculo
        (Calidad, Valoración, Timing), es puramente informativa para la
        vista de Análisis Individual, así que pedirla en un escaneo por
        lote de 10 tickers solo tira peticiones a la basura.

    Las llamadas que sí van a Finnhub (perfil, earnings, consenso, y
    noticias si se incluyen) se lanzan en paralelo con un hilo cada una:
    Finnhub no comparte límite de tasa con Yahoo, así que esto no reduce el
    número de peticiones pero sí recorta el tiempo de espera de un análisis
    (antes en serie, una detrás de otra). Los estados financieros y las
    estimaciones de analistas se dejan fuera del hilo compartido porque son
    yfinance puro y sí compiten por el mismo throttle que el histórico.
    """
    ticker = ticker.strip().upper()
    info = obtener_info(ticker)
    historico = obtener_historico(ticker)
    estados = obtener_estados_financieros(ticker)
    estimaciones = obtener_estimaciones_analistas(ticker)

    existe = bool(info.get("longName") or info.get("shortName")) or not historico.empty

    # Confirmación cruzada: solo aquí, con las dos fuentes a la vista, se
    # puede afirmar que un ticker no existe. `obtener_info()` ya no lo decide
    # por su cuenta (una respuesta vacía de Yahoo es indistinguible de un
    # bloqueo por IP). Marcarlo alarga el recuerdo del fallo a 6 h y evita
    # castigar el presupuesto de peticiones con un ticker mal escrito.
    if not existe:
        marcar_ticker_inexistente(ticker)
        logger.info("Ticker %s sin datos ni en info ni en histórico: marcado como inexistente", ticker)

    # Cadena de precio de más barata a más cara: info ya descargado -> último
    # cierre del histórico ya descargado -> petición nueva (solo si hace falta).
    precio = primero_valido(info.get("currentPrice"), info.get("regularMarketPrice"))
    if not es_valido(precio) and not historico.empty:
        precio = float(historico["Close"].iloc[-1])
    if not es_valido(precio):
        precio = obtener_precio_actual(ticker)

    necesita_perfil = not (
        info.get("sector") and (info.get("longName") or info.get("shortName")) and info.get("currency")
    )

    tareas: dict[str, object] = {}
    with ThreadPoolExecutor(max_workers=4) as ex:
        if necesita_perfil:
            tareas["perfil"] = ex.submit(obtener_perfil_finnhub, ticker)
        tareas["earnings"] = ex.submit(obtener_earnings, ticker)
        tareas["consenso"] = ex.submit(obtener_consenso, ticker)
        if incluir_noticias:
            tareas["noticias"] = ex.submit(obtener_noticias, ticker)
        resultados = {clave: futuro.result() for clave, futuro in tareas.items()}

    perfil = resultados.get("perfil", {})

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
        "estados": estados,
        "earnings": resultados.get(
            "earnings", {"ultimo": None, "proxima_fecha": None, "historial": [], "fuente": None}
        ),
        "noticias": resultados.get("noticias", []),
        "consenso": resultados.get("consenso", {}),
        "estimaciones": estimaciones,
        "fx_usd_eur": obtener_fx_usd_eur(),
        "generado": datetime.utcnow().isoformat(timespec="seconds"),
    }
