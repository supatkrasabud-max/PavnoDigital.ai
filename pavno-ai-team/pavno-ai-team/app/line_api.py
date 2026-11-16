"""LINE Messaging API: ตรวจลายเซ็น, ตอบกลับ (reply), ส่งข้อความ (push)"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import urllib.error
import urllib.request

log = logging.getLogger("line")
MAX_LEN = 4900  # LINE จำกัด 5,000 ตัวอักษรต่อข้อความ


def verify_signature(channel_secret: str, body: bytes, signature: str) -> bool:
    mac = hmac.new(channel_secret.encode(), body, hashlib.sha256).digest()
    return hmac.compare_digest(base64.b64encode(mac).decode(), signature or "")


def split_text(text: str) -> list[dict]:
    parts, text = [], text or "-"
    while text and len(parts) < 5:  # LINE ส่งได้สูงสุด 5 ข้อความต่อครั้ง
        cut = text[:MAX_LEN]
        if len(text) > MAX_LEN and "\n" in cut:
            cut = cut[:cut.rfind("\n")]
        parts.append({"type": "text", "text": cut})
        text = text[len(cut):].lstrip("\n")
    return parts


class LineClient:
    def __init__(self, access_token: str):
        self.token = access_token

    def _post(self, path: str, payload: dict) -> None:
        req = urllib.request.Request(
            f"https://api.line.me/v2/bot/message/{path}",
            data=json.dumps(payload).encode(),
            headers={"Authorization": f"Bearer {self.token}",
                     "Content-Type": "application/json"},
            method="POST")
        with urllib.request.urlopen(req, timeout=30) as r:
            r.read()

    def reply(self, reply_token: str, text: str) -> None:
        self._post("reply", {"replyToken": reply_token, "messages": split_text(text)})

    def push(self, to: str, text: str) -> None:
        self._post("push", {"to": to, "messages": split_text(text)})

    def reply_or_push(self, reply_token: str, to: str, text: str) -> None:
        """ตอบด้วย reply (ฟรี) ก่อน ถ้า token หมดอายุค่อย push (นับโควตา)"""
        try:
            self.reply(reply_token, text)
        except urllib.error.HTTPError as e:
            log.warning("reply failed (%s), falling back to push", e.code)
            self.push(to, text)
