"""เว็บเซิร์ฟเวอร์ของบอท

  POST /callback        ← LINE webhook (ข้อความจากกลุ่ม)
  POST /stripe/webhook  ← Stripe แจ้งเมื่อมีคนจ่ายเงิน → Yuki บันทึกรายรับอัตโนมัติ
  GET  /cron/daily      ← Cloud Scheduler เรียกทุกเช้า → สรุปเมื่อวาน + ความคืบหน้าเทียบเป้า
  GET  /cron/weekly     ← Cloud Scheduler เรียกทุกวันจันทร์ → รายงานสัปดาห์ที่แล้ว
  GET  /cron/monthly    ← Cloud Scheduler เรียกทุกวันที่ 1 → รายงานเดือนที่แล้ว
  GET  /health
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Route

from .agents import Team
from .config import settings
from .ledger import baht, make_ledger
from .line_api import LineClient, verify_signature
from .llm import ClaudeClient

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("app")


def build_app(team: Team | None = None, line: LineClient | None = None, cfg=settings) -> Starlette:
    team = team or Team(ClaudeClient(cfg.ANTHROPIC_API_KEY), make_ledger(cfg), cfg)
    line = line or LineClient(cfg.LINE_CHANNEL_ACCESS_TOKEN)

    async def callback(request: Request):
        body = await request.body()
        if not verify_signature(cfg.LINE_CHANNEL_SECRET, body, request.headers.get("x-line-signature", "")):
            return PlainTextResponse("bad signature", status_code=400)
        for ev in json.loads(body or b"{}").get("events", []):
            if ev.get("type") != "message" or ev.get("message", {}).get("type") != "text":
                continue
            src = ev.get("source", {})
            chat_id = src.get("groupId") or src.get("roomId") or src.get("userId", "")
            try:
                answer = team.handle(ev["message"]["text"], src.get("userId", ""), chat_id,
                                     is_group=src.get("type") in ("group", "room"))
            except Exception:
                log.exception("handle failed")
                answer = "ขออภัย ระบบขัดข้องชั่วคราว ลองใหม่อีกครั้งนะคะ"
            if answer:
                try:
                    line.reply_or_push(ev.get("replyToken", ""), chat_id, answer)
                except Exception:
                    log.exception("send failed")
        return PlainTextResponse("ok")

    async def stripe_webhook(request: Request):
        body = await request.body()
        if not verify_stripe(cfg.STRIPE_WEBHOOK_SECRET, body, request.headers.get("stripe-signature", "")):
            return PlainTextResponse("bad signature", status_code=400)
        event = json.loads(body)
        obj = event.get("data", {}).get("object", {})
        paid = (event.get("type") == "checkout.session.completed" and obj.get("payment_status") == "paid") \
            or event.get("type") == "checkout.session.async_payment_succeeded"
        if not paid:
            return JSONResponse({"ignored": event.get("type")})
        amount = (obj.get("amount_total") or 0) / 100  # THB เก็บเป็นสตางค์
        category = (obj.get("metadata") or {}).get("category", "ขายไฟล์ PDF (เว็บ/Stripe)")
        try:
            e = team.ledger.add_entry("income", category, amount,
                                      note=f"Stripe {obj.get('payment_link') or ''}".strip(),
                                      recorded_by="Stripe", ref=obj.get("id", ""), channel="เว็บ PAVNO")
        except ValueError as err:  # ซ้ำ (Stripe ส่งซ้ำได้)
            return JSONResponse({"skipped": str(err)})
        target = cfg.LINE_GROUP_ID or cfg.CEO_USER_ID
        if cfg.NOTIFY_EACH_SALE and target:
            line.push(target, f"Yuki: มียอดขายใหม่ {baht(e.amount)} ({category}) บันทึกแล้วค่ะ")
        return JSONResponse({"recorded": e.id})

    def _cron(period: str, title: str):
        async def handler(request: Request):
            if not cfg.CRON_SECRET or request.query_params.get("key") != cfg.CRON_SECRET:
                return PlainTextResponse("forbidden", status_code=403)
            text = team.report(period, title)
            target = cfg.LINE_GROUP_ID or cfg.CEO_USER_ID  # กลุ่มบริษัท หรือแชต 1:1 กับ CEO
            if target:
                line.push(target, "Yuki: " + text)
            return PlainTextResponse(text)
        return handler

    async def health(request: Request):
        return PlainTextResponse("ok")

    return Starlette(routes=[
        Route("/callback", callback, methods=["POST"]),
        Route("/stripe/webhook", stripe_webhook, methods=["POST"]),
        Route("/cron/daily", _cron("yesterday", "สรุปประจำวัน (เมื่อวาน)"), methods=["GET", "POST"]),
        Route("/cron/weekly", _cron("last_week", "รายงานบัญชีประจำสัปดาห์"), methods=["GET", "POST"]),
        Route("/cron/monthly", _cron("last_month", "รายงานบัญชีประจำเดือน"), methods=["GET", "POST"]),
        Route("/health", health),
    ])


def verify_stripe(secret: str, body: bytes, header: str, tolerance: int = 300) -> bool:
    if not secret:
        return False
    parts = dict(p.split("=", 1) for p in header.split(",") if "=" in p)
    t, sigs = parts.get("t"), [p.split("=", 1)[1] for p in header.split(",") if p.startswith("v1=")]
    if not t or not sigs or abs(time.time() - int(t)) > tolerance:
        return False
    expected = hmac.new(secret.encode(), f"{t}.".encode() + body, hashlib.sha256).hexdigest()
    return any(hmac.compare_digest(expected, s) for s in sigs)

# รันด้วย: uvicorn app.main:build_app --factory --host 0.0.0.0 --port 8080
