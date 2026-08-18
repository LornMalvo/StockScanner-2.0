"""Validación, ponderación segura y formateo de valores.

Regla de oro del proyecto: un dato que no existe NO es un cero. Cualquier
métrica ausente se excluye del cálculo y se reporta como "Dato no disponible".
Todo el resto del código debe pasar por `es_valido()` y `ponderar()`.
"""

from __future__ import annotations

import math
from datetime import date, datetime
from typing import Any, Iterable

from config.settings import TEXTO_ND


# ---------------------------------------------------------------- validez ----
def es_valido(valor: Any) -> bool:
    """True solo si el valor es un número real utilizable en un cálculo."""
    if valor is None:
        return False
    if isinstance(valor, bool):
        return True
    try:
        f = float(valor)
    except (TypeError, ValueError):
        return False
    return not (math.isnan(f) or math.isinf(f))


def num(valor: Any) -> float | None:
    """Convierte a float si es válido; None en caso contrario."""
    return float(valor) if es_valido(valor) else None


def primero_valido(*valores: Any) -> float | None:
    """Devuelve el primer valor válido de la lista (cadena de fallbacks)."""
    for v in valores:
        if es_valido(v):
            return float(v)
    return None


# ----------------------------------------------------------- ponderación ----
def ponderar(valores: dict[str, Any], pesos: dict[str, float]) -> dict:
    """Media ponderada que ignora los componentes no disponibles.

    Los pesos de los componentes ausentes se redistribuyen proporcionalmente
    entre los presentes; nunca se sustituye el dato por 0.

    Devuelve: {valor, usados: {clave: peso_normalizado}, excluidos: [claves],
               cobertura: 0-1}
    """
    usados: dict[str, float] = {}
    excluidos: list[str] = []
    for clave, peso in pesos.items():
        if es_valido(valores.get(clave)) and peso > 0:
            usados[clave] = float(peso)
        else:
            excluidos.append(clave)

    peso_total = sum(usados.values())
    peso_teorico = sum(p for p in pesos.values() if p > 0)
    if peso_total <= 0:
        return {"valor": None, "usados": {}, "excluidos": excluidos, "cobertura": 0.0}

    valor = sum(float(valores[c]) * p for c, p in usados.items()) / peso_total
    return {
        "valor": valor,
        "usados": {c: p / peso_total for c, p in usados.items()},
        "excluidos": excluidos,
        "cobertura": peso_total / peso_teorico if peso_teorico else 0.0,
    }


def escalar(valor: Any, malo: float, bueno: float) -> float | None:
    """Normaliza un valor a la escala 0-100 entre dos anclas.

    Soporta escalas invertidas (malo > bueno), p. ej. un PER donde menos es mejor.
    """
    if not es_valido(valor) or malo == bueno:
        return None
    x = (float(valor) - malo) / (bueno - malo)
    return max(0.0, min(1.0, x)) * 100.0


def media_valida(valores: Iterable[Any]) -> float | None:
    limpios = [float(v) for v in valores if es_valido(v)]
    return sum(limpios) / len(limpios) if limpios else None


# ------------------------------------------------------------- formateo -----
def fmt_num(valor: Any, decimales: int = 2, sufijo: str = "") -> str:
    if not es_valido(valor):
        return TEXTO_ND
    return f"{float(valor):,.{decimales}f}{sufijo}".replace(",", "@").replace(
        ".", ","
    ).replace("@", ".")


def fmt_pct(valor: Any, decimales: int = 1, ya_en_pct: bool = True) -> str:
    if not es_valido(valor):
        return TEXTO_ND
    v = float(valor) if ya_en_pct else float(valor) * 100
    return f"{v:+.{decimales}f} %".replace(".", ",")


def fmt_compacto(valor: Any, moneda: str = "") -> str:
    """Formatea magnitudes grandes: 1.234.000.000 -> 1,23 B."""
    if not es_valido(valor):
        return TEXTO_ND
    v = float(valor)
    signo = "-" if v < 0 else ""
    v = abs(v)
    for corte, sufijo in ((1e12, " T"), (1e9, " B"), (1e6, " M"), (1e3, " K")):
        if v >= corte:
            return f"{signo}{v / corte:,.2f}{sufijo}{moneda}".replace(".", ",")
    return f"{signo}{v:,.2f}{moneda}".replace(".", ",")


def fmt_usd_eur(valor_usd: Any, fx_usd_eur: Any, decimales: int = 2) -> str:
    """Importe en USD seguido de su conversión a EUR entre paréntesis.

    Regla del proyecto: todo valor monetario en $ debe ir acompañado de su
    conversión a €. Si no hay tipo de cambio disponible, se muestra solo el
    importe en USD (nunca se inventa una conversión).
    """
    if not es_valido(valor_usd):
        return TEXTO_ND
    base = f"{float(valor_usd):,.{decimales}f} $".replace(",", "@").replace(
        ".", ","
    ).replace("@", ".")
    if not es_valido(fx_usd_eur):
        return base
    eur = float(valor_usd) * float(fx_usd_eur)
    base_eur = f"{eur:,.{decimales}f} €".replace(",", "@").replace(".", ",").replace(
        "@", "."
    )
    return f"{base} ({base_eur})"


def _recortar_decimales(valor: float, decimales: int = 2) -> str:
    """Redondea sin ceros sobrantes: 959,00 -> '959'; 828,19 se mantiene."""
    texto = f"{valor:.{decimales}f}"
    if "." in texto:
        texto = texto.rstrip("0").rstrip(".")
    return texto.replace(".", ",")


def fmt_compacto_moneda(valor: Any, simbolo: str) -> str:
    """Magnitud grande con símbolo de moneda: 959000000 -> '959M $'.

    A diferencia de `fmt_compacto`, recorta los ceros decimales sobrantes
    (959,00 -> 959) mostrando decimales solo cuando aportan precisión real
    (828.192.403,71 -> 828,19M).
    """
    if not es_valido(valor):
        return TEXTO_ND
    v = float(valor)
    signo = "-" if v < 0 else ""
    v = abs(v)
    for corte, sufijo in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
        if v >= corte:
            return f"{signo}{_recortar_decimales(v / corte)}{sufijo} {simbolo}"
    return f"{signo}{_recortar_decimales(v)} {simbolo}"


def fmt_compacto_usd_eur(valor_usd: Any, fx_usd_eur: Any) -> str:
    """Magnitud grande en USD (formato compacto) con su conversión a EUR
    entre paréntesis. P. ej.: '959M $ (828,19M €)'."""
    if not es_valido(valor_usd):
        return TEXTO_ND
    base = fmt_compacto_moneda(valor_usd, "$")
    if not es_valido(fx_usd_eur):
        return base
    eur = float(valor_usd) * float(fx_usd_eur)
    return f"{base} ({fmt_compacto_moneda(eur, '€')})"


def fmt_fecha(valor: Any) -> str:
    if valor is None:
        return TEXTO_ND
    if isinstance(valor, (datetime, date)):
        return valor.strftime("%d/%m/%Y")
    try:
        return datetime.fromisoformat(str(valor)[:19]).strftime("%d/%m/%Y")
    except ValueError:
        return str(valor)


def dias_hasta(fecha: Any) -> int | None:
    """Días naturales desde hoy hasta la fecha dada (negativo si ya pasó)."""
    if fecha is None:
        return None
    if isinstance(fecha, datetime):
        fecha = fecha.date()
    if not isinstance(fecha, date):
        try:
            fecha = datetime.fromisoformat(str(fecha)[:10]).date()
        except ValueError:
            return None
    return (fecha - date.today()).days
