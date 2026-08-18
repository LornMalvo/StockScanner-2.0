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


def es_favorable(valor: Any, referencia: Any, menor_es_mejor: bool = False) -> bool | None:
    """Compara un valor con una referencia (media sectorial o umbral general).

    Devuelve None si no hay datos suficientes para comparar (nunca se asume
    "bueno" ni "malo" sin dato). `menor_es_mejor=True` para métricas donde
    menos es preferible (PER, PEG, deuda...).
    """
    if not es_valido(valor) or not es_valido(referencia):
        return None
    return (float(valor) < float(referencia)) if menor_es_mejor else (float(valor) > float(referencia))


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


def fmt_compacto(valor: Any, moneda: str = "", decimales: int = 2) -> str:
    """Formatea magnitudes grandes: 1.234.000.000 -> 1,23B. `moneda` se añade
    tal cual al final (pasa " $" o " €" con el espacio incluido si procede)."""
    if not es_valido(valor):
        return TEXTO_ND
    v = float(valor)
    signo = "-" if v < 0 else ""
    v = abs(v)
    for corte, sufijo in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
        if v >= corte:
            return f"{signo}{v / corte:,.{decimales}f}{sufijo}{moneda}".replace(".", ",")
    return f"{signo}{v:,.{decimales}f}{moneda}".replace(".", ",")


def fmt_eur(valor_usd: Any, fx_usd_eur: Any, decimales: int = 2) -> str:
    """Solo el importe convertido a EUR (para líneas ya acompañadas del $ aparte)."""
    if not es_valido(valor_usd) or not es_valido(fx_usd_eur):
        return TEXTO_ND
    eur = float(valor_usd) * float(fx_usd_eur)
    return f"{eur:,.{decimales}f} €".replace(",", "@").replace(".", ",").replace("@", ".")


def fmt_usd_eur(valor_usd: Any, fx_usd_eur: Any, decimales: int = 2) -> str:
    """<importe> $ (<importe> €). Formato estándar para todo valor monetario en
    dólares que muestre la app (regla de oro de conversión a euros)."""
    if not es_valido(valor_usd):
        return TEXTO_ND
    base = f"{float(valor_usd):,.{decimales}f} $".replace(",", "@").replace(
        ".", ","
    ).replace("@", ".")
    if not es_valido(fx_usd_eur):
        return f"{base} (€: {TEXTO_ND})"
    return f"{base} ({fmt_eur(valor_usd, fx_usd_eur, decimales)})"


def fmt_usd_eur_compacto(
    valor_usd: Any, fx_usd_eur: Any, decimales_usd: int = 0, decimales_eur: int = 2
) -> str:
    """Magnitudes grandes en ambas divisas: 959.000.000 -> "959M $ (828,19M €)"."""
    if not es_valido(valor_usd):
        return TEXTO_ND
    usd_txt = fmt_compacto(valor_usd, " $", decimales_usd)
    if not es_valido(fx_usd_eur):
        return f"{usd_txt} (€: {TEXTO_ND})"
    eur_valor = float(valor_usd) * float(fx_usd_eur)
    eur_txt = fmt_compacto(eur_valor, " €", decimales_eur)
    return f"{usd_txt} ({eur_txt})"


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
