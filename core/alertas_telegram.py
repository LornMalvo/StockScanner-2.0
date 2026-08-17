"""Envío de alertas a Telegram.

Se usa para avisar de: ejecución de un plan DCA, alcance de niveles de entrada
o salida y saltos de stop loss en las posiciones de Paper Trading.
"""

from __future__ import annotations

import requests
import streamlit as st

API = "https://api.telegram.org/bot{token}/sendMessage"


def _credenciales() -> tuple[str | None, str | None]:
    try:
        return st.secrets.get("TELEGRAM_BOT_TOKEN"), st.secrets.get("TELEGRAM_CHAT_ID")
    except Exception:
        return None, None


def disponible() -> bool:
    token, chat = _credenciales()
    return bool(token and chat)


def enviar(mensaje: str) -> bool:
    """Envía un mensaje en formato HTML. False si no hay credenciales o falla."""
    token, chat = _credenciales()
    if not token or not chat:
        return False
    try:
        r = requests.post(
            API.format(token=token),
            json={
                "chat_id": str(chat),
                "text": mensaje,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=10,
        )
        return r.status_code == 200
    except Exception:
        return False


def alerta_plan_ejecutado(ticker: str, plan: dict, veredicto: str) -> bool:
    entradas = "\n".join(
        f"  • Entrada {n['nivel']}: {n['precio']:.2f} ({n['distancia_pct']:+.1f} %)"
        for n in plan.get("entradas", [])
    )
    salidas = "\n".join(
        f"  • Salida {n['nivel']}: {n['precio']:.2f} ({n['distancia_pct']:+.1f} %)"
        for n in plan.get("salidas", [])
    )
    stop = (plan.get("stop_loss") or {}).get("precio")
    linea_stop = f"\n  • Stop loss: {stop:.2f}" if stop else ""
    return enviar(
        f"<b>StockScanner · Plan DCA ejecutado</b>\n"
        f"<b>{ticker}</b> — {veredicto}\n\n{entradas}\n{salidas}{linea_stop}"
    )


def alerta_nivel_alcanzado(ticker: str, tipo: str, nivel: int, precio: float) -> bool:
    return enviar(
        f"<b>StockScanner · Nivel alcanzado</b>\n"
        f"<b>{ticker}</b>: {tipo} {nivel} en {precio:.2f}"
    )
