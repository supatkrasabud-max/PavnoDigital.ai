"""แจ้ง error ของระบบ: Telegram (ถ้าตั้ง TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID) ไม่งั้นส่ง LINE หา CEO"""
from __future__ import annotations

import json
import logging
import urllib.request

log = logging.getLogger("alerts")


def send_telegram(token: str, chat_id: str, text: str) -> None:
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=json.dumps({"chat_id": chat_id, "text": text[:4000]}).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=20) as r:
        r.read()


def alert_error(cfg, line, where: str, err: Exception) -> None:
    """ห้ามโยน error ต่อ: การแจ้งเตือนล้มต้องไม่ทำให้ระบบหลักล้มตาม"""
    text = f"⚠️ PAVNO bot error ที่ {where}: {type(err).__name__}: {str(err)[:300]}"
    token = getattr(cfg, "TELEGRAM_BOT_TOKEN", "")
    chat = getattr(cfg, "TELEGRAM_CHAT_ID", "")
    try:
        if token and chat:
            send_telegram(token, chat, text)
            return
    except Exception:
        log.exception("telegram alert failed")
    ceo = (cfg.CEO_USER_ID or "").split(",")[0].strip()
    if ceo:
        try:
            line.push(ceo, text)
        except Exception:
            log.exception("line alert failed")
