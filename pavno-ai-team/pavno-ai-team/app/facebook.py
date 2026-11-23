"""โพสต์เพจ Facebook ผ่าน Ami: ร่าง → CEO อนุมัติใน LINE → บอทตั้งเวลาโพสต์ผ่าน Graph API

ขั้นตอน
1) ร่างโพสต์อยู่ในไฟล์ app/content/fb_*.json → "นำเข้าโพสต์" (หรือรายงานเช้า) ลงแท็บ โพสต์_Facebook สถานะ รออนุมัติ
2) Ami ส่งลิงก์หน้าดูร่าง (/fb/drafts?k=...) ให้ CEO ใน LINE
3) CEO พิมพ์ "อนุมัติโพสต์ FB1A2B" หรือ "อนุมัติโพสต์ทั้งหมด"
4) บอทตั้งเวลาโพสต์บนเพจตามวันเวลาในร่าง (ต้องตั้ง FB_PAGE_ID และ FB_PAGE_TOKEN ก่อน)
   ถ้ายังไม่ได้เชื่อมเพจ สถานะจะเป็น "อนุมัติแล้ว" และตั้งเวลาให้ภายหลังด้วยคำสั่ง "ตั้งเวลาโพสต์"

บอทไม่โพสต์อะไรที่ CEO ยังไม่อนุมัติ
"""
from __future__ import annotations

import glob
import hashlib
import hmac
import html
import json
import logging
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .ledger import Ledger

log = logging.getLogger("facebook")

SHEET = "Facebook"
WAIT = "รออนุมัติ"
APPROVED = "อนุมัติแล้ว"          # อนุมัติแล้ว แต่ยังไม่ได้ส่งไป Facebook (ยังไม่เชื่อมเพจ หรือส่งไม่สำเร็จ)
SCHEDULED = "ตั้งเวลาแล้ว"
POSTED = "โพสต์แล้ว"
REJECTED = "ไม่โพสต์"
CONTENT_DIR = os.path.join(os.path.dirname(__file__), "content")
MIN_LEAD = timedelta(minutes=15)    # Facebook ให้ตั้งเวลาล่วงหน้าได้ตั้งแต่ 10 นาที
MAX_LEAD = timedelta(days=29)       # และไม่เกินประมาณ 30 วัน

HELP_FB = """โพสต์ Facebook (Ami):
• โพสต์  (ดูร่างที่รออนุมัติ + ลิงก์ดูแบบมีรูป)
• อนุมัติโพสต์ FB1A2B / อนุมัติโพสต์ทั้งหมด
• ไม่อนุมัติโพสต์ FB1A2B
• แก้โพสต์ FB1A2B <ข้อความใหม่ทั้งโพสต์>
• เลื่อนโพสต์ FB1A2B 2026-12-20 19:30
• ตั้งเวลาโพสต์  (ส่งโพสต์ที่อนุมัติแล้วแต่ยังไม่ได้ตั้งเวลา)
• นำเข้าโพสต์  (โหลดร่างชุดใหม่จากระบบ)"""


class FacebookError(Exception):
    pass


class FacebookPage:
    """เรียก Graph API ด้วย Page access token"""

    def __init__(self, page_id: str, token: str, version: str = "v21.0"):
        self.page_id, self.token, self.version = page_id, token, version

    @property
    def ready(self) -> bool:
        return bool(self.page_id and self.token)

    def _post(self, path: str, data: dict) -> dict:
        body = urllib.parse.urlencode({**data, "access_token": self.token}).encode()
        req = urllib.request.Request(f"https://graph.facebook.com/{self.version}/{path}", data=body, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            try:
                msg = json.loads(e.read()).get("error", {}).get("message", "")
            except Exception:
                msg = ""
            raise FacebookError(f"Facebook ตอบ {e.code}: {msg or e.reason}") from None

    def post(self, message: str, image_urls: list[str], publish_at: datetime | None) -> str:
        """publish_at=None โพสต์ทันที ไม่งั้นตั้งเวลา คืนรหัสโพสต์"""
        media = []
        for url in image_urls[:10]:
            photo = {"url": url, "published": "false"}
            if publish_at:
                photo["temporary"] = "true"  # รูปของโพสต์ตั้งเวลาต้องเป็น temporary
            media.append(self._post(f"{self.page_id}/photos", photo)["id"])
        data = {"message": message}
        for i, mid in enumerate(media):
            data[f"attached_media[{i}]"] = json.dumps({"media_fbid": mid})
        if publish_at:
            data["published"] = "false"
            data["scheduled_publish_time"] = str(int(publish_at.timestamp()))
        return self._post(f"{self.page_id}/feed", data)["id"]


def view_key(secret: str) -> str:
    """รหัสในลิงก์หน้าดูร่าง (ได้จาก CRON_SECRET ไม่ต้องตั้งเพิ่ม)"""
    return hmac.new(secret.encode(), b"fb-drafts", hashlib.sha256).hexdigest()[:24] if secret else ""


def parse_when(day, at, tz: str) -> datetime:
    """วันที่จากชีตอาจเป็น 2026-12-04 หรือ 4/12/2026 เวลาอาจเป็น 19:30 / 19:30:00 / เศษส่วนของวัน"""
    d = str(day).strip()[:10]
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})$", d) or None
    if m:
        y, mo, dd = map(int, m.groups())
    else:
        m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})", d)
        if not m:
            raise ValueError(f"อ่านวันที่ไม่ได้: {day}")
        dd, mo, y = map(int, m.groups())
    t = str(at).strip()
    m = re.match(r"^(\d{1,2}):(\d{2})", t)
    if m:
        hh, mm = map(int, m.groups())
    else:
        try:
            frac = float(t)
        except ValueError:
            raise ValueError(f"อ่านเวลาไม่ได้: {at}") from None
        mins = round(frac * 24 * 60)
        hh, mm = divmod(mins, 60)
    return datetime(y, mo, dd, hh, mm, tzinfo=ZoneInfo(tz))


def load_drafts(folder: str = CONTENT_DIR) -> list[dict]:
    posts = []
    for path in sorted(glob.glob(os.path.join(folder, "fb_*.json"))):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        for p in data.get("posts", []):
            posts.append({**p, "series": data.get("series", os.path.basename(path))})
    return posts


class Social:
    def __init__(self, ledger: Ledger, settings, page: FacebookPage | None = None):
        self.ledger = ledger
        self.s = settings
        self.page = page or FacebookPage(getattr(settings, "FB_PAGE_ID", ""), getattr(settings, "FB_PAGE_TOKEN", ""),
                                         getattr(settings, "FB_GRAPH_VERSION", "v21.0") or "v21.0")

    # ------------------------------------------------------------ ข้อมูล
    def _now(self) -> datetime:
        return datetime.now(ZoneInfo(self.s.TIMEZONE))

    def rows(self) -> list[dict]:
        return self.ledger.pipeline(SHEET)

    def link(self) -> str:
        key = view_key(getattr(self.s, "CRON_SECRET", ""))
        base = (getattr(self.s, "PUBLIC_BASE_URL", "") or "").rstrip("/")
        return f"{base}/fb/drafts?k={key}" if key and base else ""

    def import_drafts(self, drafts: list[dict] | None = None) -> list[dict]:
        """เพิ่มร่างใหม่ลงชีต (ข้ามร่างที่มีแล้ว ดูจาก วันที่ + สินค้า + หัวข้อ)"""
        drafts = load_drafts() if drafts is None else drafts
        have = {(str(r["date"])[:10], str(r["product"]), str(r["title"])) for r in self.rows()}
        added = []
        for p in drafts:
            key = (str(p["date"])[:10], str(p["product"]), str(p["title"]))
            if key in have:
                continue
            row = {"date": p["date"], "time": p.get("time", "19:30"), "product": p["product"], "title": p["title"],
                   "text": p["text"], "images": "\n".join(p.get("images", [])), "status": WAIT,
                   "updated": self._now().strftime("%Y-%m-%d %H:%M"), "note": p.get("series", "")}
            added.append(self.ledger.add_pipeline(SHEET, row, "FB"))
            have.add(key)
        return added

    # ------------------------------------------------------------ ข้อความ LINE
    def overview(self) -> str:
        rows = self.rows()
        wait = [r for r in rows if r["status"] == WAIT]
        appr = [r for r in rows if r["status"] == APPROVED]
        sched = [r for r in rows if r["status"] == SCHEDULED]
        if not rows:
            return "ยังไม่มีร่างโพสต์ Facebook พิมพ์ \"นำเข้าโพสต์\" เพื่อโหลดชุดใหม่"
        lines = [f"📣 โพสต์ Facebook: รออนุมัติ {len(wait)} · อนุมัติแล้วรอตั้งเวลา {len(appr)} · ตั้งเวลาแล้ว {len(sched)}"]
        for r in wait[:20]:
            lines.append(f"• {r['id']} {str(r['date'])[:10]} {r['product']}: {r['title']}")
        if self.link():
            lines.append(f"\nดูข้อความเต็มและรูป: {self.link()}")
        if wait:
            lines.append("\nอนุมัติ: \"อนุมัติโพสต์ FBxxxx\" หรือ \"อนุมัติโพสต์ทั้งหมด\"\n"
                         "แก้: \"แก้โพสต์ FBxxxx <ข้อความใหม่>\" · ไม่เอา: \"ไม่อนุมัติโพสต์ FBxxxx\"")
        if not self.page.ready:
            lines.append("⚠️ ยังไม่ได้เชื่อมเพจ Facebook (FB_PAGE_TOKEN) อนุมัติได้ แต่บอทจะตั้งเวลาให้หลังเชื่อมเพจ")
        return "\n".join(lines)

    def daily(self) -> str:
        """ทุกเช้า: นำเข้าร่างใหม่ → ตั้งเวลาโพสต์ที่อนุมัติแล้ว (ที่เคยไกลเกินหรือยังไม่เชื่อมเพจ) → เตือนร่างที่รออนุมัติ"""
        added = self.import_drafts()
        lines = []
        if self.page.ready and any(r["status"] == APPROVED for r in self.rows()):
            lines.append(self.schedule_approved())
        wait = [r for r in self.rows() if r["status"] == WAIT]
        if wait:
            head = f"มีร่างโพสต์ Facebook ใหม่ {len(added)} โพสต์ " if added else ""
            lines.append(f"{head}รออนุมัติทั้งหมด {len(wait)} โพสต์ค่ะ\n" + self.overview().split("\n", 1)[1])
        return ("Ami: " + "\n\n".join(lines)) if lines else ""

    # ------------------------------------------------------------ ส่งไป Facebook
    def _publish(self, r: dict) -> dict:
        when = parse_when(r["date"], r["time"], self.s.TIMEZONE)
        now = self._now()
        if when < now - timedelta(minutes=1):
            raise ValueError(f"{r['id']} เลยเวลาโพสต์แล้ว ({when:%Y-%m-%d %H:%M}) เลื่อนด้วย \"เลื่อนโพสต์ {r['id']} YYYY-MM-DD HH:MM\"")
        if when - now > MAX_LEAD:
            raise ValueError(f"{r['id']} ไกลเกิน 29 วัน Facebook ยังไม่ให้ตั้งเวลา จะตั้งให้เมื่อใกล้ถึงวัน")
        publish_at = None if when - now < MIN_LEAD else when
        images = [u.strip() for u in str(r.get("images") or "").splitlines() if u.strip().startswith("https://")]
        fb_id = self.page.post(str(r["text"]), images, publish_at)
        status = POSTED if publish_at is None else SCHEDULED
        return self.ledger.update_pipeline(SHEET, r["id"], status=status, fb_id=fb_id,
                                           updated=now.strftime("%Y-%m-%d %H:%M"), note="")

    def approve(self, ids: list[str] | None) -> str:
        rows = self.rows()
        if ids is None:
            targets = [r for r in rows if r["status"] == WAIT]
        else:
            want = {i.upper() for i in ids}
            targets = [r for r in rows if str(r["id"]).upper() in want]
            missing = want - {str(r["id"]).upper() for r in targets}
            if missing:
                return "ไม่พบรหัส " + ", ".join(sorted(missing))
            done = [r for r in targets if r["status"] in (SCHEDULED, POSTED)]
            if done:
                return f"{done[0]['id']} {done[0]['status']}อยู่แล้วค่ะ"
        if not targets:
            return "ไม่มีโพสต์ที่รออนุมัติค่ะ"
        stamp = self._now().strftime("%Y-%m-%d %H:%M")
        for r in targets:
            self.ledger.update_pipeline(SHEET, r["id"], status=APPROVED, updated=stamp)
        return f"Ami: อนุมัติ {len(targets)} โพสต์แล้วค่ะ\n" + self.schedule_approved()

    def schedule_approved(self) -> str:
        rows = [r for r in self.rows() if r["status"] == APPROVED]
        if not rows:
            return "ไม่มีโพสต์ที่อนุมัติแล้วรอตั้งเวลา"
        if not self.page.ready:
            return (f"ยังไม่ได้เชื่อมเพจ Facebook จึงเก็บไว้เป็น \"{APPROVED}\" {len(rows)} โพสต์ "
                    "เชื่อมเพจแล้วพิมพ์ \"ตั้งเวลาโพสต์\"")
        ok, fail = [], []
        for r in sorted(rows, key=lambda x: str(x["date"])):
            try:
                r2 = self._publish(r)
                ok.append(f"✅ {r2['id']} {str(r2['date'])[:10]} {r2['time']} {r2['status']}")
            except (FacebookError, ValueError) as e:
                log.warning("facebook publish %s failed: %s", r["id"], e)
                self.ledger.update_pipeline(SHEET, r["id"], note=str(e)[:300])
                fail.append(f"⚠️ {r['id']}: {e}")
        return "\n".join(ok + fail)

    def reject(self, post_id: str) -> str:
        r = self.ledger.update_pipeline(SHEET, post_id, status=REJECTED, updated=self._now().strftime("%Y-%m-%d %H:%M"))
        return f"{r['id']} {r['title']}: {REJECTED}"

    def edit(self, post_id: str, text: str) -> str:
        r = [x for x in self.rows() if str(x["id"]).upper() == post_id.upper()]
        if r and r[0]["status"] in (SCHEDULED, POSTED):
            return f"{r[0]['id']} {r[0]['status']}แล้ว แก้ในบอทไม่ได้ ให้แก้ที่ Meta Business Suite ค่ะ"
        r = self.ledger.update_pipeline(SHEET, post_id, text=text.strip(), status=WAIT,
                                        updated=self._now().strftime("%Y-%m-%d %H:%M"))
        return f"แก้ {r['id']} แล้ว กลับไปรออนุมัติค่ะ ดูได้ที่ {self.link()}".strip()

    def move(self, post_id: str, day: str, at: str) -> str:
        parse_when(day, at, self.s.TIMEZONE)  # ตรวจรูปแบบ
        r = [x for x in self.rows() if str(x["id"]).upper() == post_id.upper()]
        if r and r[0]["status"] in (SCHEDULED, POSTED):
            return f"{r[0]['id']} {r[0]['status']}แล้ว เลื่อนในบอทไม่ได้ ให้เลื่อนที่ Meta Business Suite ค่ะ"
        r = self.ledger.update_pipeline(SHEET, post_id, date=day, time=at)
        return f"เลื่อน {r['id']} เป็น {day} {at} แล้วค่ะ (สถานะ {r['status']})"

    # ------------------------------------------------------------ คำสั่งจาก LINE (CEO เท่านั้น)
    def command(self, text: str) -> str | None:
        t = text.strip()
        low = t.lower()
        if low in ("โพสต์", "ร่างโพสต์", "ดูโพสต์", "โพสต์ facebook", "facebook"):
            return self.overview()
        if low in ("นำเข้าโพสต์", "โหลดโพสต์"):
            added = self.import_drafts()
            return f"นำเข้าร่างใหม่ {len(added)} โพสต์ค่ะ\n\n" + self.overview()
        if low == "ตั้งเวลาโพสต์":
            return self.schedule_approved()
        if re.match(r"^อนุมัติโพสต์\s*ทั้งหมด$", t):
            return self.approve(None)
        m = re.match(r"^อนุมัติโพสต์\s+((?:FB[0-9A-F]{4}[\s,]*)+)$", t, re.I)
        if m:
            return self.approve(re.findall(r"FB[0-9A-F]{4}", m.group(1), re.I))
        m = re.match(r"^ไม่อนุมัติโพสต์\s+(FB[0-9A-F]{4})\s*$", t, re.I)
        if m:
            return self.reject(m.group(1))
        m = re.match(r"^แก้โพสต์\s+(FB[0-9A-F]{4})\s+(.+)$", t, re.I | re.S)
        if m:
            return self.edit(m.group(1), m.group(2))
        m = re.match(r"^เลื่อนโพสต์\s+(FB[0-9A-F]{4})\s+(\d{4}-\d{2}-\d{2})\s+(\d{1,2}:\d{2})\s*$", t, re.I)
        if m:
            return self.move(m.group(1), m.group(2), m.group(3))
        return None

    # ------------------------------------------------------------ หน้าเว็บดูร่าง
    def drafts_html(self) -> str:
        rows = sorted(self.rows(), key=lambda r: (str(r["date"])[:10], str(r["time"])))
        color = {WAIT: "#b45309", APPROVED: "#2563eb", SCHEDULED: "#15803d", POSTED: "#15803d", REJECTED: "#9ca3af"}
        cards = []
        for r in rows:
            imgs = "".join(f'<img src="{html.escape(u.strip())}" alt="" loading="lazy">'
                           for u in str(r.get("images") or "").splitlines() if u.strip().startswith("https://"))
            note = f'<p class="note">{html.escape(str(r["note"]))}</p>' if r.get("note") and r["status"] != WAIT else ""
            cmd = (f'<p class="cmd">พิมพ์ใน LINE: <b>อนุมัติโพสต์ {html.escape(str(r["id"]))}</b></p>'
                   if r["status"] == WAIT else "")
            cards.append(
                f'<article><header><b>{html.escape(str(r["id"]))}</b> · {html.escape(str(r["date"])[:10])} '
                f'{html.escape(str(r["time"]))} · {html.escape(str(r["product"]))}'
                f'<span style="background:{color.get(r["status"], "#6b7280")}">{html.escape(str(r["status"]))}</span></header>'
                f'<h2>{html.escape(str(r["title"]))}</h2><pre>{html.escape(str(r["text"]))}</pre>'
                f'<div class="imgs">{imgs}</div>{note}{cmd}</article>')
        body = "".join(cards) or "<p>ยังไม่มีร่างโพสต์</p>"
        return ("<!doctype html><html lang='th'><head><meta charset='utf-8'>"
                "<meta name='viewport' content='width=device-width,initial-scale=1'><meta name='robots' content='noindex'>"
                "<title>ร่างโพสต์ Facebook · PAVNO</title><style>"
                "body{margin:0;background:#f3f4f6;font-family:system-ui,'Noto Sans Thai',sans-serif;color:#111827}"
                "main{max-width:640px;margin:0 auto;padding:16px}h1{font-size:20px}"
                "article{background:#fff;border-radius:12px;padding:14px;margin:0 0 14px;box-shadow:0 1px 3px #0001}"
                "header{font-size:13px;color:#6b7280;display:flex;gap:6px;align-items:center;flex-wrap:wrap}"
                "header span{color:#fff;border-radius:99px;padding:2px 10px;margin-left:auto}"
                "h2{font-size:16px;margin:8px 0}pre{white-space:pre-wrap;font-family:inherit;font-size:15px;line-height:1.6;margin:0}"
                ".imgs{display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-top:10px}"
                ".imgs img{width:100%;border-radius:8px;border:1px solid #e5e7eb}"
                ".cmd{background:#fef3c7;border-radius:8px;padding:8px;font-size:14px}.note{color:#b91c1c;font-size:13px}"
                f"</style></head><body><main><h1>ร่างโพสต์เพจ PAVNO Learn</h1>{body}</main></body></html>")
