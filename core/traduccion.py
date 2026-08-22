"""Traducción al español de la descripción de empresa (`longBusinessSummary`
de yfinance, siempre en inglés).

Usa `deep-translator` (envuelve el endpoint web de Google Translate, sin
API key ni coste) + caché en Supabase. La caché no es solo una optimización:
el endpoint no oficial de Google Translate puede dar error o bloquear por
límite de tasa, así que cachear evita depender de él en cada carga de
página para un texto que apenas cambia, y protege la app si el servicio
falla puntualmente (se sirve la última traducción válida).

Si la librería no está instalada, o la traducción falla (rate limit, sin
red, servicio caído), se devuelve el texto en inglés sin romper la
interfaz -- igual que el resto de fuentes opcionales del proyecto
(Supabase, Telegram, Finnhub).
"""

from __future__ import annotations

import hashlib

from core import bd_supabase

try:
    from deep_translator import GoogleTranslator
except ImportError:  # la librería es opcional; sin ella se sirve el texto en inglés
    GoogleTranslator = None  # type: ignore


def _hash(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()[:16]


def _traducir_via_google(texto: str) -> str | None:
    if GoogleTranslator is None:
        return None
    try:
        traduccion = GoogleTranslator(source="en", target="es").translate(texto)
        return traduccion.strip() if traduccion else None
    except Exception:
        return None


def traducir_descripcion(ticker: str, texto_original: str | None) -> tuple[str | None, bool]:
    """Devuelve (texto, es_traduccion).

    `es_traduccion=False` cuando se sirve el original en inglés (sin
    caché disponible, librería no instalada, fallo del servicio, o el
    ticker/texto están vacíos) -- así la interfaz puede avisar de que se
    muestra sin traducir en vez de dar a entender que es una traducción
    cuando no lo es.
    """
    if not texto_original:
        return None, False

    hash_actual = _hash(texto_original)

    cacheada = bd_supabase.obtener_descripcion_traducida(ticker, hash_actual)
    if cacheada:
        return cacheada, True

    traduccion = _traducir_via_google(texto_original)
    if not traduccion:
        return texto_original, False

    bd_supabase.guardar_descripcion_traducida(ticker, hash_actual, texto_original, traduccion)
    return traduccion, True
