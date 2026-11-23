"""เว็บเซิร์ฟเวอร์ของบอท

  POST /callback        ← LINE webhook (ข้อความจากกลุ่ม)
  POST /stripe/webhook  ← Stripe แจ้งเมื่อมีคนจ่ายเงิน → Yuki บันทึกรายรับอัตโนมัติ
  GET  /cron/daily      ← Cloud Scheduler เรียกทุกเช้า → สรุปเมื่อวาน + ความคืบหน้าเทียบเป้า
  GET  /cron/weekly     ← Cloud Scheduler เรียกทุกวันจันทร์ → รายงานสัปดาห์ที่แล้ว
  GET  /cron/monthly    ← Cloud Scheduler เรียกทุกวันที่ 1 → รายงานเดือนที่แล้ว
  GET  /cron/affiliate   ← ทุกเช้า 06:00 → Affiliate Researcher หาสินค้า + บท ลง Pipeline_Affiliate
  GET  /cron/sales       ← จันทร์–ศุกร์ 06:30 → Sales Agent หาลีด + ร่างข้อความ (รอ CEO อนุมัติ)
  GET  /cron/sales-summary ← จันทร์–ศุกร์ 17:00 → สรุปงานขาย
  (ใส่ &dry=1 เพื่อทดลองรันโดยไม่บันทึกและไม่ส่ง LINE)
  GET  /fb/drafts?k=…    ← หน้าดูร่างโพสต์ Facebook ที่ Ami ส่งลิงก์ให้ CEO ใน LINE
  GET  /health
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time

from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, PlainTextResponse
from starlette.routing import Route

from .agents import Team
from .alerts import alert_error
from .config import settings
from .facebook import view_key
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
            except Exception as err:
                log.exception("handle failed")
                alert_error(cfg, line, "ตอบแชต", err)
                answer = "ขออภัย ระบบขัดข้องชั่วคราว ลองใหม่อีกครั้งนะคะ"
            if answer is None and src.get("type") == "user" and not team.is_member(src.get("userId", "")):
                # คนนอกทักเข้า LINE OA → ตอบรับสุภาพ บันทึกเป็นลีด แล้วแจ้ง CEO ทันที
                answer = "ขอบคุณที่ติดต่อ PAVNO DIGITAL ค่ะ ทีมงานได้รับข้อความแล้ว จะติดต่อกลับโดยเร็วค่ะ"
                try:
                    lead = team.pipes.inbound(src.get("userId", ""), ev["message"]["text"])
                    ceo = cfg.CEO_USER_ID.split(",")[0].strip()
                    if ceo:
                        line.push(ceo, f"🔔 มีคนทักเข้า LINE OA ({lead['id']}): {ev['message']['text'][:300]}\n"
                                       "ตอบกลับได้ที่ LINE OA Manager > แชต")
                except Exception as err:
                    log.exception("inbound alert failed")
                    alert_error(cfg, line, "แจ้งลูกค้าทัก", err)
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
        target = cfg.LINE_GROUP_ID or cfg.CEO_USER_ID.split(",")[0].strip()
        if cfg.NOTIFY_EACH_SALE and target:
            line.push(target, f"Yuki: มียอดขายใหม่ {baht(e.amount)} ({category}) บันทึกแล้วค่ะ")
        return JSONResponse({"recorded": e.id})

    def _cron(period: str, title: str):
        async def handler(request: Request):
            if not cfg.CRON_SECRET or request.query_params.get("key") != cfg.CRON_SECRET:
                return PlainTextResponse("forbidden", status_code=403)
            text = team.report(period, title)
            target = cfg.LINE_GROUP_ID or cfg.CEO_USER_ID.split(",")[0].strip()  # กลุ่มบริษัท หรือแชต 1:1 กับ CEO
            if target:
                line.push(target, "Yuki: " + text)
            if period == "yesterday":  # รายงานเช้า: Ami นำเข้าร่างโพสต์ใหม่ ตั้งเวลาที่อนุมัติแล้ว และเตือนร่างที่รออนุมัติ
                try:
                    fb = await run_in_threadpool(team.social.daily)
                    ceo = cfg.CEO_USER_ID.split(",")[0].strip()  # ส่งหา CEO 1:1 เพราะต้องให้ CEO อนุมัติ
                    if fb and ceo:
                        line.push(ceo, fb)
                except Exception as err:
                    log.exception("facebook daily failed")
                    alert_error(cfg, line, "โพสต์ Facebook", err)
            return PlainTextResponse(text)
        return handler

    async def fb_drafts(request: Request):
        """หน้าดูร่างโพสต์ Facebook (ลิงก์ที่ Ami ส่งใน LINE) ใช้รหัสที่ได้จาก CRON_SECRET"""
        key = view_key(cfg.CRON_SECRET)
        if not key or not hmac.compare_digest(request.query_params.get("k", ""), key):
            return PlainTextResponse("forbidden", status_code=403)
        page = await run_in_threadpool(team.social.drafts_html)
        return HTMLResponse(page, headers={"Cache-Control": "no-store", "X-Robots-Tag": "noindex"})

    def _job(name: str, run, prefix: str = ""):
        """งานตั้งเวลาของพนักงาน AI: รัน → ส่ง LINE → ถ้าพังแจ้ง error (Telegram/LINE)"""
        async def handler(request: Request):
            if not cfg.CRON_SECRET or request.query_params.get("key") != cfg.CRON_SECRET:
                return PlainTextResponse("forbidden", status_code=403)
            dry = request.query_params.get("dry") == "1"
            try:
                text = await run_in_threadpool(run, dry)
            except Exception as err:
                log.exception("%s failed", name)
                alert_error(cfg, line, name, err)
                return PlainTextResponse(f"error: {err}", status_code=500)
            target = cfg.LINE_GROUP_ID or cfg.CEO_USER_ID.split(",")[0].strip()
            if target and not dry:
                line.push(target, prefix + text)
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
        Route("/cron/affiliate", _job("affiliate", lambda dry: team.pipes.run_affiliate(dry=dry)),
              methods=["GET", "POST"]),
        Route("/cron/sales", _job("sales", lambda dry: team.pipes.run_sales(dry=dry)), methods=["GET", "POST"]),
        Route("/cron/sales-summary", _job("sales-summary", lambda dry: team.pipes.sales_summary()),
              methods=["GET", "POST"]),
        Route("/fb/drafts", fb_drafts),
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
